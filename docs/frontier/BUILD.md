# BUILD — End-to-End Entry Point

> **You are an implementing agent (Kimi / lower agent). This folder is self-contained.**
> Goal: read this folder → implement each build unit → commit each → stop. Nothing else is required
> of the human. If anything here is ambiguous or contradicts the code you find, STOP and report —
> do not guess (grounding > helpfulness).

## 1. Read order (do not skip)

1. `MAP.md` — the program, the axis, the index.
2. `spec-00-coherence-engine.md` — the gates G0–G4 (what you're building toward).
3. `spec-01-verifier-oracle.md` — the Verifier types + the Comprehension Gate (NORMATIVE — copy the types exactly).
4. `spec-02-three-models.md` — context for *why* (research track; you are NOT training models).
5. `spec-03-build-units.md` — the units U1–U7 you implement, in dependency order.
6. `spec-04-claude-cli-division.md` — context for the end-state.

## 2. The loop — for EACH unit U1…U7, in order

```
┌─ (a) COMPREHEND  — prove you understand BEFORE you code
│      Produce a ComprehensionArtifact (spec-01) for the unit as JSON:
│        { unit_id, restated_intent, steps[], invariants[], gates[], files_touched[], out_of_scope[] }
│      The unit's contract is `units.json` (authoritative). Each step declares `covers: [...]` mapping
│      it to the acceptance[] entries it satisfies — the gate checks coverage against that mapping, not
│      by fuzzy text-match.
│      • restated_intent: the unit's intent in YOUR OWN words (kept for the human; NOT gate-scored).
│      • steps: concrete, file-level; together their `covers` must hit EVERY acceptance[] entry in units.json.
│      • invariants ⊇ units.json unit.invariants; gates ⊇ units.json unit.gates.
│      • files_touched ⊆ units.json unit.file_targets (no undeclared writes).
│      • out_of_scope: non-empty AND every entry drawn from units.json.out_of_scope_vocab (a controlled
│        vocabulary — "nothing"/free text fails the gate as CANNOT_DECIDE).
│      GATE: once U2 exists → `lgwks comprehend --unit <id> --file plan.json` must return PASS.
│            Before U2 exists (U1 only) → self-check the artifact against units.json
│            and write it to `scratch/comprehension/<unit>.json` as your committed evidence of thinking.
│      If the gate/your-check fails: REVISE the artifact. Do not start coding on a failing plan.
│      //why this step exists: tokens spent understanding now prevent architectural drift later. This
│      is the anti-drift mechanism — Intention × Understanding. It is mandatory, not optional ceremony.
│
├─ (b) IMPLEMENT  — write the code per the artifact's steps, nothing beyond files_touched.
│      Doctrine (T4): typed errors (no silent `except: pass`); `//why` at every non-obvious decision;
│      no shims/dead code; functions do one thing; comments say why. Match surrounding code's style.
│
├─ (c) VERIFY  — run the unit's tests + the whole suite:
│        python3 -m unittest discover tests
│      All green, including the unit's new L4 tests. If red: fix the code, never the test or the gate
│      (no gate weakening — #29). Reproduce → fix → verify → confirm no regression.
│
└─ (d) COMMIT  — one commit per unit (see §3). Then move to the next unit.
```

## 3. Commit rules

- One commit per unit. Message = the unit's stated `Commit:` line.
- Body: what changed · which acceptance criteria are met · the test command + result (evidence) · which
  issue it closes (U3 → `Closes #29`).
- End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Pre-commit invariants (HARD — verify, do not assume):
  - `git rev-parse --show-toplevel` is THIS worktree; `git branch --show-current` is the feature branch.
  - Working tree has no unrelated changes; suite is green.
  - No secrets/credentials/.env staged. No files written outside `files_touched` + `tests/`.
- Do **not** push or open a PR unless the human asks. Commit only. Do **not** merge or rebase.

## 4. Stop conditions (report to the human, do not improvise)

- A unit's acceptance criteria cannot be met without touching files outside its declared targets.
- A spec contradicts the actual code you find (e.g. a referenced symbol/module is absent).
- A test cannot be made green without weakening a gate or a threshold.
- A comprehension artifact keeps failing the gate (you cannot form a covering plan) → the unit spec has a gap.
- Anything requiring model *training* (research track, spec-03 §out-of-scope) → scope-creep, bounce.

## 5. What "done" means

U1–U7 implemented, each committed, full suite green, `#29` closed by U3, `scratch/comprehension/*.json`
present as evidence the comprehension gate was honored for every unit. The Coherence Engine
(`lgwks cohere`) runs end-to-end: a hallucinated-API candidate is blocked; a conformant candidate ships
with an advisory report and an audit trail in the cognition-log.
