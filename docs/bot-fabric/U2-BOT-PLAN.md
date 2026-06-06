# U2 — Bot Plan Schema

Status: spec

## Purpose

Define the declarative run contract for a bot-fabric analysis.

This is the terraform-like entrypoint:

- target repo
- selected bot lanes
- runtime policy
- output roots
- budget/gating knobs

## Output object

Canonical shape:

```json
{
  "schema": "lgwks.bot.plan.v1",
  "plan_id": "plan:lgwks-self-review",
  "run_kind": "review",
  "target_repo": "/Users/srinji/logicalworks-",
  "world_db_mode": "bind",
  "bots": [
    {"name": "graph_anomaly", "enabled": true},
    {"name": "code_hacker", "enabled": true},
    {"name": "optimizer", "enabled": true}
  ],
  "jepa": {
    "enabled": true,
    "mode": "deterministic_package"
  },
  "synth": {
    "enabled": true,
    "provider": "reasoning",
    "optional": true
  },
  "policy": {
    "allow_external_research": false,
    "branch_state_mode": "shared",
    "max_artifact_bytes": 5000000
  },
  "outputs": {
    "root": "runs/lgwks-self-review",
    "machine": "runs/lgwks-self-review/machine",
    "human": "runs/lgwks-self-review/human"
  }
}
```

## Required fields

- `schema`
- `plan_id`
- `run_kind`
- `target_repo`
- `bots`
- `jepa.enabled`
- `synth.enabled`
- `policy`
- `outputs.root`

## Enumerations

### Run kinds

- `review`
- `research`
- `continue`
- `stress`
- `optimize`

### World DB mode

- `bind`
- `readonly`
- `skip`

### Branch state mode

- `shared`
- `per_branch`

## Rules

1. Bot names must come from a fixed registry.
2. Unknown bot names fail closed.
3. The plan is declarative; it does not carry executable code.
4. JEPA and synth toggles are explicit.
5. External research is opt-in, not implied.

## File targets

Likely implementation files:

- `docs/schemas/lgwks-bot-plan-v1.schema.json`
- `lgwks_project_artifacts.py`
- `tests/test_bot_plan_schema.py`

## Acceptance

1. Invalid bot names fail validation.
2. Missing output roots fail validation.
3. A plan can be loaded and inspected without network access.
4. A plan fully determines what the runtime may attempt.
