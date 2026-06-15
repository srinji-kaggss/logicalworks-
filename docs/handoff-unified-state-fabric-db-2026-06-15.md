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

### `StorageGate.ingest_artifact()` — unified write path
- Extended `lgwks_storage.py` with four projection seams:
  - `VectorFabric` — wraps `lgwks_vector` SQLite store.
  - `TokenIndex` — token → artifact posting lists per `tokenizer_id`.
  - `GraphFabric` — seam around `lgwks_entity_graph.GraphDB`.
  - `RelationalProjection` — disposable per-tenant SQLite query surface.
- `ingest_artifact()` appends to the Causal Tape, registers in the Global Fact List, optionally persists a linked vector record, and optionally indexes the token stream.
- `ingest_fact()` remains backward-compatible: it now wraps `ingest_artifact()` with the default `word_regex:v1` tokenizer. Non-canonical `modality` values (e.g. substrate `chunk_kind` like "rule") are preserved as `chunk_kind` in `payload_meta` while the artifact uses modality `"text"`.
- Tests: `tests/test_storage.py` extended (4 new artifact tests)

### `lgwks.vector.record.v2` — additive metadata columns
- Added `tokenization_id` and `artifact_cid` columns to `vector_records` DDL.
- These fields are metadata only: they do **not** affect the vector cid, so identical embeddings still dedup regardless of which tokenizer named them.
- `decode_record` handles both v1 (8-column) and v2 (10-column) rows.
- Tests: `tests/test_vector_record.py` extended (2 new v2 tests)

### Schema registry
- Registered new contracts in `docs/schemas/REGISTRY.md`.
- `python3 scripts/check_schema_registry.py` → conformant (127 ids in code, 137 rows known).

---

## Evidence

| Check | Result |
|---|---|
| `pytest tests/test_artifact_tokenized.py tests/test_tokenizer_registry.py tests/test_storage.py tests/test_vector_record.py` | 41 passed |
| `pytest tests/test_artifact_tokenized.py tests/test_tokenizer_registry.py tests/test_storage.py tests/test_vector_record.py tests/test_entity_graph.py tests/test_substrate.py` | 78 passed |
| `python3 scripts/check_schema_registry.py` | conformant |
| `python3 -c "import lgwks_storage, lgwks_artifact_tokenized, lgwks_tokenizer_registry, lgwks_vector, lgwks_substrate_run, lgwks_ingest, lgwks_research, lgwks_run"` | all imports ok |

---

## Files touched

| File | Change |
|---|---|
| `lgwks_artifact_tokenized.py` | new: canonical artifact envelope |
| `lgwks_tokenizer_registry.py` | new: tokenizer/analyzer registry |
| `lgwks_storage.py` | extended: `StorageGate.ingest_artifact()`, four projection fabrics, backward-compatible `ingest_fact()` |
| `lgwks_vector.py` | v2: `tokenization_id` + `artifact_cid` metadata columns |
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

1. **Phase 2 — wire existing writers to `ingest_artifact()`**
   - `lgwks_substrate_run.py`: route chunks/facts/media to the gate instead of (or in addition to) per-run JSONL/`graph.db`/`substrate.db`.
   - `lgwks_ingest.py`: classify with `lgwks.modality.item.v1`, tokenize with ANT, emit artifacts to the gate.
   - `lgwks_run.py`: emit `embeddings.jsonl` + `prevector.graph.json` as artifacts.
   - `lgwks_research.py`: emit rounds/findings/REPORT.md as artifacts with `modality=reasoning`.

2. **Phase 3 — unified query surface**
   - Update `lgwks_query.py` adapters to read from `VectorFabric`, `TokenIndex`, `GraphFabric`, and tape replay.
   - Add CLI: `lgwks fabric status`, `lgwks fabric tokenizers`, `lgwks fabric replay --run <run_id>`.

3. **Phase 4 — hardening**
   - Cross-tenant leakage red-team against the new gate.
   - Crash replay: delete a projection and rebuild from the tape.
   - Re-tokenize a run with a new tokenizer and verify old projections are unaffected.

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
