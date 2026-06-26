---
type: Plan
title: P3 - Replay All Axiom Artifacts
description: Extend replay to cover both capture emissions and narration emissions.
tags: [axiom-plans, plan]
timestamp: 2026-06-06T20:59:55-04:00
---

# P3 - Replay All Axiom Artifacts

## Goal

Extend replay to cover both capture emissions and narration emissions.

## Why

`axiom replay` currently replays `emissions.jsonl` and compares `fabric-log.json`. Narration writes
`narration-emissions.jsonl`, but replay does not yet treat it as part of a full run.

## Files

- Modify: `lgwks_axiom.py`
- Modify: `tests/test_axiom_cli.py`
- Depends on: `P1-run-index.md` if available, but can be implemented standalone.

## Behavior

```bash
lgwks axiom replay <run> --all --json
```

Returns:

```json
{
  "schema": "lgwks.axiom.replay_all.v0",
  "ok": true,
  "artifacts": [
    {"kind": "capture", "ok": true, "path": "emissions.jsonl"},
    {"kind": "narration", "ok": true, "path": "narration-emissions.jsonl"}
  ]
}
```

## Implementation Steps

1. Keep existing `replay_emissions(path)` unchanged for single streams.
2. Add `replay_run(root: Path) -> dict`.
3. If `index.json` exists, use it; otherwise detect known filenames.
4. Add `--all` flag to `axiom replay`.
5. Add tests for tampered narration emission.

## Acceptance Tests

- Capture + narrate run passes `axiom replay <run> --all`.
- Tampering `narration-emissions.jsonl` fails.
- Existing `axiom replay <run>` behavior remains backward-compatible.

## Do Not Do

- Do not combine capture and narration into one fabric yet.
- Do not delete or rewrite old emission files.
