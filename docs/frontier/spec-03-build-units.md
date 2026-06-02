# SPEC-03 — Build Units (the implementation plan)

> THE plan. Deterministic enough for a Kimi/lower agent to implement unit-by-unit.
> Read MAP.md → spec-00 → spec-01 → spec-02 first. Then follow BUILD.md's loop for each unit.
> **Before implementing any unit you MUST pass its Comprehension Gate (spec-01).** No exceptions.

## Conventions (apply to every unit)

- Language: Python 3 (stdlib-first; heavy deps lazy-imported, degrade gracefully — see existing modules).
- Doctrine: typed errors (`Result`-style return or typed exception, never silent `except: pass`);
  `//why` at every non-obvious decision; no shims/dead code; functions do one thing; comments say *why*.
- Tests: `python3 -m unittest discover tests` must stay green after every unit. Each unit adds its own tests.
- No gate weakening (#29 lesson, [[feedback_no_gate_weakening]]): a failing gate means fix the thing under
  test, never loosen the threshold. Weakening requires Director approval + a logged reason.
- One commit per unit (BUILD.md §commit). Working tree must be clean and on the feature branch.

## Dependency graph

```
U1 verify ──┬─► U2 comprehend
            ├─► U3 fix#29 (honest gates)
            ├─► U4 G3 framework-reality ─┐
            ├─► U5 G1 architecture ──────┼─► U7 cohere (pipeline)
            └─► U6 G2 idiom ─────────────┘
research track (NOT this build): model#2 coder training (ml-001, #17, #27)
```

---

## U1 — Verifier oracle (`lgwks_verify.py`)

- **Depends:** none. **Gate-class delivered:** the primitive itself.
- **L0:** one typed interface every gate implements, with an honest `CANNOT_DECIDE` third verdict.
- **L1:** gates today conflate "model failed" with "subject is bad" (#29). The type must make that unrepresentable.
- **L2/L3:** implement `Outcome`, `Klass`, `Verdict`, `Verifier` Protocol, `GateRegistry`, `run_pipeline`
  exactly as in spec-01 §types. HARD short-circuits; ADVISORY accumulates.
- **L4 invariants + evidence:**
  - `run_pipeline` returns `(False, …)` on the first HARD non-PASS. (test)
  - A verifier raising internally is caught and mapped to `CANNOT_DECIDE`, never `PASS`. (test)
  - Every `Verdict` is JSON-serialisable for the cognition-log. (test)
- **Acceptance:** `tests/test_verify.py` covers all three L4 points; suite green.
- **Files:** `lgwks_verify.py`, `tests/test_verify.py`.
- **Commit:** `feat(verify): typed Verifier oracle with honest CANNOT_DECIDE verdict (spec-01)`.

## U2 — Comprehension gate (`lgwks_comprehend.py`, `lgwks comprehend`)

- **Depends:** U1. **Gate-class:** HARD (Intention × Understanding).
- **L0:** force an implementing agent to prove understanding + a correct step plan before it codes.
- **L2/L3:** implement `ComprehensionArtifact` + the comprehension Verifier + CLI per spec-01 §comprehension.
  Input: a unit-spec (parsed from this file's unit blocks) + an artifact (JSON, stdin or `--file`).
- **L4 invariants + evidence:**
  - Plan omitting any acceptance criterion → `FAIL`, `diagnosis` names the uncovered criteria. (test)
  - Undeclared file in `files_touched` → `FAIL`. (test)
  - Empty `out_of_scope` → `CANNOT_DECIDE` (push to think). (test)
  - `restated_intent` == L0 verbatim → `FAIL` (must be in own words; semantic-overlap check). (test)
- **Acceptance:** `lgwks comprehend --unit U4 --file plan.json` returns a Verdict; the four tests pass.
- **Files:** `lgwks_comprehend.py`, `tests/test_comprehend.py`, dispatch wired in `lgwks`.
- **Commit:** `feat(comprehend): Intention×Understanding gate — plan must cover spec before code (spec-01)`.

## U3 — Fix the three gate bugs (#29)

- **Depends:** U1. **Gate-class:** makes existing gates honest.
- **L0:** stop gates trusting a broken/absent model as truth; fail in the right direction.
- **L2/L3 (three sub-fixes):**
  - `lgwks_machine.py:121` — **unbin** classifier-failure from user-vagueness. When `specificity >= threshold`
    but `intent_class == "unknown"`, return a `CANNOT_DECIDE`-style result tagged `classifier_coverage_gap`
    (log as a #27 training signal) and **proceed/pass-through**; do NOT emit a "please specify" question.
    User-vagueness (low specificity) keeps the legitimate abstain. //why: two distinct entities, two paths.
  - `lgwks_public` — add a relevance Verifier: reject results below a topical-similarity floor, OR label the
    output `"ranking": "citation-canon, not relevance"` honestly. No silent canon-as-relevance.
  - `jarvis crawl` — add a source-validity Verifier before ingest: reject CAPTCHA / bot-challenge / empty-result
    / login-wall pages (detect via known markers + content heuristics) → `CANNOT_DECIDE`, do not map into concepts.
- **L4 + evidence:**
  - `refine "Find me machine focused research on how ML to AI training occurs"` does NOT abstain-blaming-human. (test)
  - A CAPTCHA fixture is rejected by crawl's source-validity gate, not ingested. (test)
  - `public` output is either relevance-filtered or honestly labelled. (test)
- **Acceptance:** three regression tests (one per symptom) green; closes #29.
- **Files:** `lgwks_machine.py`, `lgwks_public.py`, `lgwks_search.py`/crawl path, `tests/test_gates_honesty.py`.
- **Commit:** `fix(gates): unbin classifier-failure from user-vagueness; add relevance+source-validity gates (#29)`.

## U4 — G3 Framework-Reality gate (`lgwks_gate_framework.py`)

- **Depends:** U1. **Gate-class:** HARD. Highest leverage — kills API hallucination deterministically.
- **L0:** every external symbol in candidate code must exist in the *installed* version's real surface.
- **L2/L3:** build the installed-symbol set from `cargo metadata` + rustdoc JSON (`cargo rustdoc -- -Zunstable
  -output-format json` or stable equivalent). Verifier parses candidate code's external paths/calls; any symbol
  absent from the set → `FAIL` with `diagnosis` (symbol, nearest real match). No network; ground truth = the lockfile.
- **L4 + evidence:**
  - Candidate calling a non-existent `foo::bar()` → `FAIL`, diagnosis names `foo::bar`. (test, fixture crate)
  - Candidate using only real symbols → `PASS`. (test)
  - Missing rustdoc JSON → `CANNOT_DECIDE` (never silently PASS). (test)
- **Acceptance:** tests against a fixture crate green.
- **Files:** `lgwks_gate_framework.py`, `tests/test_gate_framework.py`, `tests/fixtures/crate/`.
- **Commit:** `feat(gate): G3 framework-reality — verify symbols against installed surface (spec-00)`.

## U5 — G1 Architecture gate (`lgwks_gate_arch.py`)

- **Depends:** U1. **Gate-class:** HARD on the checkable subset; ADVISORY otherwise.
- **L0:** candidate conforms to the system ER graph + ADR invariants (layering, ownership, no-global-state).
- **L2/L3:** rules from a declarative arch spec (`spec/canvas-motion/05` ER model + ADR mandates) compiled to
  checks: forbidden-import edges, ownership/linearity rules, "no global mutable state" (static scan).
  Checkable rule violated → `FAIL`; judgment-level concern → ADVISORY score + note.
- **L4 + evidence:** a fixture importing across a forbidden layer → `FAIL` naming the edge; a conformant fixture → `PASS`. (tests)
- **Acceptance:** layering + global-state tests green.
- **Files:** `lgwks_gate_arch.py`, `arch-rules.json` (declarative), `tests/test_gate_arch.py`.
- **Commit:** `feat(gate): G1 architecture conformance — layering+ownership rules as checks (spec-00)`.

## U6 — G2 Idiom gate (`lgwks_gate_idiom.py`)

- **Depends:** U1. **Gate-class:** ADVISORY (never blocks).
- **L0:** score how well candidate matches *this repo's* conventions; emit an idiom-diff report.
- **L2/L3:** embedding-distance of candidate to the repo corpus (reuse `lgwks_embed.py`) + a project lint profile.
  Returns calibrated `score` + `evidence` (nearest idiomatic exemplars, deviations). Never `FAIL`.
- **L4 + evidence:** ADVISORY verdict always (never blocks ship); calibration ECE < 0.1 on a held-out set. (tests)
- **Acceptance:** advisory-only + calibration tests green.
- **Files:** `lgwks_gate_idiom.py`, `tests/test_gate_idiom.py`.
- **Commit:** `feat(gate): G2 idiom advisory score + idiom-diff report (spec-00)`.

## U7 — Coherence pipeline (`lgwks cohere`)

- **Depends:** U4, U5, U6. **Gate-class:** composes the engine.
- **L0:** run candidate code through G0(rustc/cargo test) → G1 → G3 → G2 via the registry; ship only if all
  HARD PASS; emit the advisory report; append all verdicts to the cognition-log.
- **L2/L3:** register G0 (shell-out to `cargo build`/`test`), U4, U5 as HARD; U6 as ADVISORY; call `run_pipeline`;
  on HARD non-PASS return the `diagnosis` for retry; log every Verdict.
- **L4 + evidence:**
  - Hallucinated-API candidate → blocked at G3, never ships. (test)
  - All-pass candidate → ships, advisory report attached, verdicts in cognition-log. (test)
  - Pipeline is deterministic + replayable from the log. (test)
- **Acceptance:** end-to-end pipeline tests green; `lgwks cohere --file candidate.rs --spec unit.json` works.
- **Files:** `lgwks_cohere.py`, dispatch in `lgwks`, `tests/test_cohere.py`.
- **Commit:** `feat(cohere): Coherence Engine pipeline G0→G1→G3→G2 with cognition-log audit (spec-00)`.

---

## Out of scope for this build (research track — do NOT attempt deterministically)

Model #2 coder *training* (RLVR loop, PyTorch+MPS, CoreML export), model #1 ModernBERT fine-tune, model #3
science-engine harness. These need the platform above first and are gated on ml-001/#17/#27 + Director vetting.
If a unit's comprehension artifact lists any of these in `steps`, that is scope-creep → bounce (T1).
