"""Coverage tests for lgwks_proc — backfill #349.

Human-completed: the forge fan-out trial on this module failed (the model
hallucinated an unrelated absolute shell cwd, stalled on convergence, hit
max_steps with zero edits — tracked as a failure, not silently redone).
"""

from __future__ import annotations

from pathlib import Path

import lgwks_proc


def test_is_git_repo_true_for_real_repo():
    assert lgwks_proc.is_git_repo(Path(__file__).resolve().parents[1]) is True


def test_is_git_repo_false_for_non_repo(tmp_path):
    assert lgwks_proc.is_git_repo(tmp_path) is False


def test_run_git_status_succeeds_on_real_repo():
    rc, _ = lgwks_proc.run_git(Path(__file__).resolve().parents[1], "status")
    assert rc == 0
