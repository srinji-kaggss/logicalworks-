---
type: Handoff
title: Handoff 2026-06-25 — model law generated+gated, accountability fix, Pristine Program kicked off
description: MESH_LAW is now generated from one source and drift-gated; a pre-existing suite failure was fixed on accountability; the P0 Pristine Codebase Program (#345) is the new self-decomposing spine.
tags: [handoff, model-law, keel, pristine, robustness, p0]
owning_issue: "345"
timestamp: 2026-06-25T00:00:00Z
---

# What landed (branch `feat/model-law-generated`, off `main` @ e1b18b2)

1. **R0 — model law is no longer hand-transcribed.** `lgwks_model_mesh.MESH_LAW` is now
   GENERATED between sentinels from one authored source,
   [`spec/second-harness/model-law.json`](../../spec/second-harness/model-law.json)
   (`lgwks.model.law.v1`), by [`scripts/gen_model_law.py`](../../scripts/gen_model_law.py).
   A new **`model.law` CI lane** (next to `docs.okf` in `scripts/ci/run.mjs`) gates three
   things: the committed block is a fresh regeneration (no hand-edit), every entry conforms
   to the mesh vocabulary, and the Aetherius §3 prose table still matches the recorded
   `prose_table` — *the check that would have caught the hallucinated `Qwen3.7-VL` embed id.*
   Inventory is **byte-identical** to `origin/main` (records inventory, does not change it).
   - Provenance corrected at the root: the docstring + `docs/schemas/REGISTRY.md` wrongly
     cited FINALIZATION §3.1 as MESH_LAW's source; the 8-component `current_law` stack is
     from `docs/AETHERIUS_SPEC_2026.md` §3 — only the embed Eye traces to FINALIZATION. The
     EYE divergence (prose names a VL *visual agent*; law pins the *embedder*) is recorded in
     `spec_divergences` so the gate passes on it and fails on any *new* drift.

2. **Accountability fix.** The full suite (with `cryptography` present) surfaced **1
   pre-existing failure** — `test_home.py::test_domain_for_coverage`: the `models` verb
   (from PR #338, on `main`) was never added to the `DOMAINS` taxonomy. Not mine, but every
   fail the working agent sees is the working agent's to fix. Mapped `models` → Research in
   `lgwks_cli_introspect.py`. **Suite: 2312 passed, 0 failed.**

3. **The Pristine Codebase Program (#345, P0).** The new spine. Doctrine + method in
   [`docs/concepts/pristine-codebase-program.md`](../concepts/pristine-codebase-program.md);
   first worked design (R1 tier ceiling + R2 boundedness invariant) in
   [`docs/concepts/escalation-robustness.md`](../concepts/escalation-robustness.md). The
   epic is self-decomposing: agents break it into sub-issues and fix until pristine.

# The frame (read before continuing)

- Work and review **as an AI Senior Human Dev (SH+)** — out to beat a human SH.
- Most rot = **non-technical-director × happy-path-LLM = slop**: good idea, junior
  execution. On any problem or semantic duplicate, reconstruct *"what were they trying to
  do as a whole?"*, collapse to the one canonical primitive, re-execute, and gate it.
- The model ladder **default-to-no-model is correct** — escalate Math→ML→Model, reach the
  LLM only when needed; the caller sets a **threshold/ceiling**, not a hand-built chain. The
  gap is **robustness** (bounded, fail-closed, provably-terminating), built via **Keel** —
  *not* "run models in CI."

# Verification (claims = commands run)

- `python3 scripts/gen_model_law.py --verify` → GO (fresh, vocab valid, prose reconciled).
- Negative test: hand-editing the generated block → NO-GO exit 1; regenerate restores GO.
- `python3 scripts/gen_okf.py --verify` → 100 concepts conformant, bundle fresh.
- Full suite `uv run --python 3.12 --with pytest --with cryptography --with pyyaml --with networkx python -m pytest tests/ axiom/tests/` → **2312 passed, 46 skipped, 0 failed**.

# Open / next (the P0 tree's first leaves)

- **R1** — add caller-set `ceiling` to `lgwks_model_port.escalate()`; collapse
  `LGWKS_NO_MODELS` into `ceiling="deterministic"`. Spec + acceptance criteria in
  `escalation-robustness.md`. *Recommended first leaf.*
- **R2** — `runtime.bounded` Keel lane proving every hang-class sink routes through the
  canonical bound; fail-closed on timeout.
- **R3–R7** — forked orchestrators (#255), dup utilities (#150/#223), model-port stragglers
  (#222), god-functions, remaining hand-laws. See the inventory in the program doc.
- **Deferred**: codify the `okf_dev_role_delta_pack` (role-delta law) + wire role-based
  delegation into the daemon gates — file as sub-issues; do *not* build on rot first.

# State

Nothing committed yet (work sits on `feat/model-law-generated`, off the synced `main`).
`main` is in sync across local ⊕ gdrive ⊕ origin @ e1b18b2.
