---
type: Reference
title: U6 — Slop Math Bot Set
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:43:25-04:00
---

# U6 — Slop Math Bot Set

Status: spec

## Purpose

Implement deterministic structural bots that detect AI-slop-adjacent problems without using an LLM.

This set should emit precise records, not vague “quality” judgments.

## Sub-bots

### S1 — Graph anomaly bot

Goal:

- detect hub risk
- long chains
- unstable hotspots
- cycles

Primary sources:

- `lgwks graph --complexity`
- `lgwks graph --patterns`
- repo graph cache

Kinds emitted:

- `hub_risk`
- `cycle_risk`
- `long_chain`
- `instability_hotspot`

### S2 — Naming / binning bot

Goal:

- detect multiple names for one concept
- detect one overloaded term used for many concepts
- detect dangerous synonym drift against canonical docs/specs

Kinds emitted:

- `naming_drift`
- `concept_binning`
- `term_overload`

### S3 — Spec drift bot

Goal:

- compare implementation surfaces against spec/schema/manifest/doc claims

Kinds emitted:

- `spec_code_drift`
- `manifest_drift`
- `undocumented_surface`

### S4 — Proof gap bot

Goal:

- find claims that lack tests, links, evidence, or validation surfaces

Kinds emitted:

- `proof_gap`
- `test_gap`
- `unbacked_claim`

### S5 — Dead abstraction bot

Goal:

- detect nouns, layers, or helpers that add indirection without evidence of value

Kinds emitted:

- `dead_abstraction`
- `unused_layer`
- `duplicate_surface`

### S6 — Contradiction bot

Goal:

- detect incompatible claims across docs, schema, code comments, and artifact contracts

Kinds emitted:

- `contradiction`
- `stale_assumption`

## Shared output rules

All sub-bots emit `lgwks.bot.record.v1`.

Shared tags:

- `graph`
- `spec`
- `proof`
- `naming`
- `contradiction`
- `abstraction`

## Ranking hints for reducer

The reducer should treat the following as stronger signals:

- repeated findings across multiple sub-bots
- graph anomaly + proof gap on the same target
- contradiction + spec drift on the same concept

## Design constraints

1. no prose summaries beyond one-line record summaries
2. all findings must anchor to repo-local drill-downs
3. all sub-bots must run independently
4. each sub-bot should be callable separately for cheaper runs

## Likely file targets

- `lgwks_graph.py`
- `lgwks_review.py`
- or split files:
  - `lgwks_bot_graph_anomaly.py`
  - `lgwks_bot_spec_drift.py`
  - `lgwks_bot_contradiction.py`
- `tests/test_bot_slop_math.py`

## Acceptance

1. Each sub-bot can run independently.
2. Cycle and long-chain findings are emitted from seeded graph fixtures.
3. Spec drift can be detected against seeded schema/doc mismatches.
4. Proof gap bot detects claims with no linked tests/evidence.
5. Contradiction bot emits structured contradiction records, not prose.
