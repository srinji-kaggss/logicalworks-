"""lgwks_had — Human Assumption Decoder (consultant semantic-escalation-harness, intent math).

Decodes a Director utterance into a typed machine intent PLUS an explicit ledger of the
hidden assumptions the decode rests on — each with a posterior probability, counter-
hypotheses, the risk if it is wrong, and a status that can ABSTAIN to human review.

//why this is the structural cure for the operating-loop defect: the failure shape is
"infer an assumption, treat it as fact, act, narrate over the hole." The HAD makes every
inferred assumption an explicit, scored, falsifiable record — and refuses to mark it
`accepted` when the posterior is low or the action is risky. It cannot silently assume.

The math (consultant 03_human_assumption_decoder.yaml, RSA / Bayesian pragmatics):
  P(intent | utterance) ∝ P(utterance | intent) · P(intent)
The pragmatic-listener distribution is approximated TODAY by the L1 intent classifier's
top-k similarity distribution (softmax over verb similarities) — L1's semantic match IS the
literal-listener signal. The trained RSA speaker model is the upgrade (SCIENCE.md), not this.
Deterministic given the classifier output; no generation (INV-3).

Output conforms to the consultant event schemas (05_event_schemas.json):
TypedIntentIR + AssumptionLedgerEntry.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# //why a heuristic risk lexicon, not a model: irreversibility is a property of the verb,
# knowable without inference. Destructive/outward verbs gate to human review regardless of
# how confident the classifier is — high confidence in a dangerous action is MORE reason to
# confirm, not less (T0). Pending a learned risk head (SCIENCE.md).
_RISK_LEXICON: dict[str, str] = {
    "delete": "high", "remove": "high", "drop": "high", "destroy": "critical",
    "deploy": "high", "ship": "high", "push": "high", "merge": "high", "force": "critical",
    "publish": "high", "send": "high", "pay": "critical", "transfer": "critical",
    # destructive/irreversible synonyms — expanded so the assumption-gate's high-risk
    # escalation covers the common verbs, not just the original short list (#143 review).
    "wipe": "critical", "purge": "high", "truncate": "high", "erase": "high",
    "revoke": "high", "reset": "high", "overwrite": "high", "rm": "high", "kill": "high",
    "uninstall": "high", "format": "critical", "withdraw": "critical", "refund": "high",
    "write": "medium", "edit": "medium", "update": "medium", "create": "medium", "run": "medium",
    "crawl": "low", "show": "low", "list": "low", "search": "low", "read": "low",
    "manifest": "low", "review": "low", "map": "low", "doctor": "low", "status": "low",
}
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Acceptance thresholds (consultant D5). HEURISTIC pending labeled calibration (SCIENCE §7).
_TAU = 0.45          # posterior floor to accept an assumption without review
_MARGIN_MIN = 0.02   # top1−top2 separation floor (shared rationale with L1)


@dataclass
class AssumptionLedgerEntry:
    """One inferred assumption, scored and falsifiable. Schema: AssumptionLedgerEntry."""
    assumption_id: str
    candidate_hidden_assumption: str
    posterior_probability: float
    status: str                                   # proposed|tentative|accepted_for_low_risk_execution|confirmed_by_user|rejected|human_review
    utterance_span: Optional[str] = None
    literal_interpretation: Optional[str] = None
    counter_hypotheses: list[str] = field(default_factory=list)
    risk_if_wrong: str = "low"
    evidence_refs: list[str] = field(default_factory=list)
    resolved_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "utterance_span": self.utterance_span,
            "literal_interpretation": self.literal_interpretation,
            "candidate_hidden_assumption": self.candidate_hidden_assumption,
            "posterior_probability": round(self.posterior_probability, 4),
            "counter_hypotheses": self.counter_hypotheses,
            "risk_if_wrong": self.risk_if_wrong,
            "status": self.status,
            "resolved_by": self.resolved_by,
            "evidence_refs": self.evidence_refs,
        }


@dataclass
class TypedIntentIR:
    """The decoded intent. Schema: TypedIntentIR."""
    request_id: str
    operation: str
    risk: str
    domain: Optional[str] = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    soft_constraints: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    assumption_ledger: list[AssumptionLedgerEntry] = field(default_factory=list)
    routing: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    def needs_human(self) -> bool:
        # //why: any unresolved high-risk or low-posterior assumption blocks autonomous
        # execution — the abstention gate. routing.execute reflects this.
        return any(a.status == "human_review" for a in self.assumption_ledger) \
            or not self.routing.get("execute", False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "lgwks.had.intent.v1",
            "request_id": self.request_id,
            "operation": self.operation,
            "domain": self.domain,
            "entities": self.entities,
            "hard_constraints": self.hard_constraints,
            "soft_constraints": self.soft_constraints,
            "unknowns": self.unknowns,
            "assumption_ledger": [a.to_dict() for a in self.assumption_ledger],
            "risk": self.risk,
            "routing": self.routing,
            "audit": self.audit,
        }


def _request_id(utterance: str) -> str:
    return "req-" + hashlib.sha256(utterance.encode("utf-8")).hexdigest()[:12]


def _softmax(xs: list[float], *, temp: float = 0.05) -> list[float]:
    # //why a low temperature: the Eye compresses cosines into a narrow band (~0.68–0.83);
    # a low temp sharpens that band into a usable distribution so the top intent's posterior
    # is meaningful rather than near-uniform across 175 verbs.
    if not xs:
        return []
    scaled = [x / temp for x in xs]
    m = max(scaled)
    exps = [math.exp(s - m) for s in scaled]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def _risk_of(operation: str) -> str:
    toks = set(re.findall(r"[a-z]+", operation.lower()))
    risks = [_RISK_LEXICON[t] for t in toks if t in _RISK_LEXICON]
    if not risks:
        return "medium"  # //why default medium: an unrecognized verb is not assumed safe.
    return max(risks, key=lambda r: _RISK_ORDER[r])


def decode(utterance: str, *, classify_fn: Optional[Callable[[str], Any]] = None,
           context: Optional[dict[str, Any]] = None) -> TypedIntentIR:
    """Decode an utterance into a TypedIntentIR with a scored assumption ledger.

    classify_fn(text) -> object with .label, .top_k (list[(label, score)]), .plan_only,
    .margin. Defaults to the L1 intent classifier. Injectable for deterministic tests."""
    utterance = (utterance or "").strip()
    rid = _request_id(utterance)
    if not utterance:
        return TypedIntentIR(request_id=rid, operation="", risk="low",
                             routing={"execute": False, "reason": "empty utterance"},
                             audit={"decoder": "had.v1"})

    if classify_fn is None:
        import lgwks_intent_classifier as ic
        clf = ic.IntentClassifier.load()
        classify_fn = clf.classify
    assert classify_fn is not None  # narrowed: set above or supplied by caller

    result = classify_fn(utterance)
    operation = getattr(result, "label", "") or ""
    top_k = list(getattr(result, "top_k", []) or [])
    margin = float(getattr(result, "margin", 0.0) or 0.0)
    plan_only = bool(getattr(result, "plan_only", True))

    # RSA-style posterior over the operation: softmax of the top-k similarity distribution.
    sims = [s for _lbl, s in top_k] or [getattr(result, "confidence", 0.0)]
    posteriors = _softmax(sims)
    op_posterior = posteriors[0] if posteriors else 0.0
    counter = [lbl for lbl, _s in top_k[1:4]]

    risk = _risk_of(operation)
    # Status ladder (consultant D5 abstention). //why plan_only/low-margin → review first:
    # L1 already abstained on this utterance; the decoder must not silently upgrade an
    # abstention into an action. Only a confident, well-separated, low-risk reading executes.
    if not operation:
        status = "human_review"
    elif plan_only or margin < _MARGIN_MIN:
        status = "human_review"
    elif op_posterior >= _TAU and _RISK_ORDER[risk] <= _RISK_ORDER["medium"]:
        status = "accepted_for_low_risk_execution"
    elif op_posterior >= _TAU:
        status = "human_review"            # confident but risky → confirm (T0)
    else:
        status = "tentative" if op_posterior >= _TAU / 2 else "human_review"

    primary = AssumptionLedgerEntry(
        assumption_id=f"{rid}-op",
        candidate_hidden_assumption=f"the intent maps to lgwks operation '{operation}'",
        posterior_probability=op_posterior,
        status=status,
        utterance_span=utterance[:120],
        literal_interpretation=utterance,
        counter_hypotheses=counter,
        risk_if_wrong=risk,
        evidence_refs=[f"L1:margin={round(margin, 4)}", f"L1:plan_only={plan_only}"],
    )

    execute = (status == "accepted_for_low_risk_execution")
    return TypedIntentIR(
        request_id=rid,
        operation=operation,
        risk=risk,
        entities=[],
        unknowns=[] if operation else ["operation"],
        assumption_ledger=[primary],
        routing={"execute": execute, "target": operation if execute else None,
                 "reason": status},
        audit={"decoder": "had.v1", "posterior": round(op_posterior, 4),
               "margin": round(margin, 4), "plan_only": plan_only},
    )


# ── Unified abstention gate (#143) ─────────────────────────────────────────────
# //why this lives in HAD: the Director's session-15 ruling — injection detection is
# NOT a separate system, it is ONE MORE SIGNAL feeding HAD's abstention gate. One gate
# covers all four threat classes: malicious injection (attacker) · accidental self-
# injection (the human's own ambiguity harms the human) · weird input · fraud/anomaly.
# Each is a scored RiskSignal; the gate composes them into one verdict + one receipt.
#
# Composition is DETERMINISTIC and calculator-derivable (feedback_calculator_test):
#   composed_risk = max over signals of clamp01(weight · score)
# max-dominant = defense-in-depth: ANY one signal can flag (the Director: "either layer
# can flag"). Weights attenuate a noisier signal without letting it veto a confident one.
# Thresholds are SHARED with the injection sensor (single source of truth) so the verdict
# is identical when injection is the only live signal — exact back-compat regression.

from dataclasses import dataclass as _dataclass


@_dataclass
class RiskSignal:
    """One scored input to the abstention gate. `score`∈[0,1] is the evidence; `weight`
    attenuates a less-trusted source; `signals` are the human-readable tells that fired."""
    name: str
    score: float
    weight: float = 1.0
    signals: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def contribution(self) -> float:
        s = self.score if isinstance(self.score, (int, float)) and math.isfinite(self.score) else 0.0
        w = self.weight if isinstance(self.weight, (int, float)) and math.isfinite(self.weight) else 0.0
        return max(0.0, min(1.0, w * s))


# Named signal weights — all 1.0 (no magic attenuation; calculator-trivial). The
# differing AUTHORITY of each signal is expressed as a CAP on its score, not as a fudged
# weight: injection can reach BLOCK (a matched attack); assumption + anomaly are capped at
# CONFIRM — they are EVIDENCE FOR A HUMAN GATE, not grounds for an autonomous block
# (lgwks_algorithms doctrine: "a high anomaly score is evidence for a human/LLM gate, not
# an action"; and the human's own ambiguity is not an attack).
_W_INJECTION = 1.0
_W_ASSUMPTION = 1.0
_W_ANOMALY = 1.0

# Self-defense bound for the gate's public entry (matches the engine's INV-7 cap so
# detection over a pathological prompt can't blow latency regardless of caller).
_MAX_GATE_CHARS = 16_000


def _ladder() -> tuple[float, float, float]:
    """Verdict thresholds — imported from the injection sensor so there is ONE source of
    truth for the ladder. Falls back to HAD-local values if jailbreak is unavailable."""
    try:
        import lgwks_jailbreak as jb
        return jb._T_BLOCK, jb._T_CONFIRM, jb._T_ATTENUATE
    except Exception:
        return 0.80, 0.45, 0.20


def compose_verdict(signals: list) -> tuple[str, float]:
    """Composed risk + verdict over a list of RiskSignal. Deterministic, no model."""
    t_block, t_confirm, t_attenuate = _ladder()
    composed = round(max((s.contribution() for s in signals), default=0.0), 3)
    if composed >= t_block:
        verdict = "block"
    elif composed >= t_confirm:
        verdict = "confirm"
    elif composed >= t_attenuate:
        verdict = "attenuate"
    else:
        verdict = "proceed"
    return verdict, composed


def _injection_signal(prompt: str) -> RiskSignal:
    """Injection sensor as a pure signal provider (verdict authority now lives in the
    composed gate). The ML head plugs into lgwks_jailbreak._ml_injection_score unchanged."""
    try:
        import lgwks_jailbreak as jb
        r = jb.injection_risk(prompt)
        return RiskSignal("injection_risk", float(r.get("score", 0.0)), _W_INJECTION,
                          list(r.get("signals", [])), {"mode": r.get("mode")})
    except Exception:
        return RiskSignal("injection_risk", 0.0, _W_INJECTION)


def _assumption_signal(prompt: str, *, classify_fn=None) -> Optional[RiskSignal]:
    """Accidental-self-injection / ambiguity defense: HAD decodes the intent and scores
    the assumption it rests on. Low-confidence or risky decode → the gate ABSTAINS.

    Capped at the CONFIRM band (never BLOCK): the human's own ambiguity is not an attack —
    it escalates to confirmation, it does not get silently killed. Returns None (signal
    absent, graceful) when the classifier is unavailable/errors or LGWKS_NO_MODELS is set
    — never blocks the conscious channel (INV-6)."""
    import os
    if classify_fn is None and os.environ.get("LGWKS_NO_MODELS"):
        return None
    try:
        ir = decode(prompt, classify_fn=classify_fn)
    except Exception:
        return None
    _t_block, t_confirm, _t_attenuate = _ladder()
    status = ir.assumption_ledger[0].status if ir.assumption_ledger else "human_review"
    # //why CONSERVATIVE: this rides the engine's hot path on every request, so it must
    # NOT manufacture friction on ordinary work (INV-6 — never block the conscious
    # channel). It elevates ONLY when HAD abstains on a HIGH/CRITICAL-risk operation —
    # i.e. we INFERRED a destructive/irreversible action rather than being told it
    # plainly. That is the accidental-self-injection danger that matters
    # (irreversible-vs-purchasable doctrine): act on a wrong high-risk inference. Capped
    # at CONFIRM (never BLOCK) — the human's own ambiguity escalates, it is not an attack.
    # Ambiguity on low/medium ops is left to proceed; lowering this bar is a calibration
    # packet pending labelled data (mirrors the _TAU heuristic note).
    abstains = status not in ("accepted_for_low_risk_execution",)
    high_risk = _RISK_ORDER.get(ir.risk, 0) >= _RISK_ORDER["high"]
    score = t_confirm if (abstains and high_risk and ir.operation) else 0.0
    return RiskSignal("assumption_risk", score, _W_ASSUMPTION,
                      [f"decode:{status}:{ir.risk}"] if score > 0.0 else [],
                      {"posterior": ir.audit.get("posterior"), "risk_if_wrong": ir.risk})


def _anomaly_signal(series: Optional[list]) -> RiskSignal:
    """Fraud/anomaly/drift defense (z-score). SEAM: needs a per-request history series,
    which has no live source yet — so this contributes 0.0 (available-but-unfed) until the
    daemon event store is queryable at gate time. Wiring the feed is the only change later."""
    if not series:
        return RiskSignal("anomaly_score", 0.0, _W_ANOMALY, [], {"fed": False})
    try:
        import lgwks_algorithms as alg
        v = alg.rolling_z_score(series)  # v.score is an ABS robust z (two-sided magnitude)
        # Map z (unbounded) to [0,1] via the detector's own threshold: z at/above the
        # threshold saturates to 1.0. Then CAP at CONFIRM — an anomaly is evidence for a
        # human gate, never an autonomous block (see weight note above). So the worst an
        # anomaly spike does on its own is escalate to confirmation.
        _t_block, t_confirm, _t_attenuate = _ladder()
        norm = max(0.0, min(1.0, v.score / (v.threshold or 3.0)))
        score = round(min(norm, t_confirm), 3)
        return RiskSignal("anomaly_score", score, _W_ANOMALY,
                          ["anomaly_spike"] if v.flag else [], {"z": v.score, "fed": True})
    except Exception:
        return RiskSignal("anomaly_score", 0.0, _W_ANOMALY, [], {"fed": False})


def _unified_receipt(verdict: str, components: list) -> str:
    """System-generated (templated, NOT LLM) transparency receipt over all fired signals.
    Names the dominant signal so the human sees WHICH danger was caught."""
    if verdict == "proceed":
        return ""
    fired = [s for c in components for s in c.signals]
    dominant = max(components, key=lambda c: c.contribution(), default=None)
    tells = ", ".join(fired) if fired else "elevated risk"
    dom = dominant.name if dominant else "risk"
    if verdict == "block":
        return f"Held: input matched attack signals [{tells}] — not run. (system)"
    if verdict == "confirm":
        if dom == "assumption_risk":
            return (f"Your request was ambiguous or high-risk to decode [{tells}] — "
                    f"confirming the intent before any action. (system)")
        return f"Flagged [{tells}] — needs your confirmation before any action. (system)"
    return f"Noticed [{tells}] — sanitized the input and proceeded with reduced trust. (system)"


def assess(prompt: str, *, classify_fn=None, assume: bool = False,
           series: Optional[list] = None) -> dict:
    """The unified abstention decision over ALL risk signals (#143).

    Supersedes the injection-only lgwks_jailbreak.assess as the gate the U6 engine calls.
    Composes injection (attacker) · assumption (accidental self-injection / ambiguity) ·
    anomaly (fraud/drift, seam) into one verdict on the shared ladder. Deterministic.

    The assumption signal runs ONLY when a classifier is supplied (`classify_fn`) or
    explicitly enabled (`assume=True`). //why gated: decoding intent cold-loads the
    IntentClassifier (~seconds), which would blow the engine's <1s hot-path budget
    (INV-7) on EVERY request. The warm path (a daemon holding a loaded classifier, or a
    shared embed-port head) flips `assume=True`; the synchronous engine default leaves it
    off and composes injection + anomaly only — an exact injection-only regression.

    Returns a BACK-COMPAT SUPERSET — keeps every key the engine reads today
    (`verdict`, `injection_risk`, `signals`, `receipt`) plus the composed vector
    (`risk_score`, `components`) and an injection-only view (`injection`)."""
    # Self-defending input cap: the gate must bound attacker-controlled input even when a
    # caller (the warm/daemon path) reaches assess() directly, not only via the engine —
    # signal detection is linear in length, so an uncapped multi-MB prompt is a soft-DoS.
    if isinstance(prompt, str) and len(prompt) > _MAX_GATE_CHARS:
        prompt = prompt[:_MAX_GATE_CHARS]

    inj = _injection_signal(prompt)
    components = [inj]
    if assume or classify_fn is not None:
        asm = _assumption_signal(prompt, classify_fn=classify_fn)
        if asm is not None:
            components.append(asm)
    components.append(_anomaly_signal(series))

    verdict, composed = compose_verdict(components)
    flat_signals = [s for c in components for s in c.signals]
    # Injection-ONLY view (honest legacy surface): verdict/receipt over the injection
    # signal alone, so a consumer keying on "injection" never sees assumption/anomaly tells
    # mislabeled as injection when the other signals are warm.
    inj_verdict, _inj_composed = compose_verdict([inj])
    return {
        "schema": "lgwks.risk.assessment.v1",
        "verdict": verdict,
        "risk_score": composed,
        "injection_risk": inj.score,          # back-compat: engine reads this
        "signals": flat_signals,              # back-compat: engine reads this
        "receipt": _unified_receipt(verdict, components),
        "injection": {                        # injection-only view (not the composed verdict)
            "verdict": inj_verdict,
            "score": inj.score,
            "signals": inj.signals,
            "receipt": _unified_receipt(inj_verdict, [inj]),
        },
        "components": [
            {"name": c.name, "score": round(c.score, 3), "weight": c.weight,
             "contribution": round(c.contribution(), 3), "signals": c.signals,
             "evidence": c.evidence}
            for c in components
        ],
    }


if __name__ == "__main__":
    import json
    import sys
    text = " ".join(sys.argv[1:]) or "show me the tool manifest"
    print(json.dumps(decode(text).to_dict(), indent=2))
