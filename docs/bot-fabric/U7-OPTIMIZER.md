---
type: Reference
title: U7 — Optimizer Bot
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T13:13:23-04:00
---

# U7 — Optimizer Bot

Status: spec

## Purpose

Detect structural inefficiency in the codebase: god modules, split candidates, token-waste
indicators, and reuse opportunities. No LLM. No opinions. Math-only findings.

## Trigger

Fires automatically via git hook or file-watch on any changed `.py` file.
CLI invocation is the manual override path.

## Inputs

- repo path
- optional changed-files list (subset mode)
- repo graph cache (from `lgwks_graph.get_graph`)

## Outputs

- `findings/optimizer.jsonl`

Every line must validate as `lgwks.bot.record.v1`.

## Detection families

### O1 — God module

Flag any file where:
- in-degree or out-degree > 3× repo average (already in `detect_patterns`)
- betweenness centrality > 0.1 (gatekeeper)
- file line count > 500

Evidence: degree counts, betweenness score, line count.

### O2 — Split candidate

Flag any file where:
- line count > 350 AND defines > 8 public symbols
- OR multiple disjoint responsibility clusters detectable from symbol names
  (e.g. `build_*` + `validate_*` + `run_*` all in one file)

Evidence: line count, public symbol count, symbol name clusters.

### O3 — Token-waste indicator

Flag:
- duplicate `import` blocks (same module imported in 5+ files when a shared re-export exists)
- re-implemented utility patterns already present elsewhere in the repo
  (detected via symbol-name overlap across files, threshold ≥ 0.8 Jaccard on stems)
- dead parameters: public function signatures with parameters never referenced in callers

Evidence: duplication count, overlap score, unreferenced param names.

### O4 — Reuse candidate

Flag any function/class that:
- appears in 3+ files with > 0.85 name-stem similarity
- is not already in a shared module

Evidence: file list, similarity score, suggested consolidation target.

## Severity mapping

- `high`: god module with betweenness > 0.15 or file > 800 lines
- `medium`: split candidate or significant token waste
- `low`: reuse candidate or mild duplication
- `info`: structural observation without clear action

## Confidence mapping

- `0.9`: line count + degree threshold both exceeded
- `0.7`: one threshold exceeded or heuristic match
- `0.5`: symbol-name cluster detection (pattern-based)

## Design constraints

1. no LLM calls
2. no internet dependency
3. graph cache must be loaded before run — emit `analyzer_failure` record if unavailable
4. changed-file subset must still produce valid records (no whole-repo assumption)
5. emit recklessly — do not suppress marginal findings; the reducer filters

## Likely file targets

- `lgwks_bot_optimizer.py`
- `tests/test_bot_optimizer.py`

## Acceptance

1. God modules detected from seeded graph fixtures.
2. Split candidates flagged from seeded oversized files.
3. Token-waste duplicates detected from seeded fixture with repeated symbol names.
4. All records validate as `lgwks.bot.record.v1`.
5. Bot runs on changed-file subset without requiring full repo scan.
6. Missing graph cache emits `analyzer_failure`, not a crash.
