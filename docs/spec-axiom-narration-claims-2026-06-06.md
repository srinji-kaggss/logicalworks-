# SPEC - Axiom narration claims IR

Date: 2026-06-06
Status: implementation slice

## Purpose

`lgwks axiom check --claim "tests passed"` originally accepted free text and applied keyword heuristics.
That proved the radar side could read captured emissions, but the narration side was still stringly.

This slice turns narration into typed IR:

```text
raw narration -> NarrationClaim[] or Hole[] -> Axiom capsules -> divergence check
```

## Command

```bash
lgwks axiom narrate --claim "tests passed" --run .lgwks/axiom/runs/<id> --json
```

## Claim Schema

```json
{
  "schema": "lgwks.axiom.narration.v0",
  "claims": [
    {
      "kind": "tests_passed",
      "source": "tests passed",
      "requires": ["test:returncode=0:all"],
      "confidence": 1.0
    }
  ],
  "holes": []
}
```

Supported claim kinds in v0:

- `tests_passed`
- `worktree_clean`
- `files_changed`
- `work_implemented`

Unknown narration becomes a Hole, not a guessed claim.

## Invariants

- Narration claims are data, not authority.
- Unknown claims produce Holes with `grants=∅` and `needs=∅`.
- Typed claims can be persisted as Axiom capsules and replayed.
- `axiom check` accepts either raw `--claim` text or typed `--claims` JSON.
- Divergence evaluates typed claim kinds against captured emissions, not prose.

## Deferred

- Human-authored claim files with signatures.
- Rich grammar or ML classifier for narration parsing.
- Promoting claim kinds into core `axiom.KINDS`; keep them harness-layer for now.
