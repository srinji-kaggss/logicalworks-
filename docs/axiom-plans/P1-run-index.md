# P1 - Unified Axiom Run Index

## Goal

Create one index file per Axiom run so capture, matrix, narration, replay, and divergence artifacts are linked
without an agent having to infer paths.

## Why

Today `lgwks axiom capture`, `test-matrix`, and `narrate` write adjacent artifacts, but there is no single
run timeline. This creates CLI experience friction and makes replay/check orchestration harder.

## Files

- Modify: `lgwks_axiom.py`
- Modify: `tests/test_axiom_cli.py`
- Optional docs update: `docs/axiom-end-to-end-framework-2026-06-06.md`

## Data Shape

Write `.lgwks/axiom/runs/<run>/index.json`:

```json
{
  "schema": "lgwks.axiom.run_index.v0",
  "run_id": "axiom-...",
  "root": "...",
  "created_at": "...",
  "artifacts": [
    {"kind": "capture", "path": "packet.json", "schema": "lgwks.axiom.harness.v0"},
    {"kind": "emissions", "path": "emissions.jsonl"},
    {"kind": "fabric_log", "path": "fabric-log.json"},
    {"kind": "narration", "path": "narration.json", "schema": "lgwks.axiom.narration.v0"}
  ]
}
```

## Implementation Steps

1. Add helper `write_run_index(root: Path, run_id: str, artifacts: list[dict]) -> dict`.
2. Call it from `build_capture`.
3. Call it from `build_narration_artifact` when `--run` points at an existing run.
4. Add `lgwks axiom index <run> --json` to print the index.
5. Add manifest metadata for `axiom index`.

## Acceptance Tests

- `build_capture(..., out_dir=out)` writes `out/index.json`.
- `build_narration_artifact(..., run=out)` appends/updates narration artifacts in the same index.
- `./lgwks --machine axiom index <run> --json` returns parseable JSON.
- Existing replay/check tests still pass.

## Do Not Do

- Do not create a global database yet.
- Do not rename existing artifact files.
- Do not move run output outside `.lgwks/axiom/runs/` defaults.

