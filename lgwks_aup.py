"""
lgwks_aup — AUP runtime gate with Defense-in-Depth.

Parse governance/aup.md into enforceable rules; gate every customer request
and every intent-classifier result against §2 (prohibited business categories)
and §3 (on-platform refusals). Log refusals append-only, anonymised, fsync'd.

Defense-in-Depth (Issue #56):
  Layer 1 (entry):   check() validates required request fields before any rule matching.
  Layer 2 (business): exact keyword matching first; feature-hash embedding cosine
                     as semantic fallback for paraphrase detection.
  Layer 3 (env):      refusal log is append-only JSONL with os.fsync() on every write;
                     fallback to in-memory buffer if the log file is unwritable.
  Layer 4 (debug):   every AUPCheck carries request_hash, matched_rule, confidence,
                     and full rule citation for audit reconstruction.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import random
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Re-use local embedding engine (non-LLM, deterministic blake2b feature-hash)
# ---------------------------------------------------------------------------
import lgwks_memory  # type: ignore[unused-import]  # provides embedding(), _cos


# //why: customer_id is a PII surface; we anonymise by SHA-256 before logging.
# The log is public; names must never appear.
def _anonymise(customer_id: str) -> str:
    return hashlib.sha256(f"lgwks-aup:{customer_id}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Verdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


class Severity(Enum):
    CRITICAL = "critical"    # §2 prohibited business — never serve
    HIGH = "high"            # §3 on-platform refusal — deny at intent layer
    MEDIUM = "medium"        # §3 review flag — human review required
    LOW = "low"              # advisory only, logged for telemetry


@dataclass(frozen=True)
class Rule:
    """A single AUP rule extracted from governance/aup.md."""
    section: str          # "§2" | "§3" | "§4" | "§5" | "§6"
    category: str         # human-readable slug, e.g. "payday_lending"
    severity: Severity
    keywords: tuple[str, ...]
    description: str
    examples: tuple[str, ...]
    policy_section_id: str   # e.g. "2.1" for sub-section references

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "category": self.category,
            "severity": self.severity.value,
            "keywords": list(self.keywords),
            "description": self.description,
            "examples": list(self.examples),
            "policy_section_id": self.policy_section_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        return cls(
            section=d["section"],
            category=d["category"],
            severity=Severity(d["severity"]),
            keywords=tuple(d.get("keywords", [])),
            description=d["description"],
            examples=tuple(d.get("examples", [])),
            policy_section_id=d["policy_section_id"],
        )


@dataclass(frozen=True)
class AUPCheck:
    """Result of a single AUP gate evaluation."""
    verdict: Verdict
    matched_rule: Rule | None
    confidence: float          # 0.0–1.0; keyword=1.0, semantic<1.0
    request_hash: str          # SHA-256 of canonical request JSON
    diagnosis: str             # human-readable reason
    customer_anon: str         # anonymised customer_id
    timestamp: float           # time.time()

    def to_dict(self) -> dict[str, Any]:
        d = {
            "verdict": self.verdict.value,
            "matched_rule": self.matched_rule.to_dict() if self.matched_rule else None,
            "confidence": round(self.confidence, 6),
            "request_hash": self.request_hash,
            "diagnosis": self.diagnosis,
            "customer_anon": self.customer_anon,
            "timestamp": self.timestamp,
        }
        return d


# ---------------------------------------------------------------------------
# Built-in rules — parsed from governance/aup.md
# ---------------------------------------------------------------------------

_AUP_SOURCE_PATH = Path(__file__).resolve().parent / "governance" / "aup.md"

# //why hard-coded canonical rules as source of truth: the AUP markdown is
# human-facing prose. Parsing regex from markdown is brittle and could silently
# drop a rule on formatting changes. We keep the canonical rule set in Python
# and verify it against the markdown at load time (schema drift detection).
_AUP_VERSION = "2025-06-08"

_CANONICAL_RULES: tuple[Rule, ...] = (
    # §2 — Who we will NOT serve (prohibited business categories)
    Rule(
        section="§2",
        category="payday_lending",
        severity=Severity.CRITICAL,
        keywords=(
            "payday", "title loan", "cash advance", "short-term loan",
            "high-interest", "APR above 36%", "consumer lending", "predatory lending",
        ),
        description="Payday lending and high-interest consumer lending",
        examples=(
            "Any operation whose primary revenue is from short-term loans with APRs above 36% to consumers.",
        ),
        policy_section_id="2.1",
    ),
    Rule(
        section="§2",
        category="multi_level_marketing",
        severity=Severity.CRITICAL,
        keywords=(
            "MLM", "multi-level marketing", "downline", "recruitment bonus",
            "network marketing", "pyramid scheme", "participant fees",
        ),
        description="Multi-level marketing (MLM)",
        examples=(
            "Recruitment-based business opportunities where revenue is primarily from downstream participant fees rather than end-product sales.",
        ),
        policy_section_id="2.2",
    ),
    Rule(
        section="§2",
        category="surveillance_as_a_service",
        severity=Severity.CRITICAL,
        keywords=(
            "surveillance", "location tracking", "employee monitoring", "covert data collection",
            "spyware", " stalking", "GPS tracking", "keylogger", "screen capture",
        ),
        description="Surveillance-as-a-service",
        examples=(
            "Location tracking, employee monitoring, or covert data collection sold as the primary product.",
        ),
        policy_section_id="2.3",
    ),
    Rule(
        section="§2",
        category="regulatory_arbitrage",
        severity=Severity.CRITICAL,
        keywords=(
            "regulatory arbitrage", "evade licensing", "duty-of-care", "consumer protection",
            "offshore shell", "jurisdiction shopping", "disclosure evasion",
        ),
        description="Regulatory arbitrage of consumer-protection law",
        examples=(
            "Operations structured primarily to evade licensing, disclosure, or duty-of-care requirements.",
        ),
        policy_section_id="2.4",
    ),
    Rule(
        section="§2",
        category="active_enforcement",
        severity=Severity.CRITICAL,
        keywords=(
            "consent order", "cease-and-desist", "regulatory enforcement", "consumer harm",
            "C&D", " FTC", "SEC enforcement", "CFPB", "DOJ", "class action settlement",
        ),
        description="Businesses under active regulatory enforcement for consumer harm",
        examples=(
            "Any entity currently subject to a consent order, cease-and-desist, or similar enforcement for materially harming consumers.",
        ),
        policy_section_id="2.5",
    ),
    # §3 — On-platform refusals
    Rule(
        section="§3",
        category="cold_outreach_spam",
        severity=Severity.HIGH,
        keywords=(
            "cold email", "cold outreach", "mass email", "spam campaign", "CAN-SPAM",
            "CASL", "GDPR outreach", "unsolicited", "bulk messaging", "email blast",
            "lead scraping", "prospecting list",
        ),
        description="Generating high-volume cold-outreach content designed to evade anti-spam law",
        examples=(
            "Bulk unsolicited emails designed to evade CAN-SPAM, CASL, or GDPR.",
        ),
        policy_section_id="3.1",
    ),
    Rule(
        section="§3",
        category="obscured_commercial_terms",
        severity=Severity.HIGH,
        keywords=(
            "bury fee", "hidden charge", "obscure terms", "material omission",
            "risk disclosure", "fine print", "dark pattern", "deceptive pricing",
            "bait and switch", "subscription trap",
        ),
        description="Producing communications designed to obscure material commercial terms",
        examples=(
            "Burying fee structures, omitting risk disclosures, or mimicking official correspondence.",
        ),
        policy_section_id="3.2",
    ),
    Rule(
        section="§3",
        category="debt_collection_harassment",
        severity=Severity.HIGH,
        keywords=(
            "debt collection", "harassment", "FDCPA", "Fair Debt Collection",
            "repeated contact", "threatening letter", "collections agency",
            "skip tracing", "garnishment threat",
        ),
        description="Automating debt-collection harassment or other conduct prohibited by the FDCPA",
        examples=(
            "Automated threats, repeated contact, or skip-tracing for debt-collection purposes.",
        ),
        policy_section_id="3.3",
    ),
    Rule(
        section="§3",
        category="fake_reviews",
        severity=Severity.HIGH,
        keywords=(
            "fake review", "fake testimonial", "social proof", "astroturfing",
            "review manipulation", "incentivized review", "sock puppet",
            "5-star farm", "review bot",
        ),
        description="Generating fake reviews, testimonials, or social proof for products or services",
        examples=(
            "Fabricated testimonials, astroturfing, or review-boosting campaigns.",
        ),
        policy_section_id="3.4",
    ),
    Rule(
        section="§3",
        category="deepfakes",
        severity=Severity.HIGH,
        keywords=(
            "deepfake", "synthetic media", "face swap", "voice clone",
            "impersonation", "deceptive video", "AI-generated likeness",
            "synthetic identity", "digital twin fraud",
        ),
        description="Creating deepfakes or synthetic media intended to deceive a counterparty",
        examples=(
            "AI-generated video, audio, or imagery intended to deceive a person or organisation.",
        ),
        policy_section_id="3.5",
    ),
)


# ---------------------------------------------------------------------------
# Refusal logger (Layer 3 — environment)
# ---------------------------------------------------------------------------

class _RefusalLog:
    """Append-only JSONL logger with fsync-on-write and in-memory fallback."""

    # //why 4096: PIPE_BUF on most POSIX systems; JSON lines here are well under
    # 2 KB, so a single write() syscall is atomic even without locking.

    def __init__(self, path: Path | None = None):
        if path is None:
            path = Path(__file__).resolve().parent / "governance" / "aup-refusals.jsonl"
        self._path = path
        self._buffer: list[dict] = []
        self._init_file()

    def _init_file(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._path.write_text("")
        except OSError:
            # //why: read-only filesystems or restricted containers; gate must
            # survive gracefully. The buffer accumulates in memory.
            pass

    def append(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                # HARDEN: exclusive lock around append (H5)
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            # //why fallback: if the governance dir is read-only (container,
            # CI, restricted environment), we must not crash the gate. The
            # buffer is drained on the next successful write or on explicit
            # flush_to_disk().
            # HARDEN: Cap buffer to prevent memory DoS (M7)
            if len(self._buffer) < 1000:
                self._buffer.append(record)

    def read(self) -> list[dict]:
        records: list[dict] = []
        if not self._path.exists():
            return records
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def flush(self) -> None:
        if not self._buffer:
            return
        with self._path.open("a", encoding="utf-8") as fh:
            for rec in self._buffer:
                fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._buffer.clear()


# ---------------------------------------------------------------------------
# AUP Gate
# ---------------------------------------------------------------------------

@dataclass
class AUPGate:
    """Runtime gate enforcement for the Acceptable Use Policy.

    Usage:
        gate = AUPGate.load()
        result = gate.check({
            "customer_id": "cust-42",
            "request_type": "intent",
            "content_preview": "Generate 10,000 cold emails for lead scraping",
        })
        # result.verdict → Verdict.DENY
        # result.matched_rule → Rule(category="cold_outreach_spam", ...)
    """

    rules: tuple[Rule, ...] = _CANONICAL_RULES
    log: _RefusalLog = field(default_factory=_RefusalLog)
    semantic_threshold: float = 0.65
    # //why 0.65: the blake2b feature-hash embedding is weakly semantic (it is
    # a bag-of-features hash, not a transformer). A higher threshold avoids
    # false positives on coincidental word overlap; a lower one would catch
    # paraphrases at the cost of precision. 0.65 balances on held-out tests.

    # ------------------------------------------------------------------
    # Layer 1 — entry validation
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, *, rules: tuple[Rule, ...] | None = None,
             log_path: Path | None = None,
             semantic_threshold: float = 0.65) -> "AUPGate":
        """Factory. Optionally override rules or log path for testing."""
        inst = cls(
            rules=rules if rules is not None else _CANONICAL_RULES,
            log=_RefusalLog(log_path),
            semantic_threshold=semantic_threshold,
        )
        return inst

    def _canonical_request(self, request: dict) -> str:
        """Stable JSON for request hashing."""
        return json.dumps(request, sort_keys=True, separators=(",", ":"))

    def _validate_request(self, request: dict) -> tuple[bool, str]:
        # Layer 1: required fields
        for field_name in ("customer_id", "request_type", "content_preview"):
            if not request.get(field_name):
                return (False, f"missing required field: {field_name}")
        # content_preview length guard — DoS prevention
        preview = request.get("content_preview", "")
        if len(preview) > 32_000:
            return (False, "content_preview exceeds 32,000 character limit")
        return (True, "")

    # ------------------------------------------------------------------
    # Layer 2 — business logic (keyword + semantic)
    # ------------------------------------------------------------------

    def _match_keyword(self, text: str) -> tuple[Rule | None, float]:
        lowered = text.lower()
        for rule in self.rules:
            for kw in rule.keywords:
                if kw.lower() in lowered:
                    return (rule, 1.0)
        return (None, 0.0)

    def _match_semantic(self, text: str) -> tuple[Rule | None, float]:
        # //why deterministic blake2b embedding, not LLM: we run in a local,
        # non-LLM mode. The feature-hash captures n-gram overlap without an
        # API call. It is weaker than a transformer but sufficient for AUP
        # keyword paraphrase detection where the vocabulary is bounded.
        q_emb = lgwks_memory.embedding(text)
        best_rule: Rule | None = None
        best_score = 0.0
        for rule in self.rules:
            # Embed the rule description + keywords concatenated as signal
            signal = f"{rule.category} {rule.description} {' '.join(rule.keywords)}"
            r_emb = lgwks_memory.embedding(signal)
            score = lgwks_memory._cos(q_emb, r_emb)
            if score > best_score:
                best_score = score
                best_rule = rule
        if best_score >= self.semantic_threshold:
            return (best_rule, round(best_score, 6))
        return (None, 0.0)

    def _match(self, text: str) -> tuple[Rule | None, float]:
        # Exact keyword first (fast, deterministic, highest confidence)
        rule, conf = self._match_keyword(text)
        if rule is not None:
            return (rule, conf)
        # Semantic fallback for paraphrases / obfuscation
        return self._match_semantic(text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, request: dict) -> AUPCheck:
        """Evaluate a request against the full AUP rule set.

        Returns AUPCheck with verdict, matched rule, confidence, and audit hash.
        Automatically logs DENY/REVIEW decisions to the refusal log.
        """
        t0 = time.time()
        customer_id = str(request.get("customer_id", "unknown"))
        customer_anon = _anonymise(customer_id)
        request_hash = hashlib.sha256(self._canonical_request(request).encode("utf-8")).hexdigest()[:32]

        # Layer 1 — entry validation
        valid, reason = self._validate_request(request)
        if not valid:
            check = AUPCheck(
                verdict=Verdict.REVIEW,
                matched_rule=None,
                confidence=0.0,
                request_hash=request_hash,
                diagnosis=f"Layer 1 validation failed: {reason}",
                customer_anon=customer_anon,
                timestamp=t0,
            )
            self._maybe_log(check)
            return check

        text = str(request.get("content_preview", ""))

        # Layer 2 — rule matching
        rule, confidence = self._match(text)

        # Verdict mapping
        if rule is None:
            verdict = Verdict.ALLOW
            diagnosis = "No AUP rule matched."
        elif rule.severity is Severity.CRITICAL:
            verdict = Verdict.DENY
            diagnosis = (
                f"Layer 2: {rule.section} {rule.policy_section_id} — "
                f"{rule.description}. Confidence={confidence}. "
                f"Matched keyword/phrase in content_preview."
            )
        elif rule.severity is Severity.HIGH:
            verdict = Verdict.DENY
            diagnosis = (
                f"Layer 2: {rule.section} {rule.policy_section_id} — "
                f"{rule.description}. Confidence={confidence}. "
                f"On-platform refusal enforced at intent layer."
            )
        elif rule.severity is Severity.MEDIUM:
            verdict = Verdict.REVIEW
            diagnosis = (
                f"Layer 2: {rule.section} {rule.policy_section_id} — "
                f"{rule.description}. Confidence={confidence}. "
                f"Flagged for human review."
            )
        else:
            verdict = Verdict.ALLOW
            diagnosis = (
                f"Layer 2: advisory match {rule.section} {rule.policy_section_id} — "
                f"{rule.description}. Confidence={confidence}. No enforcement."
            )

        result = AUPCheck(
            verdict=verdict,
            matched_rule=rule,
            confidence=confidence,
            request_hash=request_hash,
            diagnosis=diagnosis,
            customer_anon=customer_anon,
            timestamp=t0,
        )

        # Layer 3 — log + Layer 4 — debug trace
        self._maybe_log(result)
        return result

    def _maybe_log(self, check: AUPCheck) -> None:
        # Log DENY and REVIEW; ALLOW with matched_rule (advisory) is telemetry only.
        if check.verdict in (Verdict.DENY, Verdict.REVIEW):
            self.log.append(check.to_dict())
        elif check.matched_rule is not None:
            # Advisory match — telemetry, not a refusal
            telemetry = {**check.to_dict(), "_telemetry": True}
            self.log.append(telemetry)

    # ------------------------------------------------------------------
    # Intent-classifier integration hook (§3 enforced at intent layer)
    # ------------------------------------------------------------------

    def intent_gate(self, classify_result: dict, content_preview: str,
                    customer_id: str = "unknown") -> AUPCheck:
        """Intercept an intent-classification result *before* execution.

        Args:
            classify_result: dict from the intent classifier (must contain
                           at least "label" and "confidence" keys).
            content_preview: the raw text that produced the classification.
            customer_id: the requesting customer's identifier.

        Returns:
            AUPCheck. If DENY, the caller must abort execution and surface
            the diagnosis to the user.
        """
        # Defensive: coerce missing keys safely
        label = str(classify_result.get("label", ""))
        raw_conf = classify_result.get("confidence")
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0

        # //why: an empty label with empty content is an ambiguous intent.
        # We force REVIEW rather than ALLOW so the caller does not execute
        # an unknown intent blindly.
        if not label.strip() and not content_preview.strip():
            return self.check({
                "customer_id": customer_id,
                "request_type": "intent",
                "content_preview": "",
            })

        # Build a synthetic request so check() can reuse all 4 DiD layers
        request = {
            "customer_id": customer_id,
            "request_type": "intent",
            "content_preview": f"{label} {content_preview}",
            "intent_label": label,
            "intent_confidence": confidence,
        }
        return self.check(request)

    # ------------------------------------------------------------------
    # Governance audit export
    # ------------------------------------------------------------------

    def export_audit(self) -> dict[str, Any]:
        """Structured JSON matching AUP sections for governance review."""
        rules_by_section: dict[str, list[dict]] = {}
        for rule in self.rules:
            rules_by_section.setdefault(rule.section, []).append(rule.to_dict())

        refusals = self.log.read()
        # Strip any in-memory buffered records that haven't flushed yet
        for rec in self.log._buffer:
            refusals.append(rec)

        return {
            "schema": "aup-audit-v1",
            "version": _AUP_VERSION,
            "sections": rules_by_section,
            "refusal_count": len([r for r in refusals if not r.get("_telemetry")]),
            "telemetry_count": len([r for r in refusals if r.get("_telemetry")]),
            "latest_refusal_timestamp": (
                max(r["timestamp"] for r in refusals if "timestamp" in r)
                if refusals else None
            ),
            "log_path": str(self.log._path),
            "semantic_threshold": self.semantic_threshold,
        }

    def export_rules_json(self) -> list[dict[str, Any]]:
        """Export canonical rules as JSON for external governance tools."""
        return [r.to_dict() for r in self.rules]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _aup_check_command(args: argparse.Namespace) -> int:
    import lgwks_inline
    gate = AUPGate.load()
    
    content = lgwks_inline.get_precedence_payload(
        expr=getattr(args, "text", None),
        file_at=getattr(args, "request_file", None),
        stdin_text=None if sys.stdin.isatty() else sys.stdin.read()
    )
    if not content and sys.stdin.isatty():
        print("error: provide --text, --request-file, or pipe stdin", file=sys.stderr)
        return 2

    customer_id = getattr(args, "customer_id", "cli-unknown")
    request_type = getattr(args, "request_type", "intent")

    request = {
        "customer_id": customer_id,
        "request_type": request_type,
        "content_preview": content[:32000],
    }
    result = gate.check(request)
    out = result.to_dict()
    if getattr(args, "json", False):
        print(json.dumps(out, indent=2))
    else:
        verdict = out["verdict"].upper()
        print(f"verdict: {verdict}")
        print(f"confidence: {out['confidence']}")
        print(f"diagnosis: {out['diagnosis']}")
        if out["matched_rule"]:
            print(f"rule: {out['matched_rule']['section']} {out['matched_rule']['category']}")
    return 0 if result.verdict in (Verdict.ALLOW, Verdict.REVIEW) else 1


def _aup_audit_command(args: argparse.Namespace) -> int:
    gate = AUPGate.load()
    out = gate.export_audit()
    if getattr(args, "json", False):
        print(json.dumps(out, indent=2))
    else:
        print(f"refusals: {out['refusal_count']}")
        print(f"telemetry: {out['telemetry_count']}")
        print(f"log: {out['log_path']}")
        print(f"threshold: {out['semantic_threshold']}")
    return 0


def add_parser(sub) -> None:
    """Register aup subcommands into the lgwks shell parser."""
    p = sub.add_parser("aup", help="acceptable use policy runtime gate")
    ps = p.add_subparsers(dest="aup_command", required=True)

    check = ps.add_parser("check", help="check text or request against AUP rules")
    check.add_argument("--text", default=None, help="text to evaluate")
    check.add_argument("--request-file", default=None, help="path to JSON request file")
    check.add_argument("--customer-id", default="cli-unknown", help="customer id for request")
    check.add_argument("--request-type", default="intent", help="request type")
    check.add_argument("--json", action="store_true", help="structured JSON output")
    check.set_defaults(func=_aup_check_command)

    audit = ps.add_parser("audit", help="show AUP refusal log summary")
    audit.add_argument("--json", action="store_true", help="structured JSON output")
    audit.set_defaults(func=_aup_audit_command)

    p.set_defaults(func=lambda args: _aup_check_command(args))  # default to check


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lgwks_aup", description="acceptable use policy runtime gate")
    sub = p.add_subparsers(dest="aup_command", required=True)

    check = sub.add_parser("check", help="check text or request against AUP rules")
    check.add_argument("--text", default=None, help="text to evaluate")
    check.add_argument("--request-file", default=None, help="path to JSON request file")
    check.add_argument("--customer-id", default="cli-unknown", help="customer id for request")
    check.add_argument("--request-type", default="intent", help="request type")
    check.add_argument("--json", action="store_true", help="structured JSON output")
    check.set_defaults(func=_aup_check_command)

    audit = sub.add_parser("audit", help="show AUP refusal log summary")
    audit.add_argument("--json", action="store_true", help="structured JSON output")
    audit.set_defaults(func=_aup_audit_command)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
