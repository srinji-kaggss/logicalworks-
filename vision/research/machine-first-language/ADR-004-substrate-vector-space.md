# ADR-004 — Substrate Vector Space: Canonical Space Decision and Build/Query Identity

**Status:** Accepted  
**Date:** 2026-06-07  
**Relates to:** Issue #41, Issue #35 (Apple-local provider seam, non-goal here)  
**Files affected:** `lgwks_substrate.py`, `tests/test_substrate.py`

---

## Context

`substrate build` embeds chunks using whichever embedding provider is requested at build time
(default `auto`, which resolves to the local Ollama provider or the deterministic feature-hash
fallback). The build records per-chunk vectors in `store/substrate/<run>/vectors.jsonl` and
embedding metadata in `store/substrate/<run>/manifest.json`.

Before this ADR, `substrate query --vector` defaulted `--embed-provider` to `"auto"`. If the
session's `auto` resolution produced a *different* provider than the one used at build time
(e.g., build used `deterministic-feature-hash` but query resolved to
`ollama:qwen3-embedding:8b`), the cosine/dot-product scores were cross-space noise —
numerically meaningful only within a single vector space. This bug was verified on run
`collm-paper-20260606-132500`.

### Concrete failure mode

```
lgwks substrate build <url> --project p --embed-provider deterministic
lgwks substrate query store/substrate/p-* --kind chunks --vector "RRSP minimum"
# → silently embeds query with qwen3, produces cross-space dot products
```

---

## Problem Statement

A substrate run's identity includes its **vector space**: the embedding provider, model, and
dimensionality used during build. If query-time embedding uses a different space, similarity
scores are undefined — they are cross-space noise, not semantic proximity measurements.

Allowing silent space mismatch:
- Corrupts downstream agent decisions that rely on vector similarity.
- Makes debugging opaque (scores look plausible but are meaningless).
- Violates the L=0 reproducibility contract for deterministic-lane queries.

---

## Decision

### 1. Run identity includes vector space

Each substrate run now records a stable `vector_space` descriptor in `manifest.json`:

```json
{
  "vector_space": {
    "provider_requested": "auto",
    "model_requested": "",
    "providers_used": {"ollama:qwen3-embedding:8b": 10},
    "canonical_provider": "ollama:qwen3-embedding:8b",
    "canonical_model": "",
    "dims": 256,
    "semantic": true,
    "ambiguous": false
  }
}
```

If multiple providers or dimensionalities were used in one run, `ambiguous` is `true` and
`canonical_provider` is empty.

### 2. Query defaults to build-time vector space

`substrate query --vector` now defaults `--embed-provider` to `""` (empty, meaning
"not specified"). When not specified, the query resolves the provider from the run's
`manifest.json → vector_space.canonical_provider`.

**Source-of-truth priority for resolving stored vector space:**
1. `manifest.json` → `vector_space` field (canonical; written at build time).
2. Fallback: inspect `vectors.jsonl` directly if manifest is absent — valid only if all rows
   share a single provider and dimensionality.
3. If ambiguous or missing: **fail closed** — return a structured error unless
   `--force-cross-space` is supplied.

### 3. Explicit provider mismatch is a hard error

If the user explicitly passes `--embed-provider` or `--embed-model` and the value differs from
the stored canonical space, `substrate query` returns a structured error:

```json
{
  "schema": "lgwks.substrate.vector_query.v0",
  "ok": false,
  "error": "embedding provider mismatch",
  "stored_vector_space": {...},
  "requested_vector_space": {...},
  "hint": "rerun without --embed-provider / --embed-model, or pass --force-cross-space"
}
```

No rows are returned. The error is fail-closed, not a warning.

### 4. Escape hatch: `--force-cross-space`

The only way to proceed with a cross-space query is:

```
lgwks substrate query <run> --vector "..." --embed-provider ollama --force-cross-space
```

When forced, the result includes:

```json
{
  "ok": true,
  "cross_space_forced": true,
  "warning": "scores are cross-space and not semantically comparable",
  ...
}
```

Agents consuming substrate query output **must** check `ok` and the absence of
`cross_space_forced` before trusting scores.

### 5. Query output always reports both spaces

Every successful vector query reports:

```json
{
  "query_vector_space": { "provider": "...", "model": "...", "semantic": true },
  "stored_vector_space": { "canonical_provider": "...", ... }
}
```

This allows downstream agents to verify space consistency without re-reading the manifest.

---

## Hybrid Lane Architecture (Current Canonical Path)

The substrate supports two embedding lanes, both may be active in a single build:

| Lane | L-level | Provider | Auditability | Recall quality |
|---|---|---|---|---|
| **L0 deterministic** | L=0 | `deterministic-feature-hash` | Fully reproducible; no model weights | Weak (loose top-k) |
| **Semantic** | L≥1 | `ollama:<model>` (frozen local) | Reproducible given frozen weights + hash | Strong semantic |

When a single run uses both lanes (e.g., `--embed-provider auto` resolves differently per
chunk), `ambiguous` is set and vector queries fail closed. **The recommended pattern is to
choose one lane per build.**

Future: a hybrid build that records *two* vector spaces (one per lane) is possible but
out of scope here.

---

## Non-Goals

- **Do not add Apple-local embeddings here.** That seam is tracked in Issue #35.
- **Do not change `lgwks_run.embed` provider semantics globally.**
- **Do not rebuild existing substrate runs.** Runs built before this ADR lack `vector_space`
  in their manifest; their `vectors.jsonl` fallback will work if homogeneous.
- **Do not change non-vector substrate query behavior** (`--match`, `--neighbors` are
  unaffected).
- **No new database schema.** `manifest.json` + `vectors.jsonl` JSONL are sufficient.

---

## Consequences

### Positive
- Cross-space mismatch is no longer silent; downstream agent decisions are not silently corrupted.
- `manifest.json` becomes the single source of vector-space truth for a run.
- New agents can read `vector_space` to decide whether scores from two runs are comparable
  (same canonical provider + model + dims → cross-run scores are valid).
- The `--force-cross-space` flag makes cross-space queries opt-in and clearly marked.

### Negative / Trade-offs
- Runs built before this ADR without `vector_space` in manifest rely on the `vectors.jsonl`
  fallback. If those runs are homogeneous they work; if mixed they will fail closed.
- Agents that previously relied on the old `provider` / `semantic` top-level fields in query
  output must be updated to read `query_vector_space.provider` and `query_vector_space.semantic`.
- The `--embed-provider` choice restriction is removed from the query parser (to allow the
  empty-string default); explicit values are still validated at `lgwks_run.embed` level.

---

## Checklist

- [x] `_load_run_manifest` helper added to `lgwks_substrate.py`
- [x] `_stored_vector_space` helper added (manifest-first, jsonl fallback, fail-closed)
- [x] `_vector_search` updated: space resolution, mismatch check, `force_cross_space` param
- [x] `build_run` emits `vector_space` in `manifest.json`
- [x] `query_run` passes `force_cross_space` to `_vector_search`
- [x] Query parser: `--embed-provider` default changed to `""`, `--force-cross-space` added
- [x] Tests: 8 cases covering all acceptance criteria
- [x] This ADR written at `vision/research/machine-first-language/ADR-004-substrate-vector-space.md`
