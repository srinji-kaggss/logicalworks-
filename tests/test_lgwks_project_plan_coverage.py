"""Tests for lgwks_project_plan module coverage."""

from __future__ import annotations

import argparse

from lgwks_project_plan import build_plan, worker_cap


def test_worker_cap_returns_computed_cap():
    """worker_cap() returns a dict with a computed_cap key that is an int >= 1."""
    result = worker_cap()
    assert "computed_cap" in result
    assert isinstance(result["computed_cap"], int)
    assert result["computed_cap"] >= 1


def test_build_plan_real_shape():
    """build_plan() with specific args returns expected shape."""
    args = argparse.Namespace(
        project="demo",
        prompt="test prompt",
        reasoning_cycles=None,
        embedding_rounds=50,
        max_workers=2,
        tokens_per_cycle=5000,
        site="open-public-sources",
        folder=".",
    )
    result = build_plan(args)

    assert result["project"] == "demo"
    assert result["prompt"] == "test prompt"
    assert result["budgets"]["embedding_rounds"] == 50
    assert result["budgets"]["max_workers"] == 2
    assert "plan_id" in result
    assert isinstance(result["plan_id"], str)
    assert result["plan_id"]  # truthy (non-empty string)
    assert len(result["branch_workers"]) == 2
