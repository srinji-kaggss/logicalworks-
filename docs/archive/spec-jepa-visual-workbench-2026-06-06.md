# SPEC — JEPA Visual Workbench (v0)

Status: planning only

Purpose: define the human visual surface that complements the machine packet.

## Problem

Large context dumps become visually flat inside chat.

The human need is:

- flood the screen with distinct signals
- keep them separable
- allow drill-down on demand
- avoid re-reading giant prose blocks

## Product promise

```text
one package
many visual slices
fast drill-down
no need to rehydrate the full chat to remember what matters
```

## Design reference direction

This is inspired by the useful behavior of dense terminals like `gloomberb`, not by finance semantics or visual branding.

Useful pattern from `gloomberb`:

- many distinct panes visible at once
- strong keyboard navigation
- command bar as primary jump surface
- drill-down from overview to detail
- plugin-style extensibility

Source:
- https://github.com/vincelwt/gloomberb

Useful pattern from `syswatch`:

- multi-tab observability replacing many disconnected tools
- replayable session timeline
- plain-English anomaly cards layered over raw signals

Source:
- https://github.com/matthart1983/syswatch

## Core workbench panes

### 1. Seed radar

Shows:

- recent seeds
- candidate project bindings
- confidence
- contradiction count
- freshness

### 2. Package graph

Shows:

- anchors
- linked resources
- related repos
- prior continuations
- promoted outcomes

### 3. Change radar

Shows:

- repo files changed since last continuation
- new external sources
- stale bindings
- failed refreshes

### 4. Action lane

Shows:

- recommended next actions
- blocked items
- preview-required actions
- current readiness level

### 5. Contradiction lane

Shows:

- changed assumptions
- conflicting views
- unverified claims
- human corrections

### 6. Evidence drawer

Shows:

- sources
- extracted snippets
- test outputs
- review artifacts

### 7. Anomaly cards

Shows:

- stale binding detected
- crawl failed or degraded
- contradiction density spike
- risky continuation requires preview
- branch-local state drift

## Interaction model

### Overview first

Start with a dense map, not a prose summary.

### Command jump

One command bar should jump to:

- seed
- repo
- package
- resource
- contradiction
- ticket

### Drill-down second

Every pane should open into:

- machine packet
- human explanation
- raw evidence

### Replay and scrub

The workbench should support session/package replay:

- scrub recent refreshes
- inspect prior continuation states
- compare "then vs now" for the same package

## Relationship to the machine package

The workbench is not a second source of truth.

Rules:

1. machine package remains canonical
2. visual panes are projections
3. every visual element should map back to a stable machine object
4. “pretty but unverifiable” is a failure mode

## Future CLI implications

The visual workbench suggests future commands:

- `lgwks seed map`
- `lgwks seed radar`
- `lgwks seed graph`
- `lgwks seed changes`
- `lgwks seed readiness`
- `lgwks seed replay`
- `lgwks seed anomalies`

## PM/operator notes

This surface exists to solve a real PM problem:

- too many partially formed initiatives
- too many moving dependencies
- too much context hidden in prose

The visual workbench should let a human operator answer:

- what changed?
- what matters now?
- what is risky?
- what is blocked?
- what should the AI do next?

without reading a 250k-token transcript again.
