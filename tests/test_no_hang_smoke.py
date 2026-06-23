"""Smoke guards that exercise the REAL path — explicitly WITHOUT LGWKS_NO_MODELS.

The `review` hang (2026-06-23) survived because every model-touching test sets
LGWKS_NO_MODELS=1, so the path real agents use was never run. These tests do the
opposite: invoke the binary as a cold agent would (flag UNSET) under an outer
deadline, asserting the CLI *returns* (degrades) instead of hanging. They are the
missing CI guard — if a model/embed/reason sink loses its bound again, one of
these trips instead of staying green.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import lgwks_substrate_config as cfg

_ROOT = Path(__file__).resolve().parent.parent
_LGWKS = _ROOT / "lgwks"


def _run(args, timeout):
    env = {k: v for k, v in os.environ.items() if k != "LGWKS_NO_MODELS"}
    env.pop("LGWKS_NO_MODELS", None)  # the whole point: real path, models allowed
    return subprocess.run(
        [sys.executable, str(_LGWKS), *args],
        capture_output=True, text=True, timeout=timeout, env=env, cwd=str(_ROOT),
    )


class TestExclusionBaseLocked(unittest.TestCase):
    def test_base_skip_dirs_excludes_site_packages(self):
        # locks the second root cause: pipeline/substrate_io/embed/codebase all
        # inherit this; without site-packages a vendored venv hangs them.
        self.assertIn("site-packages", cfg.SKIP_DIRS)


class TestRealPathDoesNotHang(unittest.TestCase):
    def test_review_changed_returns_without_hang(self):
        # the exact original failure: `lgwks review` with models enabled must
        # complete (it ast-parses the bot path that used to spin on .venv-models)
        try:
            proc = _run(["review", "--changed", "tests/test_repo_scan.py", "--json"], timeout=120)
        except subprocess.TimeoutExpired:
            self.fail("`lgwks review --changed` HUNG (>120s) — review-hang regressed")
        self.assertIn(proc.returncode, (0, 2), proc.stderr[-400:])
        self.assertTrue(proc.stdout.strip(), "review produced no stdout")
        json.loads(proc.stdout)  # must be a clean machine packet, not chatter

    def test_agent_door_executes_without_hang(self):
        try:
            proc = _run(["agent", "doctor", "--act"], timeout=90)
        except subprocess.TimeoutExpired:
            self.fail("`lgwks agent doctor --act` HUNG (>90s)")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        env = json.loads(proc.stdout)  # clean lgwks.agent.v1 envelope (S6)
        self.assertEqual(env.get("schema"), "lgwks.agent.v1")
        self.assertTrue(env.get("executed"))


if __name__ == "__main__":
    unittest.main()
