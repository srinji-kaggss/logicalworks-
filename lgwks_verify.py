"""
lgwks_verify — the Verifier oracle (spec-01).

One typed interface every gate implements, with an honest CANNOT_DECIDE third verdict.
The #29 fix encoded in the type system: a model's failure can never be laundered
into a verdict against the human.
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


@dataclass(frozen=True)
class Verdict:
    gate_id: str
    outcome: Outcome
    klass: Klass
    score: float | None = None           # ADVISORY: calibrated 0..1; HARD: None
    evidence: list[str] = field(default_factory=list)   # cited, append-only-loggable
    diagnosis: str | None = None         # on CANNOT_DECIDE/FAIL: what is missing / why

    def __post_init__(self) -> None:
        # Advisory invariant: klass == ADVISORY ⟹ outcome ∈ {PASS, CANNOT_DECIDE}
        # //why: an advisory FAIL is unrepresentable; advisory CANNOT_DECIDE is excluded from score aggregation
        if self.klass is Klass.ADVISORY and self.outcome is Outcome.FAIL:
            raise ValueError("ADVISORY verdict cannot have outcome FAIL")

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation for the cognition-log."""
        return {
            "gate_id": self.gate_id,
            "outcome": self.outcome.value,
            "klass": self.klass.value,
            "score": self.score,
            "evidence": self.evidence,
            "diagnosis": self.diagnosis,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Verdict":
        return cls(
            gate_id=d["gate_id"],
            outcome=Outcome(d["outcome"]),
            klass=Klass(d["klass"]),
            score=d.get("score"),
            evidence=list(d.get("evidence", [])),
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
