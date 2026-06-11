# Handoff — lgwks ingestion layer · 2026-06-11 (session 6, post PR #76)

> Refreshed session 6: I8–I11 boilerplate merged (PR #76); issues #72–#75 filed/open; next = close the
> tail, I8 first ([PLANS-NEXT-5.md](PLANS-NEXT-5.md)). The dated "Current state" sections below are
> append-only history — the **latest** state is the session-6 block lower in this file.

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
  pointers survive), zero-dangling handles. CLI `lgwks inbound run|info`. 14 tests incl
  real-graph. Hook extension still gated on the re-registration ops action (below).
- **I5.1** `lgwks_score.py` — directional operators activated: `R_k = P_k·diag(d_k) + N_k`,
  antisymmetric `N_k` paired so `Σ_k N_k = 0` ⇒ marginal stays identity (§4.2 proof exact)
  while directed relations score asymmetrically. Schema relations v1→v2 (issue #69). 28 tests.
  **Structural** directionality only — semantic arg-typing remains future work (`arg_typing=None`).
- **I12** graphify Leiden fix (PR #63).

Gaps G-04/05/06/11/12 closed (INGESTION-LAYER §8).

## NOT built / deferred (honest — do not claim otherwise)

- **§4.3 honesty** — with fixed `w_k`, I6 centrality is a relation-WEIGHTED eigenvector
  centrality (faithful to §4.3 for the n×m×n tensor), not a free cubic-in-x optimization.
  δ is a structural signal until I5.1 wires per-fact `s_ai`.
- **I8 P3→P0 trigger** — admission/capability boilerplate is complete and tested. P3→P0
  escalation trigger is documented in CLI output but NOT wired to a live process manager.
  Must escalate before any multi-tenant or network exposure.
- **I10 viz embedding join** — `to_frontend` wires `xyz_map` placeholder; a real SQLite join
  (embeddings-by-cid from the vector store) is needed to populate server-side coordinates
  at serve time. Not in I10 scope (viz-only); wire when the vector store is queryable at
  graph-serve time.
- **I11 citation detection** — cid substring-match proxy; true semantic citation detection
  would need model-layer analysis (out of scope, INV-3). Deterministic and explainable.
- **Hook re-registration** — `hooks/subconscious_inbound.py` still points at the dead
  space-named `/Applications/Logical Works` path. Gated on ops action (below).

## Workflow that worked this session (the Director's loop)

Per substantive packet: **spec (GH issue comment) → implement → hacker-harden → merge.**
Implementation can be delegated to a Sonnet subagent (the issue spec is the contract);
**review/harden in the main thread** — green subagent tests repeatedly hid real defects
(hollow signals, silent non-convergence, dead/unwired CLI). Recurring integration traps:
(1) every new `lgwks.*.vN` literal needs a `REGISTRY.md` row or the `governance.yml` CI
gate fails; (2) a new CLI verb must be wired in the `lgwks` dispatcher AND added to
`lgwks_home._DOMAINS` (the `test_home` L0 no-Other-catch-all invariant); (3) run the
registry gate from the repo root, not a `.claude/` worktree (it skips `.claude` paths).

## Current state (updated — session 4, 2026-06-11)

Ingestion packets **I1–I12 are all scaffolded**. I1–I7 + I5.1 + I12 are merged to main.
I8–I11 boilerplate was implemented in session 4 (branch `claude/docs-implementation-boilerplate-83n6r1`):
- **I8** `lgwks_admission.py` + `lgwks_capability.py` — token-bucket admission + capability-token isolation.
- **I9** `lgwks_crdt.py` — G-Set / OR-Set / LWW-Register, SEC convergence proof in tests.
- **I10** `lgwks_viz_project.py` — sign-fixed PCA projection, additive `xyz` in `to_frontend`.
- **I11** `lgwks_waste.py` — per-session waste ledger; `lgwks.waste.ledger.v1` flipped live.
All 61 new tests green. Registry gate green (95 ids / 103 rows).

## Current state (updated — session 6, 2026-06-11, post PR #76)

**I8–I11 boilerplate is merged to main** (PR #76 @ 6c2fdac — admission, capability, CRDT, viz-projection,
waste ledger; adversarially reviewed). **GH issues #72–#75 are filed and OPEN** (I8/I9/I10/I11, label
`ingestion`). The modules + tests are landed; what remains per issue is the **hardening/deployment** half of
each `Done =` line — the boilerplate is the structure, not the close. The I-series plan (I1–I12) is the
*entire* active backlog; PLANS-NEXT-4 closes with "after I11 the ingestion plan is fully landed" — there is
no I13.

## Suggested next step

**Close the open I-series tail, I8 first.** I8 (#72) is next because it is the security/isolation gate that
escalates **P3→P0 before any multi-tenant or network exposure** (gaps G-07 high/T0, G-09 high). Its hardening
is specced in **[PLANS-NEXT-5.md](PLANS-NEXT-5.md)** (session 6) — three gaps, NOW-safe vs exposure-gated:

1. **I8 Gap A (NOW):** the capability boundary is NOT wired into the live store reads —
   `lgwks_vector.get_record`/`query_by_source` filter on cid/source_cid, never tenant. Add `*_for_tenant`
   reads and route the `guard()` path through them. This is the load-bearing fix; isolation is a fiction
   until a read path cannot return another tenant's cid.
2. **I8 Gap B (exposure-gated):** sustained-load λ-sweep {0.5cμ, cμ, 2cμ} with zero 5xx.
3. **I8 Gap C (exposure-gated):** wire the P3→P0 escalation to a fail-closed checkpoint at the exposure
   entrypoint (it is documented prose today, not enforced). Confirm with the Director which surface opens
   first before choosing the entrypoint.

After I8: **#73 (I9 CRDT** — nearest to done; SEC/CvRDT tests green, mostly needs BUILDLOG proof + close) →
**#74 (I10** vector-store join: SQLite join on `vr_space_tenant` by cid so `to_frontend` emits real coords,
not an empty `xyz_map`) → **#75 (I11** daemon-loop wiring + live transcript path; confirm
`LGWKS_TRANSCRIPT_PATH` with the Director). After #75 the ingestion plan is fully landed.

**Open ops action (carried from I7):** re-register `hooks/subconscious_inbound.py` against the live
`/Applications/logicalworks` dir (currently points at dead space-named path). Confirm path first.

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
