"""
Tests for lgwks.bot.plan.v1 schema validation.

Spec: docs/bot-fabric/U2-BOT-PLAN.md
Acceptance:
  1. Invalid bot names fail validation.
  2. Missing output roots fail validation.
  3. A plan can be loaded and inspected without network access.
  4. A plan fully determines what the runtime may attempt.
"""

import json
from pathlib import Path

import lgwks_project_artifacts as artifacts

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "schemas" / "lgwks-bot-plan-v1.schema.json"


def _canonical_plan(**overrides) -> dict:
    base = {
        "schema": "lgwks.bot.plan.v1",
        "plan_id": "plan:lgwks-self-review",
        "run_kind": "review",
        "target_repo": "/Users/srinji/logicalworks-",
        "world_db_mode": "bind",
        "bots": [
            {"name": "graph_anomaly", "enabled": True},
            {"name": "code_hacker", "enabled": True},
            {"name": "optimizer", "enabled": True},
        ],
        "jepa": {"enabled": True, "mode": "deterministic_package"},
        "synth": {"enabled": True, "provider": "reasoning", "optional": True},
        "policy": {
            "allow_external_research": False,
            "branch_state_mode": "shared",
            "max_artifact_bytes": 5_000_000,
        },
        "outputs": {
            "root": "runs/lgwks-self-review",
            "machine": "runs/lgwks-self-review/machine",
            "human": "runs/lgwks-self-review/human",
        },
    }
    base.update(overrides)
    return base


# -- acceptance 1: invalid bot names fail validation -----------------------

def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"schema file not found at {SCHEMA_PATH}"


def test_schema_is_valid_json():
    payload = json.loads(SCHEMA_PATH.read_text())
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert payload["title"] == "lgwks.bot.plan.v1"


def test_known_bot_passes():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan())
    assert ok, errs
    assert errs == []


def test_unknown_bot_fails():
    plan = _canonical_plan()
    plan["bots"].append({"name": "skynet", "enabled": True})
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("skynet" in e for e in errs)


def test_custom_registry_allows_extension():
    ok, errs = artifacts.validate_bot_plan(
        _canonical_plan(bots=[{"name": "skynet", "enabled": True}]),
        known_bots={"skynet"},
    )
    assert ok, errs


# -- acceptance 2: missing output roots fail validation ------------------

def test_missing_outputs_fails():
    plan = _canonical_plan()
    del plan["outputs"]
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("outputs" in e for e in errs)


def test_outputs_without_root_fails():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan(outputs={"machine": "m"}))
    assert not ok
    assert any("root" in e for e in errs)


def test_outputs_with_root_passes():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan(outputs={"root": "runs/x"}))
    assert ok, errs


# -- acceptance 3: plan can be loaded without network access ---------------

def test_plan_is_pure_data():
    plan = _canonical_plan()
    # No function objects, no closures, no network handles.
    assert all(not callable(v) for v in plan.values())
    # Can round-trip through JSON.
    assert json.loads(json.dumps(plan)) == plan


def test_validator_is_stdlib_only():
    import inspect

    src = inspect.getsource(artifacts.validate_bot_plan)
    assert "jsonschema" not in src


# -- acceptance 4: plan fully determines runtime policy --------------------

def test_run_kinds():
    for rk in ["review", "research", "continue", "stress", "optimize"]:
        ok, errs = artifacts.validate_bot_plan(_canonical_plan(run_kind=rk))
        assert ok, errs

    ok, errs = artifacts.validate_bot_plan(_canonical_plan(run_kind="deploy"))
    assert not ok
    assert any("deploy" in e for e in errs)


def test_world_db_modes():
    for mode in ["bind", "readonly", "skip"]:
        ok, errs = artifacts.validate_bot_plan(_canonical_plan(world_db_mode=mode))
        assert ok, errs

    ok, errs = artifacts.validate_bot_plan(_canonical_plan(world_db_mode="write"))
    assert not ok
    assert any("write" in e for e in errs)


def test_branch_state_modes():
    for mode in ["shared", "per_branch"]:
        plan = _canonical_plan()
        plan["policy"]["branch_state_mode"] = mode
        ok, errs = artifacts.validate_bot_plan(plan)
        assert ok, errs

    plan = _canonical_plan()
    plan["policy"]["branch_state_mode"] = "global"
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("global" in e for e in errs)


def test_external_research_opt_in():
    plan = _canonical_plan()
    ok, errs = artifacts.validate_bot_plan(plan)
    assert ok, errs
    assert not plan["policy"]["allow_external_research"]


def test_max_artifact_bytes_non_negative():
    plan = _canonical_plan()
    plan["policy"]["max_artifact_bytes"] = -1
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("max_artifact_bytes" in e for e in errs)


def test_jepa_enabled_required():
    plan = _canonical_plan()
    del plan["jepa"]["enabled"]
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("jepa.enabled" in e for e in errs)


def test_synth_enabled_required():
    plan = _canonical_plan()
    del plan["synth"]["enabled"]
    ok, errs = artifacts.validate_bot_plan(plan)
    assert not ok
    assert any("synth.enabled" in e for e in errs)


def test_empty_bots_fails():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan(bots=[]))
    assert not ok
    assert any("bots" in e.lower() for e in errs)


def test_bots_entry_must_have_name_and_enabled():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan(bots=[{"enabled": True}]))
    assert not ok
    assert any("name" in e for e in errs)

    ok, errs = artifacts.validate_bot_plan(_canonical_plan(bots=[{"name": "graph_anomaly"}]))
    assert not ok
    assert any("enabled" in e for e in errs)


def test_schema_discriminator_enforced():
    ok, errs = artifacts.validate_bot_plan(_canonical_plan(schema="wrong"))
    assert not ok
    assert any("lgwks.bot.plan.v1" in e for e in errs)
