# Handoff — lgwks ingestion layer (scoring spine landing) · 2026-06-10

You are the next agent on the lgwks rebuild. Read this fully before acting. Written
AI-for-AI; receipts, not essays. Authority ladder: `/CLAUDE.md` → `governance/README.md`
→ `spec/second-harness/INGESTION-PLAN.md` (work packets) → `docs/ARCHITECTURE.md` → the
assigned GitHub issue. Build-state truth = `BUILDLOG.md`, not spec prose.

## Hard constraints (do not violate)

1. **The model layer is OUT OF SCOPE.** Do not spec, map, or touch it. Treat all models
   (Eye/Tongue/Membrane, Ollama, Gemini, Qwen3-VL, CoreML) as opaque deps. The
   text=local-Qwen / media=cloud-Gemini split is INTENDED. If a step needs the model
   layer, STOP AND ASK.
2. **Verify before you assert.** Every claim about env/git/files/tests runs the command
   first. `cargo test` / `pytest` is the verifier. Use the repo venv: `.venv/bin/python`.
3. **No emojis. No sprawl.** Receipts. Don't mirror the Director's thinking-out-loud.
4. **On a real fork in the Director's intent, ASK (AskUserQuestion).** Don't ask what the
   code can answer; read the code.
5. **No silent failure, no gate weakening.** When a check fails, fix the thing under test,
   never loosen the gate. Surface degeneracy/non-convergence loudly.

## Current state (verified — main @ docs-update commit)

Ingestion packets I1–I6 + I12 are **done and merged**. The deterministic scoring spine
(I1 → I4/I5 → I6) is complete. Per-packet detail in `INGESTION-PLAN.md`; landings in
`BUILDLOG.md` (2026-06-10 session 2). Contracts in `docs/schemas/REGISTRY.md`.

- **I1** `lgwks_vector.py` — `lgwks.vector.record.v1` (binary f32, blake2b cid, space guard).
- **I2** `lgwks_input.py` — `lgwks.modality.item.v1` (universal input routing).
- **I3** `crawler/` v2 + `lgwks_lfm2_extract.py` — `lgwks.crawl.v2` + `…artifacts.v1` (PR #64).
- **I4** `lgwks_embed_port.py` — `lgwks.embed.port.v1` (mlx→transformers, local-only).
- **I5** `lgwks_score.py` — `lgwks.score.record.v1` + `lgwks.schema.relations.v1`: factored
  RESCAL `R_k`, CBOR+zstd MDL, blake2b cid (PR #65). CLI `lgwks score`.
- **I6** `lgwks_rank.py` — `lgwks.rank.record.v1`: relation-weighted vs relation-blind
  centrality, σ-shifted power iteration + Rayleigh convergence, δ slop signal (PR #67).
  CLI `lgwks rank`. Closes G-06.
- **I7** `lgwks_inbound.py` — `lgwks.inbound.v1`: RRF fusion of graph rank ⊕ vector cosine
  rank (`RRF_K=60`), 1500-token reflex cap, deterministic truncation (bulk first, depth
  pointers survive), zero-dangling handles. CLI `lgwks inbound run|info`. 12 tests
  (session 3). Hook extension still gated on the re-registration ops action (below).
- **I12** graphify Leiden fix (PR #63).

Gaps G-04/05/06/11/12 closed (INGESTION-LAYER §8).

## NOT built / deferred (honest — do not claim otherwise)

- **I5.1 (deferred, not yet issued)** — directional `P_k` activation. I5 ships identity
  operators (so the §4.2 marginal-identity proof holds exactly); scoring currently
  collapses to cosine. Genuine directional/embedding-coupled scoring is future work.
- **§4.3 honesty** — with fixed `w_k`, I6 centrality is a relation-WEIGHTED eigenvector
  centrality (faithful to §4.3 for the n×m×n tensor), not a free cubic-in-x optimization.
  δ is a structural signal until I5.1 wires per-fact `s_ai`.
- **I8–I11 (P3, not yet issued)** — I8 (queue/isolation) escalates to **P0 before any
  multi-tenant or network exposure**. I10 viz must never run ahead of the spine.

## Workflow that worked this session (the Director's loop)

Per substantive packet: **spec (GH issue comment) → implement → hacker-harden → merge.**
Implementation can be delegated to a Sonnet subagent (the issue spec is the contract);
**review/harden in the main thread** — green subagent tests repeatedly hid real defects
(hollow signals, silent non-convergence, dead/unwired CLI). Recurring integration traps:
(1) every new `lgwks.*.vN` literal needs a `REGISTRY.md` row or the `governance.yml` CI
gate fails; (2) a new CLI verb must be wired in the `lgwks` dispatcher AND added to
`lgwks_home._DOMAINS` (the `test_home` L0 no-Other-catch-all invariant); (3) run the
registry gate from the repo root, not a `.claude/` worktree (it skips `.claude` paths).

## Suggested next step

Per build order **I7 → I5.1 → I8** (PLANS-NEXT-3.md): I7 landed (session 3). Next is
**I5.1** — directional `P_k` operator activation (`lgwks_score.py:73 build_operators`,
currently all-identity → scoring collapses to cosine). **File the GH issue first**
(not yet issued). The hard constraint: any directional `P_k` must keep the §4.2
marginal-identity proof `(1/m)Σ_k R_k = I` to ≤1e-6 — if neither derivation (sign-flip
involution / antisymmetric tie-break) closes cleanly, STOP AND ASK (the proof is
load-bearing). Then I8 (queue/isolation, P3→P0 before any multi-tenant/network exposure).

**Open ops action (carried from I7):** to wire the L5 reflex pack into the live
`UserPromptSubmit` hook, re-register `hooks/subconscious_inbound.py` against the live
`/Applications/logicalworks` dir (it points at the dead space-named `/Applications/Logical
Works`). Confirm the path with the Director before relying on live hook behavior. The I7
module + CLI + tests do not depend on it.

## Doc map

- `INGESTION-PLAN.md` — per-packet contracts/status (rung 1 for the data layer).
- `INGESTION-LAYER.md` — architecture + proven math (§4 scoring, §7 consumer tail) + §8 gap log.
- `BUILDLOG.md` — append-only build-state truth.
- `docs/schemas/REGISTRY.md` — every cross-module contract; check before minting.
- `prd/PRD-04-context-economy.md` — reflex-cap + RRF authority for I7.
