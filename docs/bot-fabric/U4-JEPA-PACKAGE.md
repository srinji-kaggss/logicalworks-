---
type: Reference
title: U4 — JEPA Package Contract
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:26:16-04:00
---

# U4 — JEPA Package Contract

Status: spec

## Purpose

Define the canonical package that turns raw findings into one machine object.

This is the first real JEPA surface in the bot fabric.

## Inputs

- reduced findings
- repo graph
- world-db bindings
- prior package references
- optional human dump

## Outputs

- `package.json`
- `machine/packet.json`
- `machine/contradictions.json`
- `human/summary.json`
- `index/links.json`

## Package object

Canonical shape:

```json
{
  "schema": "lgwks.jepa.package.v1",
  "package_id": "pkg:lgwks-self-review:abc123",
  "plan_id": "plan:lgwks-self-review",
  "repo": "/Users/srinji/logicalworks-",
  "anchors": [
    {"kind": "file", "id": "lgwks_substrate.py"},
    {"kind": "concept", "id": "hub-module"}
  ],
  "clusters": ["cluster:1", "cluster:2"],
  "contradictions": ["ctr:1"],
  "world_refs": ["wdb:hub-module"],
  "next_actions": [
    "inspect lgwks_substrate.py",
    "review graph cycle around lgwks_graph.py"
  ],
  "synth_ready": true
}
```

## Machine packet

The machine packet is the compact continuation object for AI and later runtime steps.

Must contain:

- package id
- top anchors
- ranked findings
- contradictions
- recommended reads
- recommended commands

## Human projection

The human projection is not prose-first.

Must contain:

- anomaly cards
- top blocks
- drill-down links
- “what changed”
- “what matters now”

## Contradiction handling

Contradictions are first-class package elements, not notes.

Each contradiction record must include:

- subject
- competing evidence refs
- current confidence
- recommended resolution step

## Design constraints

1. one canonical package, many projections
2. package ids are stable and content-linked
3. no projection may invent unsupported claims
4. package must remain useful if the final LLM synth is skipped

## File targets

Likely implementation files:

- `lgwks_jepa.py`
- `lgwks_project_artifacts.py`
- `tests/test_jepa_package.py`

## Acceptance

1. A package can be built from reducer outputs without any LLM.
2. Machine and human projections both derive from the same package.
3. Contradictions are explicit and linkable.
4. The package contains enough next-step structure to continue work without prose synthesis.
