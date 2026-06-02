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
- **Advisory invariant (enforce in `__post_init__`):** `klass == ADVISORY ⟹ outcome ∈ {PASS, CANNOT_DECIDE}`;
  an advisory `FAIL` is unrepresentable. An advisory `CANNOT_DECIDE` (e.g. the idiom embedder failed) is
  **excluded from any score aggregation and surfaced separately** — never averaged as 0. (Closes the leak
  where an advisory gate's CANNOT_DECIDE silently lands in the report as a score.)
- `ADVISORY` verifiers never block; they accumulate into a report (scores only where the gate produced one).
- **Per-HARD-gate soundness obligation:** every HARD verifier must state its **false-PASS surface** and either
  prove it empty or **downgrade to ADVISORY**. A static scan with unbounded false negatives (e.g. "no global
  mutable state" via AST) cannot be HARD — see `arch-rules.json`, where each rule's `klass` is declared in data,
  not chosen at runtime. **Only G0 (compiler/formal) is provably sound today**; G1/G3 must declare their gaps.
- `run_pipeline` is **fail-fast** on HARD (first non-PASS returns) → diagnosis is single-gate by design; an
  agent fixes one HARD gate then re-runs for the next. Accepted tradeoff (still never ships wrong).
- Every `Verdict` is appended to the cognition-log (`lgwks_cognition.py`) → full audit (who/what/gate/outcome).
- **Sound, not complete:** guarantees "never ships wrong" **for gates with a real oracle**, not "always ships."
  A subject no HARD gate can pass simply does not ship; the agent is told which gate and why (`diagnosis`).

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

**The gate's input is `units.json`, NOT prose markdown** — every check is a deterministic coverage/subset
test over that file's arrays. No semantic-similarity heuristic exists in this gate (that would be the
unfalsifiable "vibe" the thesis condemns). The four checks:
1. **Coverage:** every `acceptance[]` entry for the unit is addressed by ≥1 `step`. The mapping must be
   explicit — each step declares `covers: ["<verbatim acceptance id/text>"]`; an uncovered criterion →
   `FAIL`, `diagnosis` lists it. (Not fuzzy text-match — a declared, checkable mapping.)
2. **Write surface:** `files_touched ⊆ unit.file_targets`. Any extra → `FAIL`.
3. **Subset:** `invariants ⊇ unit.invariants` and `gates ⊇ unit.gates`. Any missing → `FAIL`.
4. **Scope boundary:** `out_of_scope` is non-empty AND every entry ∈ `units.json.out_of_scope_vocab`
   (a controlled vocabulary). Empty, or a free-text token like "nothing" → `CANNOT_DECIDE` (push to think).

(Removed: the former "restated_intent semantic-overlap" check — it had no oracle and was gameable by
reordering words. `restated_intent` is still required in the artifact for the human/orchestrator to read,
but it is **not** gate-scored. We do not gate on vibes.)

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
