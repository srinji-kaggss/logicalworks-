# U3 — Deterministic Reducer

Status: spec

## Purpose

Take many bot records and turn them into a compact, ranked, deduped evidence pack.

This is the anti-noise layer before JEPA and before any LLM synthesis.

## Inputs

- `bot-records.jsonl`
- optional repo graph metrics
- optional historical package fingerprints

## Outputs

- `findings.normalized.jsonl`
- `clusters.json`
- `anomaly-cards.json`
- `review-packet.json`

## Pipeline

### Step 1 — Normalize

- canonicalize paths
- canonicalize symbol ids
- normalize severity/confidence scales
- assign stable record ids

### Step 2 — Deduplicate

Duplicate criteria:

- same `kind`
- same `target`
- equivalent primary evidence

Merge behavior:

- preserve all evidence references
- keep highest severity
- merge tags
- keep provenance of contributing bots

### Step 3 — Cluster

Cluster axes:

- file
- symbol
- subsystem
- failure theme
- world-db concept

### Step 4 — Rank

Rank using deterministic signals:

- severity
- confidence
- blast radius
- contradiction density
- recurrence across bots

### Step 5 — Emit anomaly cards

Each card is a compact human/operator object:

- title
- severity
- why it matters
- top drill-down links

## Review packet contract

Must include:

- top findings
- clusters
- open contradictions
- recommended next reads
- recommended next commands

## Design constraints

1. no LLM calls
2. no hidden heuristics without tests
3. reducer output must be reproducible
4. reducer must remain useful if JEPA/synth are disabled

## File targets

Likely implementation files:

- `lgwks_project_artifacts.py`
- `lgwks_review.py`
- `tests/test_bot_reducer.py`

## Acceptance

1. Duplicate findings collapse deterministically.
2. Cluster output is stable between runs on the same inputs.
3. Review packet contains enough ranked structure for a human to act without synthesis.
4. Anomaly cards point to valid drill-down links.
