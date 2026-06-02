"""Tests for lgwks_repo — audit, recover, cleanup, handoff, graph.

Uses isolated temp repos so no mutation of the real logicalworks- repo.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_repo as repo


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


class TestAudit(unittest.TestCase):
    def test_clean_repo(self):
        r = _init_repo()
        findings, health = repo.repo_audit(r)
        self.assertFalse(any(f.severity == "danger" for f in findings))
        self.assertEqual(health["uncommitted"], 0)
        self.assertEqual(health["dangling_commits"], 0)
        self.assertEqual(health["stashes"], 0)

    def test_uncommitted_changes(self):
        r = _init_repo()
        (r / "a.py").write_text("x = 2\n")
        findings, health = repo.repo_audit(r)
        self.assertTrue(any(f.check == "uncommitted" for f in findings))
        self.assertEqual(health["uncommitted"], 1)

    def test_dangling_commit(self):
        r = _init_repo()
        _git(r, "checkout", "-b", "temp")
        (r / "b.py").write_text("y = 1\n")
        _git(r, "add", "b.py")
        _git(r, "commit", "-m", "temp")
        _git(r, "checkout", "main")
        _git(r, "branch", "-D", "temp")
        findings, health = repo.repo_audit(r)
        self.assertTrue(any(f.check == "dangling" for f in findings))
        self.assertEqual(health["dangling_commits"], 1)

    def test_stash_found(self):
        r = _init_repo()
        (r / "a.py").write_text("x = 2\n")
        _git(r, "stash", "push", "-m", "wip")
        findings, health = repo.repo_audit(r)
        self.assertTrue(any(f.check == "stashes" for f in findings))
        self.assertEqual(health["stashes"], 1)


class TestRecover(unittest.TestCase):
    def test_recover_dry_run(self):
        r = _init_repo()
        _git(r, "checkout", "-b", "temp")
        (r / "lost.py").write_text("z = 1\n")
        _git(r, "add", "lost.py")
        _git(r, "commit", "-m", "temp")
        _git(r, "checkout", "main")
        _git(r, "branch", "-D", "temp")
        groups, extracted = repo.repo_recover(r, dry_run=True)
        self.assertTrue(any("lost.py" in g.files for g in groups))
        self.assertEqual(len(extracted), 0)

    def test_recover_extract(self):
        r = _init_repo()
        _git(r, "checkout", "-b", "temp")
        (r / "lost.py").write_text("z = 1\n")
        _git(r, "add", "lost.py")
        _git(r, "commit", "-m", "temp")
        _git(r, "checkout", "main")
        _git(r, "branch", "-D", "temp")
        groups, extracted = repo.repo_recover(r, dry_run=False)
        self.assertIn("lost.py", extracted)
        self.assertTrue((r / "lost.py").exists())
        self.assertEqual((r / "lost.py").read_text(), "z = 1\n")


class TestCleanup(unittest.TestCase):
    def test_cleanup_deletes_merged_branch(self):
        r = _init_repo()
        _git(r, "checkout", "-b", "feat")
        (r / "b.py").write_text("y = 1\n")
        _git(r, "add", "b.py")
        _git(r, "commit", "-m", "feat")
        _git(r, "checkout", "main")
        _git(r, "merge", "--no-ff", "feat", "-m", "merge feat")
        result = repo.repo_cleanup(r)
        self.assertTrue(any("deleted branch feat" in a for a in result["actions"]))
        rc, branches = repo._git(r, "branch")
        self.assertNotIn("feat", branches.split())

    def test_cleanup_skips_dirty_worktree_without_force(self):
        r = _init_repo()
        # create a second worktree with uncommitted changes
        wt = Path(tempfile.gettempdir()) / "lgwks_repo_test_wt"
        if wt.exists():
            import shutil
            shutil.rmtree(wt, ignore_errors=True)
        _git(r, "worktree", "add", str(wt))
        (wt / "dirty.py").write_text("dirty = 1\n")
        result = repo.repo_cleanup(r)
        self.assertTrue(any("worktree" in s for s in result["skipped"]))
        # cleanup temp worktree dir manually (repo_cleanup skipped it)
        import shutil
        shutil.rmtree(wt, ignore_errors=True)


class TestHandoff(unittest.TestCase):
    def test_handoff_schema_and_health(self):
        r = _init_repo()
        payload = repo.repo_handoff(r)
        self.assertEqual(payload["schema"], "lgwks.repo.handoff.v0")
        self.assertIn("health", payload)
        self.assertEqual(payload["health"]["dangling_commits"], 0)
        self.assertIn("last_cleanup", payload)


class TestGraph(unittest.TestCase):
    def test_graph_extracts_imports_and_defs(self):
        r = _init_repo()
        (r / "b.py").write_text("import os\nclass Foo:\n    pass\ndef bar():\n    pass\n")
        _git(r, "add", "b.py")
        _git(r, "commit", "-m", "add b")
        g = repo.repo_graph(r)
        self.assertEqual(g["schema"], "lgwks.repo.graph.v0")
        self.assertIn("b.py", g["files"])
        self.assertIn("os", [e["to"] for e in g["edges"]])
        self.assertIn("class Foo", g["files"]["b.py"]["defines"])
        self.assertIn("def bar", g["files"]["b.py"]["defines"])


class TestMergeMock(unittest.TestCase):
    def test_merge_rejects_closed_pr(self):
        r = _init_repo()
        orig_gh = repo._gh
        def fake_gh(*args, **kwargs):
            if "view" in args:
                return 0, '{"state":"CLOSED","headRefName":"x","baseRefName":"main"}'
            return 1, ""
        repo._gh = fake_gh
        try:
            result = repo.repo_merge(r, "1")
            self.assertIn("error", result)
            self.assertIn("not open", result["error"])
        finally:
            repo._gh = orig_gh


if __name__ == "__main__":
    unittest.main()
