# JEPA Ticket Schema — 2026-06-06

Purpose: define a ticket ID scheme that survives reprioritization, regrouping, and future subprojects.

## Problem

Purely sequential IDs like `JEPA-001`, `JEPA-002`, `JEPA-003` are easy to start with but become weak once:

- priorities change
- issues get split or merged
- work moves between product, control-plane, ML, and UX
- the same capability needs frontend, CLI, data, and evaluation slices

We want stable IDs that are:

- easy to sort
- easy to scan
- not coupled to current priority
- reusable across specs, commits, dashboards, and future CLI artifacts

## Canonical format

Use:

```text
LGW-<TRACK>-<NNN>
```

Where:

- `LGW` = product/program prefix
- `TRACK` = stable capability track
- `NNN` = zero-padded sequence within that track

Examples:

- `LGW-SEED-001`
- `LGW-CTRL-004`
- `LGW-VIEW-002`
- `LGW-ML-003`

## Stable tracks

### `SEED`

Human-facing seed/product loop.

Examples:

- ingest
- continue
- refine
- lookup
- project binding

### `PKG`

Canonical package and artifact contract.

Examples:

- machine packet
- human projection
- evidence pack
- resource folder
- package publishing

### `CTRL`

Control plane, safety, readiness, and automation policy.

Examples:

- preview gates
- dry-run
- explicit scope
- readiness
- silent-failure checks

### `STATE`

Session, continuation state, lineage, and resumability.

Examples:

- repo-local state
- continuation history
- forkable continuation
- event ledger

### `VIEW`

Human visual surfaces and drill-down workbenches.

Examples:

- graph view
- dense pane layout
- map view
- operator dashboard

### `ML`

Learned routing, JEPA predictors, temporal GNN, and model-hub work.

Examples:

- ModernBERT router
- package-level JEPA dataset
- temporal GNN
- compaction prediction

### `RUNTIME`

CLI/runtime shell, worktrees, backend seams, and local execution shells.

Examples:

- continuation shell
- mission mode
- sandbox wrapper
- setup compiler

### `EVAL`

Benchmarks, controls, ablations, and scientific validation.

Examples:

- control ladder
- wording-drift benchmark
- token-savings benchmark
- next-action accuracy benchmark

### `REF`

External OSS/reference incorporation and provenance work.

Examples:

- license review
- donor pattern extraction
- translation into `lgwks` terms

## Rules

1. IDs are stable once assigned.
2. Priority is tracked separately from the ID.
3. One ticket can have:
- one canonical ID
- many labels
- one current priority
- one current milestone
4. Splits create child IDs, not renumbering.
5. Merges preserve references to prior IDs in notes.

## Priority should not live in the ID

Use labels or status fields instead:

- `P0`
- `P1`
- `P2`
- `Now`
- `Next`
- `Later`

This lets us re-org without renaming the work.

## Legacy mapping

Current `JEPA-xxx` IDs can remain as historical references.

Going forward:

- new planning docs should prefer canonical `LGW-*` IDs
- old `JEPA-*` items can be mapped gradually as work gets touched

## Initial mapping

- `JEPA-001` -> `LGW-SEED-001`
- `JEPA-002` -> `LGW-SEED-002`
- `JEPA-003` -> `LGW-SEED-003`
- `JEPA-004` -> `LGW-STATE-001`
- `JEPA-005` -> `LGW-EVAL-001`
- `JEPA-010` -> `LGW-ML-001`
- `JEPA-012` -> `LGW-ML-003`
- `JEPA-018` -> `LGW-CTRL-001`
- `JEPA-021` -> `LGW-RUNTIME-001`
- `JEPA-029` -> `LGW-PKG-003`

This is a migration aid, not a full rewrite.
