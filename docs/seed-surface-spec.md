---
type: Spec
title: Seed Surface Spec (JEPA-001 / JEPA-002 / JEPA-003)
description: Status: spec
tags: [spec]
timestamp: 2026-06-06T13:13:23-04:00
---

# Seed Surface Spec (JEPA-001 / JEPA-002 / JEPA-003)

Status: spec

## What seed is

The human-facing ingress compiler. The human dumps — links, thoughts, code fragments,
docs, "this matters somehow" — with zero discipline. Seed normalizes it, crawls it,
binds it to repo state, and compiles it into a durable machine-readable package.

The human never thinks about JEPA, bots, or packages. They just dump.

Seed is a new CLI layer over existing internals (capture/portal/jepa).
It adds: human-friendly verbs, zero-discipline intake, seed index, and continuation.

## Verbs

```
lgwks seed ingest  <views...>         — compile raw input into a seed package
lgwks seed continue <query|key>       — load best package, refresh, emit context
lgwks seed show    <key>              — inspect a seed package
lgwks seed ls      [--repo PATH]      — list seeds, sorted by freshness
lgwks seed refine  <key> <new_input>  — add new views to an existing seed
```

## lgwks seed ingest

### Inputs accepted (zero-discipline)

- URLs (crawled via lgwks_crawl)
- file paths (read and normalized)
- inline text (piped or passed as arg)
- repo paths (graph extracted)
- existing package keys (referenced as prior)

### What it does

```
1. normalize each view → typed_view (url | file | text | repo | prior)
2. crawl URLs, extract text, store in seed resource folder
3. extract repo graph if a repo path is given
4. run bot fabric on any repo-local changed files
5. build JEPA package from views + bot findings + graph
6. write seed index entry
7. auto-suggest candidate project bindings
8. emit: seed key, summary card, L score
```

### Output structure

```
store/seeds/<seed_key>/
  package.json          — JEPA package (lgwks.jepa.package.v1)
  machine-packet.json   — compact context for AI
  human-summary.md      — one-page human projection
  resources/            — crawled/extracted raw materials
  views/                — normalized input views
  index-entry.json      — seed index record
```

### Seed key

Deterministic from content hash of normalized views:
```
seed:<sha256(sorted(view_hashes))[:16]>
```

Same content ingested twice produces the same key (idempotent).

## lgwks seed continue

### What it does

```
1. resolve best matching seed/package for the query
   — exact key match if key given
   — semantic lookup via BERT router if query text given (abstain → recency fallback)
2. refresh repo graph on changed files since last package
3. run bot fabric on changed files
4. update package with fresh findings
5. emit: technical stream for AI, human fit summary, next actions
```

### Resolution policy

```
exact key    → load directly
query text   → BERT router (if available) → top-1 or abstain
abstain      → recency fallback: most recent seed for this repo
no match     → emit structured error, suggest ingest
```

### Continuation packet (JEPA-003)

The continuation packet is the machine packet extended with:
```json
{
  "continuation_context": {
    "prior_package_id": "...",
    "repo_head": "...",
    "changed_files_since_last": [...],
    "fresh_findings_count": 12,
    "contradiction_delta": 2,
    "suggested_hardening": [...]
  }
}
```

This is the bytecode the AI loads. Not the chat. Not memory.md. The compiled artifact.

## Seed index (JEPA-002)

File: `store/seeds/index.json`

Each entry:
```json
{
  "key": "seed:abc123",
  "created_at": "...",
  "repo": "...",
  "anchors": [...],
  "tags": [...],
  "freshness": "2026-06-06T12:00:00Z",
  "l_score": 0.04,
  "finding_count": 18,
  "contradiction_count": 2
}
```

### Lookup axes supported

- exact key
- repo path
- anchor (file, symbol, concept)
- date range
- query text (BERT router / recency fallback)

## Event ledger (JEPA-004)

Every seed operation appends to: `store/seeds/ledger.jsonl`

Event kinds:
```
seed_built | repo_bound | continued | command_run | outcome | contradiction_added | contradiction_resolved
```

Each event:
```json
{
  "schema": "lgwks.seed.event.v1",
  "event_id": "...",
  "kind": "seed_built",
  "seed_key": "...",
  "timestamp": "...",
  "actor": "human | bot | llm",
  "payload": {...}
}
```

`actor: llm` events contribute to L score tracking across sessions.

## L score in seed context

Every seed package carries an L score. The seed index makes it queryable.
High-L seeds are flagged in `lgwks seed ls` output:
```
seed:abc123  2026-06-06  repo:logic-os-kernel  findings:18  L:0.04  ✓
seed:def456  2026-06-06  repo:logic-os-kernel  findings:3   L:0.82  ⚠ high LLM coefficient
```

## Design constraints

1. ingest is idempotent — same content produces same key, no duplicate packages
2. continuation never blocks the human — runs in background, streams progress
3. seed index is append-only — no entries deleted, only superseded (with pointer to successor)
4. all seed operations append to the event ledger
5. a seed with no repo binding is valid (research/intake mode)
6. CLI output is human-readable by default; `--machine` flag emits JSON

## Likely file targets

- `lgwks_seed.py`
- `tests/test_seed_ingest.py`
- `tests/test_seed_continue.py`
- `tests/test_seed_index.py`

## Acceptance

### JEPA-001 (ingest)
1. URL input is crawled and normalized into a seed resource.
2. Repo path input triggers bot fabric run and graph refresh.
3. Inline text input is accepted and normalized.
4. Output package validates as `lgwks.jepa.package.v1`.
5. Same content ingested twice produces the same seed key.

### JEPA-002 (index)
1. Seed index entry written on every ingest.
2. `lgwks seed ls` lists seeds sorted by freshness.
3. Lookup by repo path returns matching seeds.
4. Lookup by key returns exact match.

### JEPA-003 (continuation)
1. `lgwks seed continue` with a valid key loads the package.
2. Changed files since last package are detected and re-scanned.
3. Continuation packet is emitted with `prior_package_id` set.
4. Query text with no matching seed returns structured error with suggest-ingest hint.
