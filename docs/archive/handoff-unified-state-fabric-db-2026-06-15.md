---
type: Archive
title: Handoff — Unified State Fabric DB + Tokenizer-Aware Ingestion (Phase 1)
description: Every workflow and command lands here.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Handoff — Unified State Fabric DB + Tokenizer-Aware Ingestion (Phase 1)

**Date:** 2026-06-15
**Scope:** Establish the canonical tokenized artifact envelope, tokenizer registry, and `StorageGate.ingest_artifact()` foundation so research/run/ingest/substrate outputs can naturally converge in one store.
**Issue:** #152 ("Deferred dedup: convergence candidates from one-source-of-truth sweep")
**Plan:** `.claude/plans/unified-state-fabric-db.md`

---

## What shipped

### `lgwks.artifact.tokenized.v1` — canonical artifact envelope
- New module: `lgwks_artifact_tokenized.py`
- One row on the Causal Tape = one artifact from any source (research/run/ingest/substrate/daemon_event/project_artifact).
- Fields: `artifact_cid`, `tenant_id`, `source`, `run_id`/`session_id`, `modality`, `tokenization_id`, `token_stream`, `payload_cid`, `payload_meta`, `capability_id`, `timestamp`, `prev_hash`.
- Deterministic `artifact_cid` over canonical JSON; content-addressed.
- Validation rejects unknown `source` or `modality`.
- JSON Schema: `docs/schemas/lgwks.artifact.tokenized.v1.json`
- Tests: `tests/test_artifact_tokenized.py` (8 passed)

### `lgwks.tokenizer.registry.v1` — tokenizer/analyzer identity
- New module: `lgwks_tokenizer_registry.py`
- Persists as `store/tokenizer_registry.jsonl` under the gate root.
- Auto-seeds two canonical entries:
  - `word_regex:v1` — the existing `WORD_RE` regex from `lgwks_substrate_config`.
  - `aetherius:v0` — the Aetherius Neural Tokenizer with modality anchors `[IMG]`, `[TTY]`, `[VOICE]`, `[SENS]`, `[ANE]`, `[MEM]`.
- Registration is idempotent (first definition wins).
- JSON Schema: `docs/schemas/lgwks.tokenizer.registry.v1.json`
- Tests: `tests/test_tokenizer_registry.py` (5 passed)

### `StorageGate.ingest_artifact()` — THE unified write endpoint
Every workflow and command lands here. The endpoint is built to be robust and
open/closed — new views are added by registration, never by editing the gate.

- **Projection contract** (new module `lgwks_fabric_projection.py`): `Projection`
  Protocol (`name` + `apply(ctx) -> ProjectionResult` + `close()`),
  `IngestContext` (artifact + optional `vector_record` + `index_tokens` + an
  `extras` forward-compat bag), `IngestReceipt`, and `run_isolated()`.
- **Robustness semantics:**
  - The **Causal Tape append is the only must-succeed step** (durable source of
    record). If it raises, nothing is recorded and the caller sees it.
  - The Global Fact List and every projection are **derived and rebuildable by
    tape replay**, so each runs **isolated**: a failing/new projection is captured
    in the `IngestReceipt` (`receipt.ok`, `receipt.failures()`) and can never roll
    back the tape or starve sibling projections.
  - `apply()` must be **idempotent** (content-addressed keys / INSERT OR IGNORE /
    UPSERT) so replay reconstructs projections exactly.
- **Registry:** the four fabrics now implement `Projection` and are registered in
  `StorageGate.__init__`; `register_projection()` is the public extension point.
  - `VectorFabric` (`name="vector"`) — upserts a linked vector record if supplied.
  - `TokenIndex` (`name="token_index"`) — token → artifact posting lists per `tokenizer_id` (the UQA posting-list seam).
  - `GraphFabric` (`name="graph"`) — registered but **inert in Phase 1** (entity/relation edges not yet on the bare envelope).
  - `RelationalProjection` (`name="relational"`) — registered but **inert in Phase 1** (rebuilt by replay in Phase 3).
- `ingest_artifact()` / `ingest_fact()` now return an `IngestReceipt` (truthy iff
  the tape entry was written), not a bare `entry_hash` string. Existing
  truthiness checks keep working; callers that ignore the return (e.g.
  `lgwks_substrate_run.py`) are unaffected.
- `ingest_fact()` remains backward-compatible: it wraps `ingest_artifact()` with
  the default `word_regex:v1` tokenizer. Non-canonical `modality` values (e.g.
  substrate `chunk_kind` like "rule") are preserved as `chunk_kind` in
  `payload_meta` while the artifact uses modality `"text"`.
- Tests: `tests/test_storage.py` extended — artifact ingestion + a
  `TestProjectionRegistry` proving a new projection is routed, a failing one is
  isolated (tape + siblings still commit), and a non-conforming one is rejected
  at registration.

### Training-data path wired (producer side — ANT → gate)
- **ANT fixed** (`lgwks_tokenizer.py`): content is now **byte-level UTF-8** (was
  `ord(c)`, which corrupted the vocab for any char >255); entity tokens use the
  **full 32-bit hash** offset by `ENTITY_TOKEN_BASE` (was a lossy `% 10_000_000`
  that caused false postings). `tokenize_trajectory` now receives the turn's
  actual `content` (the old `to_dict()` path dropped it).
- **Cortex emits trajectories to the fabric** (`lgwks_cortex.py`): each transcript
  turn is ANT-tokenized and written through `gate.ingest_artifact` as a
  `modality=reasoning`, `tokenization_id=aetherius:v0` artifact — so the token
  stream lands on the **Causal Tape + TokenIndex** instead of being discarded.
  The tape is now the replayable training corpus; `*.cortex.jsonl` is a mirror.
  `process_transcript(..., gate=...)` accepts an injected gate for testability.
- **Tokenizer split resolved:** ANT produces the integer token streams (training +
  posting algebra → TokenIndex); **lexical text search is served by FTS5**
  (`chunk_fts`/`fact_fts` in the relational projection), so no second lexical
  tokenizer is needed.
- Tests: `tests/test_cortex_trajectory.py` — ANT byte-level + entity-hash
  determinism, and cortex turns persisting as tokenized artifacts.

### `lgwks.vector.record.v2` — additive metadata columns
- Added `tokenization_id` and `artifact_cid` columns to `vector_records` DDL.
- These fields are metadata only: they do **not** affect the vector cid, so identical embeddings still dedup regardless of which tokenizer named them.
- `decode_record` handles both v1 (8-column) and v2 (10-column) rows.
- **Migration hardening:** `_connect()` now runs `_ensure_v2_columns()` before the
  DDL. A pre-existing v1 store lacks `tokenization_id`/`artifact_cid`, so the v2
  index DDL (`CREATE INDEX ... ON vector_records(tokenization_id)`) would raise
  `no such column` and break *opening* the store. The migration `ALTER`s the
  columns in first (idempotent; no-op on fresh DBs), mirroring the `CausalTape`
  `sequence` backfill.
- Tests: `tests/test_vector_record.py` extended — v2 roundtrip, cid-stability,
  and a **v1→v2 reopen migration** regression.

### Schema registry
- Registered new contracts in `docs/schemas/REGISTRY.md`.
- `python3 scripts/check_schema_registry.py` → conformant (127 ids in code, 137 rows known).

---

## Evidence

| Check | Result |
|---|---|
| `pytest tests/test_artifact_tokenized.py tests/test_tokenizer_registry.py tests/test_storage.py tests/test_vector_record.py tests/test_entity_graph.py tests/test_substrate.py` | 82 passed |
| `python3 scripts/check_schema_registry.py` | conformant (127 ids, 137 rows) |
| `python3 -c "import lgwks_fabric_projection, lgwks_storage, lgwks_substrate_run, lgwks_vector"` | all imports ok |

---

## Files touched

| File | Change |
|---|---|
| `lgwks_artifact_tokenized.py` | new: canonical artifact envelope |
| `lgwks_tokenizer_registry.py` | new: tokenizer/analyzer registry |
| `lgwks_fabric_projection.py` | new: `Projection` contract, `IngestContext`, `ProjectionResult`, `IngestReceipt`, `run_isolated()` |
| `lgwks_storage.py` | extended: projection registry + `register_projection()`, isolated fan-out `ingest_artifact()` returning `IngestReceipt`, fabrics implement `Projection` |
| `lgwks_vector.py` | v2: `tokenization_id` + `artifact_cid` columns **+ `_ensure_v2_columns()` v1→v2 migration** |
| `docs/schemas/lgwks.artifact.tokenized.v1.json` | new schema |
| `docs/schemas/lgwks.tokenizer.registry.v1.json` | new schema |
| `docs/schemas/REGISTRY.md` | register new + updated contracts |
| `tests/test_artifact_tokenized.py` | new tests |
| `tests/test_tokenizer_registry.py` | new tests |
| `tests/test_storage.py` | extended with artifact ingestion tests |
| `tests/test_vector_record.py` | extended with v2 metadata tests |
| `.claude/plans/unified-state-fabric-db.md` | implementation plan |
| `docs/handoff-unified-state-fabric-db-2026-06-15.md` | this handoff |

---

## Seams / what's deferred

The foundation interfaces are now locked. The next agent extends through these seams without refactoring:

**The endpoint contract is now final** — `ingest_artifact(ctx)` + the `Projection`
registry. Phase 2/3 extend through it (register a projection, fill an inert one,
add an `IngestContext` field) and must not refactor the ingest path.

### Consolidation landed in this PR (write + read + first deletion)
- **Producer wired:** cortex trajectories (ANT) and substrate runs now write through
  the gate. substrate_run dual-writes the relational + graph projections in parity
  with (what was) the legacy stores.
- **Reader landed:** `FabricReader` (`lgwks_fabric_reader.py`) is the unified read
  surface (FTS / vector / graph / dims / tape replay).
- **Legacy DELETED:** the per-run `substrate.db` writer `_build_index_db` (zero
  readers; gate `RelationalProjection.project_run` is the cumulative, parity-tested
  replacement). Removed from `lgwks_substrate_db`, the `lgwks_substrate` facade, and
  `substrate_run`; legacy tests updated.
- **Behavior change (intended):** the relational store is now project-cumulative,
  not per-run; the frontier table keeps latest-status-per-URL (idempotent) rather
  than append-all. Cumulative is the chosen model (PII separation is the tenant layer).
- **Legacy DELETED (follow-up PR — graph + fact-vector consolidation):**
  - **#169 DONE** — per-run `graph.db` removed. `substrate_run` ingests into the
    gate's cumulative `GraphFabric` and sources `graph.json`/`graph.mmd`/stats from
    it; `query --neighbors` resolves against the gate via `FabricReader`
    (`GraphFabric.export_json`/`export_mermaid`/`resolve_node` are the new seams).
    `engine` reads its own `.lgwks/entity_graph.db` — unaffected.
  - **#170 DONE** — `GLOBAL_FACT_DB` + `lgwks_substrate_db` module removed. Fact
    embedding vectors now accumulate in the gate's world-tier `VectorFabric` via
    `VectorFabric.ingest_fact_vectors` (tenant=`world`, content-addressed, idempotent;
    deterministic/semantic land in distinct `provider:dN` spaces). `GLOBAL_FACT_DB`
    constant + facade exports removed.
  - **Durability fix (caught by dogfood):** `VectorFabric` writes now commit
    (`vec_mod.upsert_record` doesn't) — `apply()` commits per-artifact,
    `ingest_fact_vectors` once per batch — so vectors survive `gate.close()`. This was
    a latent gap: `VectorFabric` had no substrate-flow writers before #170.

## Phases 2–4 — LANDED (2026-06-22)

The forward plan below shipped on `main`. This section is the completion record;
the Phase-1 narrative above is preserved as the foundation it built on.

1. **Phase 2 — wire writers to the gate** (#165, PR #289) — **DONE.**
   - Every chunk/fact/vector/media row now carries `tokenization_id` + `artifact_cid`
     so a vector traces to the exact tape entry it embeds; `VectorFabric.ingest_fact_vectors`
     and the relational projection both persist that provenance (was NULL).
   - `lgwks_run.py` mirrors `embeddings.jsonl` → `VectorFabric` (provenance-stamped) +
     `prevector.graph.json` → `reasoning` artifact; `lgwks_research.py` mirrors
     `REPORT.md` → `reasoning` artifact. Both best-effort + isolated, keyed on a
     **stable** corpus gate (research: `cfg.project`; run: `"run"`) — never per-run,
     so reasoning trajectories accumulate instead of spawning per-run islands.
   - `lgwks_ingest.py` (original scope item) was deleted in an earlier refactor — moot.
   - `GraphFabric.apply` is live (#165 step 2, prior work); `RelationalProjection`
     is populated in bulk by `project_run` and **rebuildable** by `replay_run` (Phase 3).
   - JSONL/REPORT files remain the human-readable exports.

2. **Phase 3 — unified query surface + fabric CLI** (#166, PR #290) — **DONE.**
   - `FabricReader.query(text)` returns ONE result set across **lexical** (relational
     FTS5), **token-index** (posting coverage for the surfaced artifacts), **graph**
     (node resolution + per-term fallback + neighbours), and **vector** (deterministic
     query embedding → cosine via `VectorFabric.search_similar`, ranked within one
     `space_id`). Every lexical/vector hit carries `tokenization_id` + `artifact_cid`.
   - CLI: **`lgwks state fabric {status,tokenizers,replay,query}`** — housed under the
     existing `state` verb group (T6), so the top-level verb-budget gate stays fixed.
     `status` = `StorageGate.status()`; `replay --run` = `StorageGate.replay_run()`
     (rebuild the relational projection from the tape; `ingest_fact` now threads
     `run_id` so replay is run-scoped).
   - Honest scope note: there is no canonical text→int word encoder for `word_regex`,
     so the token-index is reached *through* the artifacts a query resolves to.

3. **Phase 4 — hardening** (#167) + **capability-gated graph door** (#277) — **DONE** (PR #291).
   - **Tape integrity (true positive, fixed):** the Causal Tape had no verification —
     `CausalTape.verify_chain()` now checks contiguous sequence + `prev_hash` linkage +
     `entry_hash` recomputation per tenant; `replay_run` refuses an inconsistent tape;
     `status()` surfaces `chain_ok`/`chain_error`.
   - **Cross-tenant (§1-INV):** `TenantStore` is now projection-generic
     (`TenantStore.over_gate`) — graph reads gate on the **verified capability** and
     scope to the verified principal; `GraphFabric.scope_tier` is internal behind the
     door. A reads A⊕world, never B's private graph rows. (#277)
   - **Crash replay:** wipe the relational projection → deterministic rebuild from the
     tape; tampered/torn tape refused.
   - **Re-tokenization:** a new tokenizer adds an independent token-index lineage;
     the old lineage is untouched; `tokenization_id` distinguishes them.
   - Documented scope: semantic vectors are model-dependent, not byte-reproducible
     offline — replay rebuilds the deterministic projections; crawl chrome (source/url)
     the tape never recorded comes back empty.

### Resolved after this handoff
- **ANT analyzer fixes (#293, PR #294 — CLOSED):** the codepoint→byte content fix and the
  `% 10_000_000`→full-hash entity fix had already landed in #185; #294 finished the job —
  widened the entity hash 4→7 bytes (56-bit; ~268M-entity birthday point, still inside the
  SQLite signed-`INTEGER` ceiling) for true corpus injectivity, plus the differential
  acceptance tests (distinct entities → distinct token ids; full 0..255 byte round-trip).

### Still open (filed, not done here)
- **#223 residual:** the six legacy DB-stores (cache/cognition/vault/cycle/waste/memory)
  that re-roll their own append/hash-chain persistence are NOT yet projections over the
  fabric — a separate migration from this writer/reader/hardening work.

Co-Authored-By: Claude <noreply@anthropic.com>
