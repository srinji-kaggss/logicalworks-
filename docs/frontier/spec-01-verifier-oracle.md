# SPEC-01 — The Verifier Oracle + the Comprehension Gate

> The one new primitive. Everything else is a Verifier. Read MAP.md, then spec-00.
> Audience: Kimi build agents. This file is normative — types and verdicts are the contract.

## L0 — Intent

One typed interface that all gates implement, so the Coherence Engine (spec-00), the existing
gate bugs (#29), and the new **Intention × Understanding** check are *the same shape*: a thing
that inspects a subject and returns an honest verdict — including "I cannot decide," which is
distinct from "this is bad." The #29 disease was a missing `CANNOT_DECIDE`; the model's failure
got laundered into a verdict against the human. This primitive makes that unrepresentable.

## L2 — The types (implement exactly)

```python
# lgwks_verify.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

class Outcome(Enum):
    PASS = "pass"                 # subject satisfies the gate
    FAIL = "fail"                 # subject violates the gate (HARD → reject+retry)
    CANNOT_DECIDE = "cannot_decide"  # the gate's model abstains; NEVER silently treated as PASS or FAIL
                                  # //why: this is the #29 fix encoded in the type system

class Klass(Enum):
    HARD = "hard"                 # 100% or reject. ship() unreachable unless PASS.
    ADVISORY = "advisory"         # calibrated score, never blocks; produces a report

@dataclass(frozen=True)
class Verdict:
    gate_id: str
    outcome: Outcome
    klass: Klass
    score: float | None           # ADVISORY: calibrated 0..1; HARD: None
    evidence: list[str]           # cited, append-only-loggable; never a stack trace or schema dump
    diagnosis: str | None = None  # on CANNOT_DECIDE/FAIL: what is missing / why — for self-routing, not blame

class Verifier(Protocol):
    gate_id: str
    klass: Klass
    def check(self, subject: object, context: object) -> Verdict: ...
```

### Soundness discipline (the law)

- A `HARD` gate gates `ship()`: ship is reachable **only** if every HARD verifier returns `PASS`.
- `CANNOT_DECIDE` from a HARD gate **blocks ship and surfaces** (orchestrator/human), never passes.
  It is the model saying "out of my competence" — the opposite of guessing. (Directly fixes #29.)
- `ADVISORY` verifiers never block; they accumulate into a calibrated report (target ECE < 0.1).
- Every `Verdict` is appended to the cognition-log (`lgwks_cognition.py`) → full audit (who/what/gate/outcome).
- **Sound, not complete:** the engine guarantees "never ships wrong," not "always ships." A subject no
  HARD gate can pass simply does not ship; the agent is told precisely which gate and why (`diagnosis`).

## The gate registry + pipeline

```python
@dataclass
class GateRegistry:
    hard: list[Verifier] = field(default_factory=list)
    advisory: list[Verifier] = field(default_factory=list)

def run_pipeline(subject, context, reg: GateRegistry) -> tuple[bool, list[Verdict]]:
    verdicts = []
    for g in reg.hard:                     # short-circuit: first non-PASS stops, drives retry/surface
        v = g.check(subject, context); verdicts.append(v)
        if v.outcome is not Outcome.PASS:
            return (False, verdicts)       # //why: no point scoring idiom on code that won't compile
    for g in reg.advisory:                 # advisory always runs, accumulates
        verdicts.append(g.check(subject, context))
    return (True, verdicts)
```

## The Comprehension Gate — Intention × Understanding (`lgwks comprehend`)

The anti-drift mechanism. **Before an agent implements a build unit, it must emit a comprehension
artifact and pass this gate.** The gate forces token-spend on understanding so drift cannot occur
downstream. It is just another `Verifier` whose `subject` is the agent's plan and `context` is the
unit spec (spec-03).

```python
# lgwks_comprehend.py — Verifier(klass=HARD, gate_id="comprehension")
@dataclass(frozen=True)
class ComprehensionArtifact:        # the agent MUST produce this before coding
    unit_id: str
    restated_intent: str            # the unit's L0 in the agent's own words
    steps: list[str]                # ordered, concrete, file-level plan
    invariants: list[str]           # what must hold (from the unit's L4)
    gates: list[str]                # which Verifiers the output must pass
    files_touched: list[str]        # declared write surface
    out_of_scope: list[str]         # what it will deliberately NOT do (scope-creep guard, T1)
```

**Deterministic checks (HARD — coverage, not vibes):**
1. Every acceptance criterion in the unit spec is addressed by ≥1 `step`. Missing → `FAIL` + `diagnosis` lists the uncovered criteria.
2. Every `files_touched` entry matches the unit's declared file targets (no undeclared write surface). Extra/missing → `FAIL`.
3. `invariants` ⊇ the unit's L4 invariants; `gates` ⊇ the unit's required gates. Missing → `FAIL`.
4. `out_of_scope` is non-empty (the agent has thought about the boundary). Empty → `CANNOT_DECIDE` (push to think).
5. `restated_intent` is non-trivial (not a copy of L0 verbatim; semantic overlap, not string identity).

**PASS → the agent may implement. FAIL → bounce with `diagnosis`; the agent revises the artifact.**
This is `refine` (classify·gap·specificity·abstain) applied to the *implementer's plan* instead of the
user's prompt — the same membrane, pointed inward. It cannot be satisfied without genuine thinking,
which is the point: tokens spent here are tokens not lost to rework (the depth-is-the-economy mantra).

## L4 — Invariants + evidence

- `ship` unreachable with any HARD `FAIL`/`CANNOT_DECIDE`. (test: inject a hallucinated-API candidate → G3 FAIL → no ship.)
- `comprehend` rejects a plan that omits any acceptance criterion. (test: plan missing criterion #2 → FAIL, diagnosis names #2.)
- A gate whose model errors returns `CANNOT_DECIDE`, never a silent `PASS`. (test: feed empty/garbage → CANNOT_DECIDE.)
- Every Verdict round-trips to the cognition-log and replays deterministically.

## L5 — Industry parallel

Type-state + refinement types (make illegal states unrepresentable); the `CANNOT_DECIDE` third value
is the abstention discipline of well-calibrated classifiers and of conformal prediction (predict a set,
or abstain, never a confident wrong point). Comprehension-before-action mirrors design-doc/RFC gates and
TLA+ "write the spec before the code" — here made a machine-checked precondition, not a culture norm.

## File targets

- `lgwks_verify.py` — types above + `GateRegistry` + `run_pipeline`.
- `lgwks_comprehend.py` — `ComprehensionArtifact` + the comprehension Verifier + `lgwks comprehend` CLI.
- `tests/test_verify.py`, `tests/test_comprehend.py` — the L4 tests.
