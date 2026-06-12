# Handoff — lgwks subconscious build · 2026-06-12 (session 10, main @ caab5f2)

> Refreshed session 10: opened the **I8-hardening** track (#89) and landed **L1+L2+L7** — §1-INV is now cryptographically enforced (PR #90).
> **One open issue: #89** (I8-hardening, L1+L3 done, L4/L5 tail remaining).
> The dated "Current state" / "Session N state" sections below are append-only history — the **latest** state is the session-10 block at the bottom.

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

**Close the open I-series tail, I8 first — reframed (session 6) as multi-tenant concurrency + isolation over
the two-DB topology.** Director clarified the real surface: concurrency is within one tenant *and* across
tenants; the complexity is the **shared world DB ("the Google", `store/substrate-global/`) + the private
per-pair DB (`store/projects/`)**; the §1-INV tenant isolation holding **under concurrent load** is the
security load (Figma / Google Workspace daemon model). Gap analysis: **[ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md)**
(L1–L9). I8 packet: **[PLANS-NEXT-5.md](PLANS-NEXT-5.md)**. Deferred surfaces (network/MCP, sharing/ACL):
**[SCOPE-DEFERRED.md](SCOPE-DEFERRED.md)**.

**Hardest surface = §1-INV under concurrency** (ARCH L1+L2+L7 enforced through L3+L4). Build order inside I8:
1. **Enforce §1-INV (L1/L2):** tier-routing access layer + tenant-scoped private reads
   (`get_record_for_tenant`/`query_by_source_for_tenant`, capability-guarded). Today `lgwks_vector` reads
   never filter on `tenant` → A can read B. The load-bearing fix.
2. **Tier-scoped capability (L7):** token scopes `tenant:rw` / `world:r` / `world:promote`, not a flat tenant.
3. **Per-tenant durable no-drop fair queue (L3/L4):** durable cross-process `admission_queue` table over
   `lgwks_sqlite.connect` (WAL); backpressure not 429; per-tenant buckets ordered AFTER cap (fixes the
   fail-OPEN, RECONCILE.md:318); fair leasing ≤ `c`; lease/reap crash-durability.
4. **Promotion audit (L5):** tenant→world is the only cross-tier write, logged to the cognition chain.

After I8: **#73 (I9 — deploy CRDT on both tiers, ARCH L6:** G-Set world / OR-Set+LWW tenant, wired to the
live stores) → **#74 (I10** vector-store join) → **#75 (I11** daemon wiring; confirm `LGWKS_TRANSCRIPT_PATH`
with the Director). After #75 the ingestion plan is fully landed.

### Simplest-now correction (session 6 final — read this before the two-DB spec above)
The Director scoped I8 down: **"it's all 1 conceptual db; world data shared; standard data called in at
query; log the complexity as future, get the thing working basically."** So the **now-build** is minimal —
one logical store (`vector_records`), a `tenant` column with a `'world'` sentinel for shared rows, a tenant
read = `WHERE tenant = ? OR tenant = 'world'`, and WAL (`lgwks_sqlite.connect`) for basic concurrency. See
[PLANS-NEXT-5.md](PLANS-NEXT-5.md). The full capability-crypto / durable-queue / CRDT / promotion hardening
([ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md), [SCOPE-DEFERRED.md](SCOPE-DEFERRED.md)) is the
*destination*, not the next commit. North star (framing only, do not over-build): an AI-first Unix-style CLI,
"the daemon you code on" — keep modules small/composable.

### Boilerplate home/stale audit (session 6 — what to wire vs what is staling)
PR #76 added 5 modules. All are CLI-wired in the `lgwks` dispatcher (`lgwks:1483-1500`) but most have **no
runtime caller** — they are scaffolding that will stale unless the canonical issue that owns each is worked.
None is dead/removable; each has a designated home in an open issue:

| module | runtime caller? | home (open issue) | status |
|--------|-----------------|-------------------|--------|
| `lgwks_viz_project.py` | yes — `lgwks_graph_viz.py` | #74 (I10 vector-store join completes the feed) | **partial home**; needs the cid→embedding join |
| `lgwks_capability.py` | `lgwks_vector.query_for_tenant()` | #72 closed | **homed** — tenant field feeds WHERE clause |
| `lgwks_admission.py` | none | deferred — parked for durable-queue future | scaffolding; staling; SCOPE-DEFERRED.md |
| `lgwks_crdt.py` | `lgwks_pipeline.run_pipeline()` Stage 1.5 | #73 closed | **homed** — GSet/ORSet live node tracker |
| `lgwks_waste.py` | `lgwks_session.session_end()` + pipeline Stage 12 | #75 closed | **homed** — wired via LGWKS_TRANSCRIPT_PATH |

**I-series status (session 7):** I1–I12 all landed. No open ingestion issues. `lgwks_admission.py` is the one remaining staling module — its home is the durable-queue / P3→P0 future work documented in ARCH-two-db-multitenant.md.

**Open ops action (carried from I7):** re-register `hooks/subconscious_inbound.py` against the live
`/Applications/logicalworks` dir (currently points at dead space-named path). Confirm path first.

**Open ops action (carried from I7):** to wire the L5 reflex pack into the live
`UserPromptSubmit` hook, re-register `hooks/subconscious_inbound.py` against the live
`/Applications/logicalworks` dir (it points at the dead space-named `/Applications/Logical
Works`). Confirm the path with the Director before relying on live hook behavior. The I7
module + CLI + tests do not depend on it.

## Session 7 state (2026-06-11, PR #79 → main @ 7e570b5)

**I-series: fully landed.** Issues #72–#75 closed. I1–I12 all done.

| module | status | home |
|---|---|---|
| `lgwks_vector` | ✅ homed | I1 + I8 (query_for_tenant) |
| `lgwks_crdt` | ✅ homed | I9 — pipeline Stage 1.5 |
| `lgwks_viz_project` | ✅ homed (partial) | I10 — graph_viz.to_frontend; vector-store join deferred |
| `lgwks_waste` | ✅ homed | I11 — session_end + pipeline Stage 12 |
| `lgwks_admission` | staling | parked for durable-queue future (SCOPE-DEFERRED.md) |
| `lgwks_capability` | ✅ homed | I8 — tenant field → query_for_tenant WHERE clause |

**Next:** no open ingestion issues. Remaining deferred surfaces: crypto §1-INV enforcement, per-tenant durable queue, promotion audit, network/MCP (all in ARCH-two-db-multitenant.md + SCOPE-DEFERRED.md). The P3→P0 trigger for `lgwks_admission` fires before any multi-tenant or network exposure. The hook re-registration ops action (subconscious_inbound.py → live `/Applications/logicalworks` path) is still pending — confirm path with Director before relying on live hook behavior.

## Session 8 state (2026-06-11, main @ 8353036)

**PRD §13 first slice: 2/3 done.**

| unit | status | module | commit |
|---|---|---|---|
| U1 Capability Map | ✅ CLI wired + all verbs covered | `lgwks_map.py` — `add_parser` + 64 intent strings filled | 0b8665d |
| U6 Subconscious Engine | ✅ standalone green | `lgwks_engine.py` — `lgwks.engine.schema.v1` | 8353036 |
| U7 Inbound hook | **next** | upgrade `hooks/subconscious_inbound.py` to call `run_engine()` | — |

**What U7-minimal requires (do not hook until Director confirms):**
1. Replace the `lgwks_map.map_intent()` call in `hooks/subconscious_inbound.py` with `lgwks_engine.run_engine(prompt)`.
2. Format `additionalContext` from the full §6 schema (C/G/P + selections + flags), not just the verb list.
3. Confirm the hook path is registered against the live `/Applications/logicalworks` dir (not the dead `/Applications/Logical Works` path).
4. Test standalone: pipe a JSON prompt payload to `python3 hooks/subconscious_inbound.py` and verify `additionalContext` contains the §6 schema.
5. Only then re-register with `lgwks hooks install`.

**Codebase shape (session 8):**
- 125 modules, 45,246 LOC, 0 staling (NAVMAP regenerated)
- archive/: 8 modules parked (lgwks_actor, lgwks_algorithms, lgwks_diff, lgwks_had, lgwks_local_llm, lgwks_math, lgwks_monitor, lgwks_sast)
- 63 CLI verbs, all mapped to a home domain (no-Other invariant holds)
- Governance gate: 97/97 schema IDs registered

**open ops action (carried from I7):** re-register `hooks/subconscious_inbound.py` against the live `/Applications/logicalworks` dir — confirm path with Director before wiring U7.

**Parallel tracks (do not block U7):** U2 (Actor contract), U3 (World-Graph query), U4 (BERT runtime), U5 (Transcript Cortex) all run in parallel per PRD §12 and upgrade U6 once landed. PRD §13 says: U1 + U7-minimal first (deterministic signals), BERT upgrades the `attention` field after.

## Session 9 state (2026-06-12, main @ dd30d10)

**PRD §13 first slice: DONE. U1 ✅ U6 ✅ U7 ✅.** Then the two U6.1 follow-ons landed.

| unit | status | module | commit / PR |
|---|---|---|---|
| U7 Inbound hook | ✅ closed (#81) — `run_engine()` wired, §6 schema injected; verified test-only | `hooks/subconscious_inbound.py` | #82 |
| U6.2 Qwen-cosine seam | ✅ merged (#85) — coverage→cosine, availability-gated over lexical floor | `lgwks_engine.py` + `scripts/build_capability_embeddings.py` | #87 |
| U6.3 / invariant I8 | ✅ merged (#86) — demand-weighted coverage, padding/verbosity-invariant | `lgwks_engine.py` + `scripts/build_capability_idf.py` | #87 |

**§6 score axes now (post U6.1/U6.2/U6.3):** C coverage (lexical+demand OR Qwen-cosine; `coverage_mode` reports which) · G grounding gap (graph, nullable) · d decisiveness (margin) · P = geometric mean over available axes (constant-free). New artifacts: `lgwks.capability_idf.v1`, `lgwks.capability_vectors.v1` (both optional, runtime degrades gracefully when absent).

**Hardened (adversarial pass):** `.lgwks/*.json` artifacts are an untrusted input surface — sanitized (finite/non-negative weights), C clamped to [0,1], `_embedding_coverage` fully guarded (poison → lexical floor, never raises), prompt capped (`_MAX_PROMPT_CHARS`). 52 engine/invariant/hook tests green.

**Codebase shape (session 9):** 128 modules, 46,444 LOC (NAVMAP regenerated). Governance gate: 99/99 schema IDs registered.

**Two open ops/decisions (Director-gated):**
1. **Live hook wiring** — U7 is verified test-only; the `UserPromptSubmit` hook is NOT registered. Wire it into `/Applications/logicalworks/.claude/settings.json` when the Director wants live interception (it's a `UserPromptSubmit` Claude-Code hook, NOT an `lgwks hooks` bus event).
2. **Activate qwen mode** — `make download-models` (Qwen3-VL-Embedding-8B not present here) + run the two `scripts/build_capability_*` builders; the engine stays on the lexical floor until then.

**Next deferred (need Director go):** N novelty axis + `attention` (Qwen-native); P→probability calibration (outcome log + isotonic fit). U2–U5 parallel tracks still upgrade U6 once landed.

## Session 10 state (2026-06-12, main @ 8586b11, PR #90)

**I8-hardening track opened (#89) — L1 landed.** The deferred half of I8 (the full multi-tenant
destination in `ARCH-two-db-multitenant.md`, gaps L1–L7) was promoted out of the SCOPE-DEFERRED
ledger into issue **#89**. Director scoped the full packet (L1–L5); built the load-bearing first
step this session.

**L1+L2+L7 done (PR #90 @ 8586b11) — §1-INV now cryptographically enforced:**

| piece | what | module |
|---|---|---|
| L7 tier-scoped caps | `lgwks.capability.v1→v2`: scopes (`tenant:rw`/`world:r`/`world:promote`) signed into the HMAC payload → escalation/narrowing breaks the sig. `require_scope()` gates each tier op. | `lgwks_capability.py` |
| L1 secure cid read | `get_record_for_tenant()` — resolves own ⊕ world only; cross-tenant cid → `None` (no existence side-channel). `get_record`/`query_by_source` marked UNSCOPED/admin-only. | `lgwks_vector.py` |
| L2 seam on read path | `assemble_inbound(tenant=...)` + `inbound run --tenant` — cross-tenant graph nodes drop from the reflex pack. | `lgwks_inbound.py` |
| harden (in-thread) | `world` reserved as non-issuable + guard-rejected; `make_tenant_filter` world-aware. | `lgwks_capability.py` |

81 tests green (incl. §1-INV **10⁴ A/B against a live on-disk store**); registry 99/99 (v2 row,
v1 superseded). BUILDLOG + NAVMAP updated in-PR.

**Honest limits (NOT closed — deferred to the L2/L3 access router; documented in BUILDLOG):**
1. **Enforcement is advisory** — `query_for_tenant`/`get_record_for_tenant` trust the tenant
   string; nothing structurally forces every caller through `guard`/`require_scope`. Mandatory
   gating is the L2 access-router work.
2. **`assemble_inbound(tenant=None)` is fail-open** by design (single-operator P3 default) until
   multi-tenant exposure.

**L3 done (PR #92 @ caab5f2) — per-tenant admission, fail-open closed:**

| piece | what | module |
|---|---|---|
| capability-first | `TenantAdmissionGate.admit/lease/release` run `require_scope(TENANT_RW)` BEFORE any rate/queue/lease state → invalid/missing cap consumes no token, no slot. Closes the L1-noted "advisory enforcement" gap on the admission path. | `lgwks_admission.py` |
| per-tenant lanes | each validated tenant gets its own `TokenBucket` + bounded `AdmissionQueue` (per-tenant `q_max`) → one tenant's flood drains only its own lane. | `lgwks_admission.py` |
| fair leasing ≤ c | in-flight bounded by `c` AND per-tenant ceiling ⌈c/active⌉ via `lease()/release()`. | `lgwks_admission.py` |

Reused `lgwks.admission.v1` (no mint). 73 tests green (12 new in `test_i8_admission_fairness.py`);
registry 99/99. **Honest limit:** in-memory single-process; durable cross-process backing is L4
(the `lease()/release()` interface is left for L4 to persist).

**Next (issue #89 tail, ARCH build order):** **L4** durable cross-process queue (WAL
`admission_queue` table over `lgwks_sqlite.connect`, no drop/backpressure, lease/reap
crash-durability — persists the L3 lease interface) → **L5** promotion audit (tenant→world
hash-chained record on the cognition chain, `lgwks_cognition.py`). **L6** (CRDT deploy on the two
stores) is a separate packet = I9. Deferred surfaces (network/MCP D2, cross-workspace ACL D3, …)
stay parked in `SCOPE-DEFERRED.md`.

## Doc map

- `spec/second-harness/PRD.md` — authoritative end-state. §12 unit table. §13 first slice.
- `INGESTION-PLAN.md` — per-packet contracts/status (rung 1 for the data layer, all done).
- `INGESTION-LAYER.md` — architecture + proven math (§4 scoring, §7 consumer tail) + §8 gap log.
- `BUILDLOG.md` — append-only build-state truth.
- `docs/schemas/REGISTRY.md` — every cross-module contract; check before minting.
- `docs/NAVMAP.md` + `docs/navmap.json` — generated module atlas (125 modules); refresh with `python3 scripts/gen_navmap.py`.
- `prd/PRD-04-context-economy.md` — reflex-cap + RRF authority for I7.
