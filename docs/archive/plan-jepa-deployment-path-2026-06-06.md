---
type: Archive
title: JEPA Deployment Path — 2026-06-06
description: Build down from thesis to working product without pretending the full JEPA learner already exists.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# JEPA Deployment Path — 2026-06-06

## Goal

Build down from thesis to working product without pretending the full JEPA learner already exists.

## Phase 0 — Foundation

Status: partially complete

Shipped / shipping:

- `capture`
- `portal`
- `jepa` runtime package
- ML doctor surfaces
- scientific approach doc

Exit criteria:

- package exists
- machine/human projections exist
- repo binding exists
- readiness gaps are explicit

## Phase 1 — Product seed surface

Objective:

Expose a human-facing package flow that assumes low discipline.

Build:

- `lgwks seed ingest`
- `lgwks seed continue`
- `lgwks seed refine`
- `lgwks seed show`
- `lgwks seed ls`

Exit criteria:

- user can dump context without choosing storage layout
- package gets created and indexed
- continuation path can resolve a prior package against repo state

## Phase 2 — Continuation stream

Objective:

Replace chat archaeology with a compact technical stream for coding agents.

Build:

- seed-to-portal resolver
- changed-file/repo-refresh pass
- compact AI stream packet
- human fit summary packet

Exit criteria:

- continuation starts from package + repo graph
- not from rereading long chats

## Phase 3 — Benchmark harness

Objective:

Prove the product loop is better than raw prompt continuation.

Build:

- fixed task set
- control ladder (`C0`, `C1`, `T1`, `T2`)
- metrics:
  - top-k file recall
  - next-command accuracy
  - contradiction recall
  - token cost
  - time to useful action

Exit criteria:

- measurable win on `H1`, `H2`, or `H5`

## Phase 4 — Learned router

Objective:

Promote the first trained discriminative layer.

Build:

- ModernBERT router
- package classification / continuation routing
- paraphrase/slop robustness evaluation

Exit criteria:

- better than deterministic baseline
- calibrated abstention

## Phase 5 — Package-level JEPA predictor

Objective:

Train the first latent multi-view predictor over canonical packages.

Build:

- package dataset
- view pairing protocol
- latent alignment objective
- package-next-state prediction

Exit criteria:

- improves continuation and routing under wording drift

## Phase 6 — Temporal GNN

Objective:

Learn the transition graph:

```text
seed/jepa -> portal -> command -> outcome -> contradiction/update
```

Build:

- event schema
- graph dataset
- next-action learner
- contradiction-aware scoring

Exit criteria:

- beats heuristic scheduler on next useful action

## Phase 7 — Full research branch

Objective:

Decide whether full LLM-JEPA fine-tuning is justified.

Gate:

- only after the package-level predictor and temporal graph path show clear value

Reason:

- otherwise we would be adding training complexity without proving the systems thesis first
