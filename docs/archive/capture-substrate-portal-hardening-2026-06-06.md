---
type: Archive
title: lgwks Capture / Substrate / Portal Hardening
description: This slice hardens the operator-facing ingress path and the durable SQLite spine.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# lgwks Capture / Substrate / Portal Hardening

## What changed

This slice hardens the operator-facing ingress path and the durable SQLite spine.

- Added `capture build` / `capture show` as the unified front door over existing deterministic layers.
- Kept `substrate` as the heavy ingest engine instead of rebuilding document parsing from scratch.
- Kept `portal` as the repo-grounded re-entry packet for coding agents.
- Added shared SQLite connection hardening and routed the main durable stores through it.

## Layer map

The intended chain is now:

1. `capture`
   - operator entry point
   - accepts messy target or inline context
   - materializes inline blobs when needed
   - calls `substrate`
   - optionally binds to `portal` when a concrete repo/folder exists

2. `substrate`
   - deterministic ingest and chunk/fact/vector production
   - builds per-run artifacts plus the global fact DB

3. `entity-graph`
   - local structural graph over extracted chunks

4. `portal`
   - turns cleaned intent plus local repo graph into a coding packet
   - candidate relations stay `search`
   - proven repo edges stay `hard`

This preserves one CLI entry while keeping modality-specific execution behind the membrane.

## SQLite hardening rules

All durable SQLite connections should now use the shared connector in `lgwks_sqlite.py`.

Applied pragmas:

- `foreign_keys=ON`
- `busy_timeout=5000`
- `temp_store=MEMORY`
- `journal_mode=WAL`
- `synchronous=NORMAL`

Current layers routed through the shared connector:

- `lgwks_substrate.py`
- `lgwks_entity_graph.py`
- `JarvisDB` in `lgwks`

This is not “performance tuning.” It is baseline correctness for long-lived append/update workloads.

## Product direction

The product wedge remains:

- capture messy human research once
- normalize it deterministically
- generate reusable keys
- later re-enter from code with far less slop

That means we should prefer building on existing seams over replacing them:

- `extract` for file/doc/web reading
- `browser` + `auth_runtime` for hostile portals
- `substrate` for ingest/storage
- `portal` for code-agent re-entry

## Gaps still open

- screenshot/image OCR and layout ingestion
- video/audio transcript and event segmentation
- direct `substrate run -> portal code packet` without re-supplying intent
- richer global idea-bank/project-seed retrieval over capture packets
- model/weight packaging for fully local multimodal ingestion

## OSS leverage call

Do not outsource the control plane.

Use OSS for narrow ingest backends where it clearly beats building:

- OCR/layout
- PDF/document conversion
- speech/video transcript
- local embedding models

But keep these layers inside `lgwks`:

- packet schema
- capture compiler
- relation lifecycle
- repo binding
- portal emission

That is the differentiator.
