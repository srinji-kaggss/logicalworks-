---
type: Plan
title: P4 - Rust Boundary Plan
description: Define when and how Axiom moves from Python to Rust without prematurely slowing CLI iteration.
tags: [axiom-plans, plan]
timestamp: 2026-06-06T20:59:55-04:00
---

# P4 - Rust Boundary Plan

## Goal

Define when and how Axiom moves from Python to Rust without prematurely slowing CLI iteration.

## Current Answer

Python is correct for the harness right now. Rust is likely correct for the byte verifier later.

## Why Python Now

- `lgwks` is already a Python CLI with many existing modules.
- The current work is harness-heavy: git, subprocess, JSON artifacts, CLI UX, manifests, tests.
- Python makes the IR shape cheap to iterate while the vocabulary is still changing.
- The Axiom byte layer is intentionally stdlib-only and isolated, so it can be ported later.

## Why Not Rust Yet

- The core schema is not stable enough.
- Rewriting early would freeze the wrong abstractions.
- Most current bugs are product-boundary bugs, not CPU/performance bugs.
- The hardest current work is deciding artifact semantics, not optimizing varint decode.

## What Should Become Rust

Candidate crate after schema stabilizes:

```text
axiom-core
  varint
  wire
  cid
  capsule decode/encode
  verifier
  fabric log verification
```

Python should remain:

```text
lgwks_axiom.py
  CLI parsing
  git/test capture
  file paths
  run index
  manifest
  UX
```

## Migration Trigger

Move byte core to Rust when all are true:

- `Capsule` field schema has survived at least two more PRs.
- `axiom replay` is stable and used by other commands.
- Test matrix and narration IR no longer need schema churn every session.
- A second consumer wants the byte verifier outside Python.

## Interop Shape

Preferred:

```bash
axiom-core verify-capsule --bytes-hex ...
axiom-core replay --emissions emissions.jsonl
```

Then Python calls the binary and preserves CLI UX.

Avoid first:

- PyO3 bindings.
- Rust rewrite of the whole CLI.
- Mixed ownership of path/git/subprocess behavior.

## Acceptance For First Rust Slice

- Rust binary verifies all current `axiom/tests` fixture bytes.
- Python and Rust produce identical CIDs for the same capsules.
- Existing Python tests still pass.
