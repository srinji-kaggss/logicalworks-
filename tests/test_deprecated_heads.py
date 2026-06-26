"""Gate: the killed orchestrator heads stay dead.

Enforces engine/deprecated_heads.py — a head marked `head_killed_boilerplate`
must carry `_DEPRECATED_HEAD = True`; a head marked `deleted` must not import.
This is an additive gate (it can only tighten): it prevents a retired peer
orchestrator from silently coming back to life. Absorption plan + SoT:
engine/DAEMON-ABSORPTION-LOG.md.
"""
from __future__ import annotations

import importlib

import pytest

from engine.deprecated_heads import DEPRECATED_HEADS, ORCHESTRATION_SOT


def test_sot_is_the_daemon():
    assert ORCHESTRATION_SOT == "lgwks_daemon"


@pytest.mark.parametrize("module_name", sorted(DEPRECATED_HEADS))
def test_head_status_is_enforced(module_name: str):
    status = DEPRECATED_HEADS[module_name]["status"]
    if status == "deleted":
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)
    elif status == "head_killed_boilerplate":
        mod = importlib.import_module(module_name)
        assert getattr(mod, "_DEPRECATED_HEAD", False) is True, (
            f"{module_name} is a killed head but missing `_DEPRECATED_HEAD = True`"
        )
    else:  # pragma: no cover - guards the registry vocabulary
        pytest.fail(f"unknown status {status!r} for {module_name}")


def test_every_head_has_an_absorption_target():
    for name, meta in DEPRECATED_HEADS.items():
        assert meta.get("absorb_into"), f"{name} has no daemon absorption target logged"
