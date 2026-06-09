# PRD-09 — Review & Nitpick Attenuation

Parent: none directly (new child; doctrine "review is a production-grade gate") · Status: draft v0.1
Absorbs: input YAML `determinism_and_nitpick_attenuation_subsystem` · Replaces: **Greptile
review**, CodeRabbit-class AI reviewers, and the noise tax of generic AI review.

## Problem

AI review tools monetize two things: codebase context (PRD-02 owns that now) and noise
suppression (not drowning the human in nitpicks). A review comment that a linter could have
made is pure waste — it spends reviewer attention and model tokens to restate a rule.
Conversely, AI review that misses semantic defects while flagging style is the skeptic's
best evidence against AI-built software.

## Absorbed from the input YAML — with deviations

| YAML proposal | Verdict | //why |
|---|---|---|
| linter-first routing suppression (if a linter can flag it, it never reaches the LLM prompt) | ADOPT — the core idea | deterministic gate > model judgment (T4 conformance); ESLint/Ruff/clippy run native, their domain is subtracted from review scope |
| few-shot grounding from recent commit history (learn implicit team patterns) | ADOPT, modified | retrieval of real exemplar diffs (non-generative selection, INV-3-compatible); patterns surfaced as *citations to commits*, not generated style claims |
| SonarQube integration | DEFER | heavyweight; ruff/eslint/clippy/tsc cover the floor; add only if a gap is measured |

## Scope

- IN: diff-scoped review pipeline: diff → PRD-02 graph context (callers/consumers of
  changed nodes) → deterministic-gate subtraction (linters+typecheckers run first; their
  findings deduped out) → semantic review focused on what only semantics can catch
  (the three sins, invariant violations, trust-boundary changes).
- IN: doctrine gates as code: existing `lgwks_gate_arch/framework/idiom.py` wired in-path.
- IN: severity discipline: every finding carries `{class, severity, evidence_span,
  fix_confidence}`; nitpick-class findings are suppressed from output entirely when a
  linter rule covers them (logged as suppressed, count visible — no silent cap).
- IN: exemplar retrieval: "this repo does X" claims must cite ≥2 real commits/files.
- OUT: auto-fix (separate consent), generative review prose beyond findings (INV-3 applies
  to the meta-layer; the semantic-review step itself is an Opus/local-LLM call and is the
  ONE sanctioned generative step — clearly labeled, never injected as subconscious signal).

## Builds on (candidates — verify at unit start)

`lgwks_review.py`, `lgwks_project_review.py`, `lgwks_diff.py`, `lgwks_gate_*.py`,
`lgwks_codebase.py`, PRD-02 query surface · prior art: docs/bot-fabric U5-CODE-HACKER.

## Contract

Emits `lgwks.review.v1`: `{diff_ref, findings[], suppressed_count, gates_run[],
exemplars[]}`. Consumer: PRD-07 cockpit (Director-facing); GitHub PR comments via existing
gh tooling when directed.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 09-a gate subtraction | on a fixture diff with 10 planted linter-catchable + 5 semantic defects: all 10 suppressed from LLM scope, ≥4/5 semantic reach review; suppression logged |
| 09-b graph-context review | review prompt contains the changed nodes' dependency closure from PRD-02, within PRD-04 budget; proven by prompt inspection |
| 09-c exemplar grounding | every team-pattern claim in output carries ≥2 commit citations; uncited pattern claims fail the output validator |
| 09-d benchmark | on 20 historical repo diffs with known outcomes: precision/recall vs what review actually caught/missed; beats no-context LLM review baseline (paired, SCIENCE §10) |

## Open questions → SCIENCE.md

Finding-precision measurement protocol (§10); whether local LLM (lgwks_local_llm/ollama)
suffices for semantic review or Opus is required (cost/quality paired eval); auto-fix consent UX.
