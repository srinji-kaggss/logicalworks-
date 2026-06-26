---
type: Plan
title: Axiom Follow-On Plan Pack
description: Purpose: give a cheaper coding agent small, self-contained tasks after PR 42.
tags: [axiom-plans, plan]
timestamp: 2026-06-06T20:59:55-04:00
---

# Axiom Follow-On Plan Pack

Purpose: give a cheaper coding agent small, self-contained tasks after PR 42.

Current state on `main`:

- `axiom/` is the standalone byte layer: canonical TLV, CID, Capsule, verifier, Fabric.
- `lgwks_axiom.py` is the CLI harness above the byte layer: capture, replay, test-matrix, narrate, check, doctor.
- `lgwks_manifest.py` exposes Axiom commands for agent discovery.

Hard boundary:

- Do not import `lgwks*` from `axiom/`.
- Do not move CLI/test runner/path handling into `axiom/`.
- Do not claim WASM/MLIR lowering is implemented.

Recommended order:

1. `P1-run-index.md`
2. `P2-argv-policy.md`
3. `P3-replay-all.md`
4. `P4-rust-boundary.md`

Verification baseline for every plan:

```bash
uv run --with pytest python -m pytest axiom/tests/ tests/test_axiom_cli.py tests/test_research_stack.py::TestManifest -q
./lgwks --machine axiom doctor --repo . --json
./lgwks manifest --for-agent
```
