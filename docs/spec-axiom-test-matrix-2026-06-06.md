# SPEC - Axiom test matrix IR

Date: 2026-06-06
Status: implementation slice

## Purpose

`lgwks axiom capture --test` proves one command. The next IR step is a deterministic test matrix: multiple
bounded test commands with stable labels, captured as Axiom evidence capsules, replayable from disk.

This is the JVM method-table analogy for tests: a named set of executable checks belongs to one verified
artifact, not to scattered narration.

## Command

```bash
lgwks axiom test-matrix --repo . --file matrix.json --intent "pre-merge verification" --json
```

## Matrix input

Accepted shapes:

```json
{
  "schema": "lgwks.axiom.test_matrix.v0",
  "tests": [
    {"label": "unit", "command": "python -m pytest tests/test_axiom_cli.py -q", "timeout": 30}
  ]
}
```

or a bare list of the same test objects.

## Invariants

- Labels are required, unique, ASCII-safe, and deterministic after normalization.
- Commands are required non-empty strings.
- Timeouts are bounded to `1..3600` seconds.
- Each result captures return code, elapsed seconds, and bounded stdout/stderr tails.
- Matrix output is a normal `lgwks.axiom.harness.v0` packet and must pass `axiom replay`.
- Narration like "tests passed" is true only when at least one captured test exists and all captured tests
  returned `0`.

## Deferred

- Replace shell command strings with typed argv vectors.
- Add policy gates for destructive test commands.
- Add dependency-aware test grouping.
