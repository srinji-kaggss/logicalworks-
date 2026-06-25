---
type: Reference
title: U1 — Bot Record Schema
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:26:16-04:00
---

# U1 — Bot Record Schema

Status: spec

## Purpose

Define the smallest canonical evidence unit emitted by every deterministic bot.

If this unit is weak, every later layer becomes vague:

- reducer cannot cluster reliably
- JEPA cannot bind views cleanly
- synthesizer sees prose instead of facts
- human drill-down breaks

## Output object

Canonical shape:

```json
{
  "schema": "lgwks.bot.record.v1",
  "run_id": "run:2026-06-06:abc123",
  "bot": "graph_anomaly",
  "target": {
    "kind": "file",
    "id": "lgwks_substrate.py"
  },
  "kind": "hub_risk",
  "summary": "high-betweenness transit hub with broad blast radius",
  "severity": "medium",
  "confidence": 0.88,
  "status": "open",
  "evidence": [
    {
      "type": "metric",
      "name": "betweenness",
      "value": 0.074765,
      "unit": "score"
    }
  ],
  "links": {
    "repo": "/Users/srinji/logicalworks-",
    "file": "lgwks_substrate.py",
    "symbol": null,
    "tests": ["tests/test_substrate.py"],
    "artifacts": ["runs/graph/current.json"]
  },
  "world_refs": [
    {
      "kind": "concept",
      "id": "hub-module"
    }
  ],
  "tags": ["graph", "blast-radius", "architecture"],
  "created_at": "2026-06-06T12:00:00Z"
}
```

## Required fields

- `schema`
- `run_id`
- `bot`
- `target.kind`
- `target.id`
- `kind`
- `severity`
- `confidence`
- `status`
- `evidence`
- `links`
- `created_at`

## Enumerations

### Severity

- `info`
- `low`
- `medium`
- `high`
- `critical`

### Status

- `open`
- `confirmed`
- `suppressed`
- `duplicate`
- `resolved`

## Confidence rules

- closed interval `[0.0, 1.0]`
- deterministic bots should prefer calibrated heuristics over fake precision
- if confidence is not meaningful, set a coarse value like `0.25`, `0.5`, `0.75`

## Evidence rules

Every record must contain at least one evidence item.

Allowed evidence types:

- `metric`
- `edge`
- `trace`
- `query`
- `test_output`
- `file_excerpt`
- `history`
- `external_ref`

No bot may emit a finding without attaching drillable evidence.

## Link rules

Links are mandatory because the human and the final synthesizer must both be able to descend from the summary to the proof.

Minimum links:

- one repo-local anchor:
  - file
  - symbol
  - test
  - artifact

## Design constraints

1. one record = one claim
2. no nested prose blobs
3. no implicit severity
4. no free-form “trust me” rationale
5. no cross-record hidden dependency

## File targets

Likely implementation files:

- `docs/schemas/lgwks-bot-record-v1.schema.json`
- `lgwks_project_artifacts.py`
- `tests/test_bot_record_schema.py`

## Acceptance

1. A JSON schema exists and validates canonical records.
2. Invalid severity and confidence values fail closed.
3. A record without evidence fails validation.
4. A record without drill-down links fails validation.
5. The schema is simple enough for every bot lane to reuse unchanged.
