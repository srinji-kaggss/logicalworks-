"""Tests for lgwks_session — markers, summaries, activity parsing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_session as session


def _git(repo_dir: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_dir), *args], check=True, capture_output=True)


def _init_repo() -> Path:
    d = Path(tempfile.mkdtemp())
    _git(d, "init", "--initial-branch=main")
    _git(d, "config", "user.email", "test@example.com")
    _git(d, "config", "user.name", "Test")
    (d / "a.py").write_text("x = 1\n")
    _git(d, "add", "a.py")
    _git(d, "commit", "-m", "initial")
    return d


class TestMarkers(unittest.TestCase):
    def test_marker_roundtrip(self):
        r = _init_repo()
        session._write_marker(r, "begin")
        last = session._last_marker(r)
        self.assertIsNotNone(last)
        self.assertEqual(last["kind"], "begin")
        self.assertEqual(last["repo"], str(r))

    def test_marker_overwrite(self):
        r = _init_repo()
        session._write_marker(r, "begin")
        session._write_marker(r, "end", "done")
        last = session._last_marker(r)
        self.assertEqual(last["kind"], "end")
        self.assertEqual(last["note"], "done")


class TestGitActivity(unittest.TestCase):
    def test_commits_detected(self):
        r = _init_repo()
        (r / "b.py").write_text("y = 2\n")
        _git(r, "add", "b.py")
        _git(r, "commit", "-m", "feat: add b")
        activity = session._git_activity_since(r, None)
        self.assertEqual(len(activity["commits"]), 2)
        subjects = [c["subject"] for c in activity["commits"]]
        self.assertIn("feat: add b", subjects)

    def test_no_commits_since_future(self):
        r = _init_repo()
        activity = session._git_activity_since(r, "2099-01-01T00:00:00Z")
        self.assertEqual(len(activity["commits"]), 0)


class TestSummarize(unittest.TestCase):
    def test_narrative_for_empty(self):
        r = _init_repo()
        activity = {"commits": [], "reflog": [], "branch_ops": [], "worktrees": [str(r)], "stashes": 0, "uncommitted": 0}
        summary = session._summarize_activity(r, activity, [])
        self.assertEqual(summary["narrative"], "No activity detected since last marker.")

    def test_narrative_with_commits(self):
        r = _init_repo()
        activity = {
            "commits": [
                {"sha": "abc1234", "subject": "feat: add foo", "date": "2026-06-02T12:00:00Z"},
                {"sha": "def5678", "subject": "fix: bar bug", "date": "2026-06-02T11:00:00Z"},
            ],
            "reflog": [],
            "branch_ops": [],
            "worktrees": [str(r)],
            "stashes": 0,
            "uncommitted": 0,
        }
        summary = session._summarize_activity(r, activity, [])
        self.assertIn("2 commit(s)", summary["narrative"])
        self.assertEqual(summary["commits"]["verbs"]["feat"], 1)


class TestBeginEnd(unittest.TestCase):
    def test_begin_writes_marker(self):
        r = _init_repo()
        summary = session.session_begin(r)
        self.assertEqual(summary["schema"], "lgwks.session.summary.v0")
        last = session._last_marker(r)
        self.assertEqual(last["kind"], "begin")

    def test_end_writes_marker(self):
        r = _init_repo()
        session.session_begin(r)
        summary = session.session_end(r, "finished tests")
        last = session._last_marker(r)
        self.assertEqual(last["kind"], "end")
        self.assertEqual(last["note"], "finished tests")


if __name__ == "__main__":
    unittest.main()
