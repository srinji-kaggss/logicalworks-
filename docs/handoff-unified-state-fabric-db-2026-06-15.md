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

1. **Phase 2 — wire existing writers to `ingest_artifact()`** (#165)
   - `lgwks_substrate_run.py`: the legacy per-run `graph.db`/`substrate.db` and the cross-run `GLOBAL_FACT_DB` are now **gone** — relational, graph, and fact-vectors all route through the gate's projections (`project_run` / `graph_fabric.ingest_chunks` / `vector_fabric.ingest_fact_vectors`). Remaining Phase-2 work: move the per-artifact projection into `apply(ctx)` (see next bullet) and emit chunk/media as `ingest_artifact` envelopes rather than the current bulk `project_run` bridge. JSONL mirrors stay as human-readable exports.
   - **Fill the inert seams via their `apply(ctx)`:** give `GraphFabric.apply` entity/relation extraction (carry edges in `IngestContext.extras` or `payload_meta`); give `RelationalProjection.apply` the per-artifact row projection — no new ingest plumbing needed, just the two method bodies.
   - `lgwks_ingest.py`: classify with `lgwks.modality.item.v1`, tokenize with ANT, emit artifacts to the gate.
   - `lgwks_run.py`: emit `embeddings.jsonl` + `prevector.graph.json` as artifacts.
   - `lgwks_research.py`: emit rounds/findings/REPORT.md as artifacts with `modality=reasoning`.

2. **Phase 3 — unified query surface** (#166)
   - Update `lgwks_query.py` adapters to read from `VectorFabric`, `TokenIndex`, `GraphFabric`, and tape replay. **Per the UQA inspiration, the target is one posting-list algebra: every projection answers as `(artifact_cid, payload)` postings so vector/token/graph/relational compose by intersection/union, scored by the calibrated gate (UQA `fuse_log_odds`).**
   - Add CLI: `lgwks fabric status`, `lgwks fabric tokenizers`, `lgwks fabric replay --run <run_id>`.

3. **Phase 4 — hardening** (#167)
   - Cross-tenant leakage red-team against the new gate.
   - Crash replay: delete a projection and rebuild from the tape (the `Projection` contract requires idempotent `apply`, so replay is well-defined).
   - Re-tokenize a run with a new tokenizer and verify old projections are unaffected.
   - **ANT analyzer fixes (file as issue):** `lgwks_tokenizer.py` `tokenize_trajectory` encodes content with `ord(c)` (codepoint, not byte) — chars >255 collide with the Core/Modal/entity token ranges, violating the "byte-level" contract; and entity tokens `1_000_000 + hash % 10_000_000` are lossy (birthday collisions → false postings in the token index). Both matter once token streams feed the posting-list DB.

---

## Dependencies / blockers

- **Issue #150** (centralize duplicated utilities — `_sha` cid-consistency violation) should be reconciled before Phase 2 widens. The gate now imports `lgwks_hashing.content_id` for artifact cids; any future consolidation should preserve that path.
- No model downloads or network calls were added; no new secrets.

---

## Next suggested actions

1. Review + merge this Phase 1 foundation.
2. File child issues for Phase 2, Phase 3, and Phase 4 under #152.
3. Pick Phase 2 next: wire `lgwks_substrate_run.py` to the gate while keeping JSONL mirrors as human-readable exports.

Co-Authored-By: Claude <noreply@anthropic.com>
