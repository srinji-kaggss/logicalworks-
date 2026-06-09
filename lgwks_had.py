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


if __name__ == "__main__":
    import json
    import sys
    text = " ".join(sys.argv[1:]) or "show me the tool manifest"
    print(json.dumps(decode(text).to_dict(), indent=2))
