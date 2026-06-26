---
type: Archive
title: JEPA Program Map — 2026-06-06
description: Purpose: give the project a high-level build-down map that can survive backlog churn.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# JEPA Program Map — 2026-06-06

Purpose: give the project a high-level build-down map that can survive backlog churn.

## North star

Reduce intent recovery cost by compiling messy human input into durable machine artifacts, then projecting them back into human and agent workflows.

## Program layers

### Layer 1 — Ingress

Goal:
- user can dump context with near-zero discipline

Tracks:
- `LGW-SEED-*`
- `LGW-STATE-*`

Current focus:
- `LGW-SEED-001` product-facing `seed` surface
- `LGW-SEED-002` seed index and lookup
- `LGW-SEED-003` continuation packet

### Layer 2 — Canonical package

Goal:
- one source of truth for human and machine projections

Tracks:
- `LGW-PKG-*`

Current focus:
- package contract
- resource folder contract
- evidence pack contract
- agent-readable package publishing

### Layer 3 — Control plane

Goal:
- make agent work reviewable, bounded, and resumable

Tracks:
- `LGW-CTRL-*`
- `LGW-RUNTIME-*`

Current focus:
- readiness artifact
- explicit scope
- preview/apply gates
- silent-failure checks
- worktree-isolated continuation shell

### Layer 4 — Visual/operator workbench

Goal:
- show enough distinct context at once that humans can steer without reopening ten chats

Tracks:
- `LGW-VIEW-*`

Current focus:
- dense pane map
- graph drill-down
- change radar
- contradiction view

### Layer 5 — Learned world model

Goal:
- make continuation and intent reconstruction better than token-only replay

Tracks:
- `LGW-ML-*`
- `LGW-EVAL-*`

Current focus:
- ModernBERT router
- package JEPA dataset
- temporal GNN
- controls and ablations

## Recommended milestones

### M1 — Product seed loop

Outcome:
- `seed ingest|continue|refine|show|ls`
- seed index
- continuation packet
- evidence pack

Primary IDs:
- `LGW-SEED-001`
- `LGW-SEED-002`
- `LGW-SEED-003`
- `LGW-PKG-003`
- `LGW-CTRL-002`

### M2 — Safe continuation

Outcome:
- preview mode
- explicit scope
- readiness report
- silent-failure checks

Primary IDs:
- `LGW-CTRL-001`
- `LGW-CTRL-003`
- `LGW-CTRL-004`
- `LGW-RUNTIME-001`

### M3 — Visual workbench

Outcome:
- operator can inspect dense context as panes and maps
- AI gets a machine stream; human gets a visual radar

Primary IDs:
- `LGW-VIEW-001`
- `LGW-VIEW-002`
- `LGW-VIEW-003`

### M4 — Learned routing

Outcome:
- route continuation to the right package/repo/tranche with measurable gains

Primary IDs:
- `LGW-ML-001`
- `LGW-EVAL-001`

### M5 — JEPA research path

Outcome:
- package dataset
- temporal GNN
- proof that latent package alignment beats prompt-only continuation

Primary IDs:
- `LGW-ML-002`
- `LGW-ML-003`
- `LGW-EVAL-002`

## PM struggles to design around

### 1. The backlog becomes a proxy memory system

Bad outcome:
- tickets turn into half-remembered context dumps

Fix:
- tickets should point to packages, evidence packs, and maps

### 2. Priority churn destroys naming

Bad outcome:
- renumbering and relabeling create confusion

Fix:
- stable canonical IDs
- priority as metadata, not identity

### 3. Humans think in narratives, systems need objects

Bad outcome:
- “the thing from yesterday” cannot be resolved

Fix:
- package keys
- project binding
- visual continuation map

### 4. Static tools stay disconnected

Bad outcome:
- the agent keeps rebuilding orchestration logic from scratch

Fix:
- treat proven tools/patterns as reusable building blocks
- compile them into machine contracts instead of rediscovering them in-chat

### 6. One command hides too many untyped decisions

Bad outcome:
- a single continuation verb becomes a black box

Fix:
- keep the user-facing command simple
- decompose the internal path into typed sub-engines and gates

### 5. Too much context becomes visually flat

Bad outcome:
- everything is text, nothing pops

Fix:
- distinct panes
- summaries with drill-down
- map/radar surfaces
