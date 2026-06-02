"""Tests for lgwks_review — heuristic scanning, graph impact, action proposals."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_review as review


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


class TestHeuristicScan(unittest.TestCase):
    def test_trivial_assertion(self):
        r = _init_repo()
        (r / "bad.py").write_text("def test_foo():\n    assert 20 == 20\n")
        findings = review._heuristic_scan(r / "bad.py", "bad.py")
        self.assertTrue(any(f.check == "trivial_assertion_ast" for f in findings))

    def test_hardcoded_secret(self):
        r = _init_repo()
        (r / "bad.py").write_text("api_key = 'sk-12345678abcdefgh'\n")
        findings = review._heuristic_scan(r / "bad.py", "bad.py")
        self.assertTrue(any(f.check == "hardcoded_secret" for f in findings))

    def test_bare_except(self):
        r = _init_repo()
        (r / "bad.py").write_text("try:\n    x\nexcept:\n    pass\n")
        findings = review._heuristic_scan(r / "bad.py", "bad.py")
        self.assertTrue(any(f.check == "bare_except" for f in findings))

    def test_clean_file(self):
        r = _init_repo()
        (r / "good.py").write_text("def add(a, b):\n    return a + b\n")
        findings = review._heuristic_scan(r / "good.py", "good.py")
        self.assertEqual(len(findings), 0)


class TestReviewRepo(unittest.TestCase):
    def test_review_detects_staged_changes(self):
        r = _init_repo()
        (r / "bad.py").write_text("assert 1 == 1\n")
        _git(r, "add", "bad.py")
        artifact = review.review_repo(r)
        self.assertIn("bad.py", artifact.files_changed)
        self.assertTrue(any(f.check == "trivial_assertion_ast" for f in artifact.findings))

    def test_review_proposes_actions(self):
        r = _init_repo()
        (r / "bad.py").write_text("assert 1 == 1\n")
        _git(r, "add", "bad.py")
        artifact = review.review_repo(r)
        self.assertTrue(len(artifact.proposed_actions) > 0)
        self.assertTrue(any(a["verb"] == "commit" for a in artifact.proposed_actions))

    def test_review_clean_diff(self):
        r = _init_repo()
        artifact = review.review_repo(r)
        self.assertEqual(len(artifact.findings), 0)
        self.assertTrue(any(a["verb"] == "push" for a in artifact.proposed_actions))


if __name__ == "__main__":
    unittest.main()
