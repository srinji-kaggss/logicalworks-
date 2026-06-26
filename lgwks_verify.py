"""
lgwks_verify — the Verifier oracle (spec-01), hardened with provenance tracking.

One typed interface every gate implements, with an honest CANNOT_DECIDE third verdict.
The #29 fix encoded in the type system: a model's failure can never be laundered
into a verdict against the human.

HARDENING (Issue #52):
  * Evidence is now structured (source_url, tier, origin_type, transform_hash).
  * LCalculator consumes a pipeline of Verdict objects and returns L = invented / total.
  * Evidence strings passed to Verdict are auto-coerced with conservative origin_type=INVENTED
    so that legacy callers do not silently produce zero-L pipelines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Outcome(Enum):
    PASS = "pass"
    FAIL = "fail"
    CANNOT_DECIDE = "cannot_decide"
    # //why: this is the #29 fix encoded in the type system


class Klass(Enum):
    HARD = "hard"
    ADVISORY = "advisory"


class OriginType(Enum):
    """Provenance classification per ARCHITECTURE.md provenance contract."""
    GROUNDED = "grounded"     # deterministic source: bot, repo, crawl, human_input
    INFERRED = "inferred"     # fixed-weight small model (post-training, deterministic)
    INVENTED = "invented"     # LLM generation — the only origin that contributes to L


@dataclass(frozen=True)
class Evidence:
    """A structured, auditable evidence item attached to a Verdict."""
    source_url: str | None = None
    tier: str = "unverified"                # primary | secondary | unverified
    origin_type: OriginType = OriginType.INVENTED
    transform_hash: str | None = None         # hash of the transform log producing this evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "tier": self.tier,
            "origin_type": self.origin_type.value,
            "transform_hash": self.transform_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            source_url=d.get("source_url"),
            tier=d.get("tier", "unverified"),
            origin_type=OriginType(d.get("origin_type", "invented")),
            transform_hash=d.get("transform_hash"),
        )


@dataclass(frozen=True)
class Verdict:
    gate_id: str
    outcome: Outcome
    klass: Klass
    score: float | None = None           # ADVISORY: calibrated 0..1; HARD: None
    evidence: list[Evidence | str] = field(default_factory=list)
    diagnosis: str | None = None         # on CANNOT_DECIDE/FAIL: what is missing / why

    def __post_init__(self) -> None:
        # Advisory invariant: klass == ADVISORY ⟹ outcome ∈ {PASS, CANNOT_DECIDE}
        # //why: an advisory FAIL is unrepresentable; advisory CANNOT_DECIDE is excluded from score aggregation
        if self.klass is Klass.ADVISORY and self.outcome is Outcome.FAIL:
            raise ValueError("ADVISORY verdict cannot have outcome FAIL")
        # Coerce legacy string evidence to structured Evidence with conservative origin_type=INVENTED.
        # This prevents older gates from accidentally claiming zero-L by not providing provenance.
        object.__setattr__(self, "evidence", [
            e if isinstance(e, Evidence) else Evidence(origin_type=OriginType.INVENTED, tier="legacy_string")
            for e in self.evidence
        ])

    @property
    def provenance(self) -> list[Evidence]:
        """All evidence as structured Evidence (coercion already applied in __post_init__)."""
        return [e for e in self.evidence if isinstance(e, Evidence)]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation for the cognition-log."""
        return {
            "gate_id": self.gate_id,
            "outcome": self.outcome.value,
            "klass": self.klass.value,
            "score": self.score,
            "evidence": [e.to_dict() if isinstance(e, Evidence) else str(e) for e in self.evidence],
            "diagnosis": self.diagnosis,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Verdict":
        raw_ev = d.get("evidence", [])
        evidence: list[Evidence | str] = []
        for e in raw_ev:
            if isinstance(e, dict):
                evidence.append(Evidence.from_dict(e))
            else:
                evidence.append(str(e))
        return cls(
            gate_id=d["gate_id"],
            outcome=Outcome(d["outcome"]),
            klass=Klass(d["klass"]),
            score=d.get("score"),
            evidence=evidence,
            diagnosis=d.get("diagnosis"),
        )


@runtime_checkable
class Verifier(Protocol):
    gate_id: str
    klass: Klass
    def check(self, subject: object, context: object) -> Verdict: ...


@dataclass
class GateRegistry:
    hard: list[Verifier] = field(default_factory=list)
    advisory: list[Verifier] = field(default_factory=list)


def run_pipeline(subject: object, context: object, reg: GateRegistry) -> tuple[bool, list[Verdict]]:
    """
    Fail-fast on HARD (first non-PASS stops), then accumulate ADVISORY.
    Any verifier raising internally is caught and mapped to CANNOT_DECIDE,
    never PASS — this is the safety boundary.
    """
    verdicts: list[Verdict] = []
    for g in reg.hard:
        try:
            v = g.check(subject, context)
        except Exception as exc:
            v = Verdict(
                gate_id=g.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=Klass.HARD,
                diagnosis=f"verifier raised internally: {type(exc).__name__}: {exc}",
            )
        verdicts.append(v)
        if v.outcome is not Outcome.PASS:
            return (False, verdicts)
    for g in reg.advisory:
        try:
            v = g.check(subject, context)
        except Exception as exc:
            v = Verdict(
                gate_id=g.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=Klass.ADVISORY,
                diagnosis=f"verifier raised internally: {type(exc).__name__}: {exc}",
            )
        verdicts.append(v)
    return (True, verdicts)


# ---------------------------------------------------------------------------
# L-Score calculator (Issue #52)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LScore:
    """Pipeline-level provenance audit metric.

    L = invented_claims / total_claims_in_output
    Low L  → system did the work; LLM executed a pre-solved problem. Auditable.
    High L → LLM invented the answer. No trail. Auditor red flag.
    """
    total_claims: int
    invented_claims: int
    inferred_claims: int
    grounded_claims: int
    L: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "invented_claims": self.invented_claims,
            "inferred_claims": self.inferred_claims,
            "grounded_claims": self.grounded_claims,
            "L": round(self.L, 6),
        }


class LCalculator:
    """Compute L from a pipeline of Verdict objects, weighted by evidence provenance.

    Each Verdict is treated as a claim with its evidence list representing sub-claims.
    If a Verdict has no evidence items, the verdict itself is counted as one claim of its
    implicit origin (INVENTED for LLM gates, GROUNDED for bot gates — but since legacy
    evidence defaults to INVENTED, older gates that pass strings will be counted honestly).
    """

    @classmethod
    def from_verdicts(cls, verdicts: list[Verdict]) -> LScore:
        total = 0
        invented = 0
        inferred = 0
        grounded = 0

        for v in verdicts:
            prov = v.provenance
            if not prov:
                # No provenance attached — count the verdict itself as one claim.
                # Default to INVENTED to avoid false-confidence on legacy pipelines.
                total += 1
                invented += 1
                continue
            for e in prov:
                total += 1
                if e.origin_type is OriginType.INVENTED:
                    invented += 1
                elif e.origin_type is OriginType.INFERRED:
                    inferred += 1
                elif e.origin_type is OriginType.GROUNDED:
                    grounded += 1
                else:
                    invented += 1  # conservative catch-all

        L = invented / total if total > 0 else 0.0
        return LScore(total_claims=total, invented_claims=invented,
                      inferred_claims=inferred, grounded_claims=grounded, L=L)

    @classmethod
    def to_report(cls, score: LScore) -> str:
        return (
            f"L={score.L:.4f}  ({score.invented_claims}/{score.total_claims} invented)  "
            f"grounded={score.grounded_claims}  inferred={score.inferred_claims}"
        )


def check_gate_evidence_completeness(verdicts: list[Verdict]) -> tuple[bool, list[str]]:
    """Return (complete, missing_reasons). A gate with FAIL or CANNOT_DECIDE that has zero
    evidence/provenance is flagged as incomplete."""
    reasons: list[str] = []
    for v in verdicts:
        if v.outcome in (Outcome.FAIL, Outcome.CANNOT_DECIDE) and not v.provenance:
            reasons.append(f"{v.gate_id}: {v.outcome.value} with no evidence/provenance")
    return (len(reasons) == 0, reasons)

import argparse
import subprocess
import os
import re
from pathlib import Path

def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("verify", help="deterministic CI / Keel integration")
    parser.add_argument("--profile", required=True, help="Profile JSON to use")
    parser.add_argument("--tier", choices=["commit", "nightly", "release"], default="commit")
    parser.add_argument("--concurrency", type=int, default=0)
    parser.add_argument("--self-test", action="store_true", help="Run the known-bad corpus self-qualification")
    parser.set_defaults(func=verify_command)

def verify_command(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parent
    keel_run = root / "lgwks_verify" / "keel" / "src" / "run.mjs"
    
    if getattr(args, "self_test", False):
        qualify_run = root / "lgwks_verify" / "keel" / "src" / "qualify.mjs"
        return subprocess.run(["node", str(qualify_run)]).returncode

    # Tier authority: nightly/release compose the commit floor with the vendored Keel tier
    # runners (#241) over the tailored evidence (#311). scripts/ci/run.mjs is the single tier
    # authority — it seals a real verdict (GO / NO-GO / BLOCKED-on-missing-evidence). Delegate to
    # it rather than asserting a verdict here, so the verb cannot drift from the runner's truth.
    tier = getattr(args, "tier", "commit")
    if tier != "commit":
        ci_run = root / "scripts" / "ci" / "run.mjs"
        return subprocess.run(["node", str(ci_run), "--tier", tier]).returncode

    profile_path = Path(args.profile)
    if not profile_path.is_file():
        print(f"error: profile not found: {args.profile}", file=__import__('sys').stderr)
        return 2

    cmd = ["node", str(keel_run), "--profile", args.profile]
    if getattr(args, "concurrency", 0) > 0:
        cmd.extend(["--concurrency", str(args.concurrency)])

    is_machine = os.environ.get("LGWKS_MACHINE") == "1"

    res = subprocess.run(cmd, capture_output=is_machine, text=True)

    if not is_machine:
        return res.returncode

    # If --machine, parse output and construct JSON
    chain_file = root / ".keel" / "_chain.jsonl"
    run_id = None
    if chain_file.exists():
        with open(chain_file, "r") as f:
            lines = f.read().splitlines()
            if lines:
                try:
                    last_entry = json.loads(lines[-1])
                    run_id = last_entry.get("run")
                except json.JSONDecodeError:
                    pass

    if run_id:
        proj_ai_file = root / ".keel" / f"projection-ai-{run_id}.json"
        if proj_ai_file.exists():
            with open(proj_ai_file, "r") as f:
                data = json.load(f)
            
            # Extract crossing from stdout
            crossing = {"points": 0, "failed": 0, "unknown": 0}
            crossing_match = re.search(r"crossing: (\d+) structural point.*?\((\d+) failed, (\d+) unknown\)", res.stdout)
            if crossing_match:
                crossing["points"] = int(crossing_match.group(1))
                crossing["failed"] = int(crossing_match.group(2))
                crossing["unknown"] = int(crossing_match.group(3))
            
            advisories = []
            if "⚠ ADVISORY" in res.stdout:
                adv_lines = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith("·")]
                advisories = adv_lines

            data["coverage"] = "unknown"
            data["crossing"] = crossing
            data["advisories"] = advisories
            
            print(json.dumps(data, indent=2))
        else:
            print(json.dumps({"error": f"No projection found for run {run_id}"}))
            
    return res.returncode
