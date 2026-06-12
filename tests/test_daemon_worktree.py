"""Tests for P2: daemon-owned git worktree runtime (WorktreeManager + registry)."""
from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lgwks_daemon_store import DaemonEventStore, WORKTREE_SCHEMA


def _make_store(tmp: Path) -> DaemonEventStore:
    return DaemonEventStore(tmp / "daemon-events.db")


def _init_git_repo(path: Path) -> None:
    """Set up a minimal git repo so worktree operations have something to work with."""
    subprocess.run(["git", "init", "-b", "main", str(path)], capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"], capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], capture_output=True)
    (path / "README").write_text("init")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init", "--no-gpg-sign"], capture_output=True)


class TestWorktreeRegistry(unittest.TestCase):
    """Unit tests for the store-layer worktree registry (no git required)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = _make_store(self.tmp)

    def tearDown(self):
        self.store.close()

    def test_open_and_get(self):
        inserted = self.store.open_worktree(
            worktree_id="wt-001",
            tenant_id="t1",
            session_id="sess-a",
            agent_id="claude",
            repo_path="/repo",
            worktree_path="/repo/store/daemon/worktrees/wt-001",
            branch="daemon/wt-001",
            base_sha="abc123",
        )
        self.assertTrue(inserted)
        rec = self.store.get_worktree("wt-001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["status"], "active")
        self.assertEqual(rec["schema"], WORKTREE_SCHEMA)
        self.assertEqual(rec["session_id"], "sess-a")
        self.assertEqual(rec["tenant_id"], "t1")

    def test_open_idempotent(self):
        kwargs = dict(
            worktree_id="wt-002", tenant_id="t1", session_id="sess-b", agent_id="claude",
            repo_path="/r", worktree_path="/r/wt-002", branch="daemon/wt-002", base_sha="d0",
        )
        self.assertTrue(self.store.open_worktree(**kwargs))
        self.assertFalse(self.store.open_worktree(**kwargs))
        self.assertEqual(len(self.store.list_worktrees("t1")), 1)

    def test_close_worktree(self):
        self.store.open_worktree(
            worktree_id="wt-003", tenant_id="t1", session_id="s3", agent_id="claude",
            repo_path="/r", worktree_path="/r/wt-003", branch="daemon/wt-003", base_sha="e0",
        )
        self.store.close_worktree("wt-003")
        rec = self.store.get_worktree("wt-003")
        self.assertEqual(rec["status"], "closed")
        self.assertIsNotNone(rec["closed_at"])

    def test_close_worktree_with_error(self):
        self.store.open_worktree(
            worktree_id="wt-004", tenant_id="t1", session_id="s4", agent_id="claude",
            repo_path="/r", worktree_path="/r/wt-004", branch="daemon/wt-004", base_sha="f0",
        )
        self.store.close_worktree("wt-004", error="git remove failed")
        self.assertEqual(self.store.get_worktree("wt-004")["status"], "error")

    def test_list_active_only(self):
        for i in range(3):
            self.store.open_worktree(
                worktree_id=f"wt-l{i}", tenant_id="t1", session_id=f"s{i}", agent_id="claude",
                repo_path="/r", worktree_path=f"/r/wt-l{i}", branch=f"daemon/wt-l{i}", base_sha="0",
            )
        self.store.close_worktree("wt-l0")
        active = self.store.list_worktrees("t1", active_only=True)
        all_ = self.store.list_worktrees("t1", active_only=False)
        self.assertEqual(len(active), 2)
        self.assertEqual(len(all_), 3)

    def test_tenant_isolation(self):
        self.store.open_worktree(
            worktree_id="wt-ta", tenant_id="ta", session_id="s", agent_id="claude",
            repo_path="/r", worktree_path="/r/ta", branch="daemon/ta", base_sha="0",
        )
        self.store.open_worktree(
            worktree_id="wt-tb", tenant_id="tb", session_id="s", agent_id="claude",
            repo_path="/r", worktree_path="/r/tb", branch="daemon/tb", base_sha="0",
        )
        self.assertEqual(len(self.store.list_worktrees("ta")), 1)
        self.assertEqual(len(self.store.list_worktrees("tb")), 1)

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.store.get_worktree("not-a-real-id"))

    def test_concurrent_open_no_duplicate(self):
        results = []
        errors = []

        def worker(wt_id: str) -> None:
            try:
                s = _make_store(self.tmp)
                try:
                    r = s.open_worktree(
                        worktree_id=wt_id, tenant_id="t1", session_id=f"s-{wt_id}",
                        agent_id="claude", repo_path="/r",
                        worktree_path=f"/r/{wt_id}", branch=f"daemon/{wt_id}", base_sha="0",
                    )
                    results.append(r)
                finally:
                    s.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"wt-c{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 5)
        self.assertEqual(sum(results), 5)  # all inserted (distinct wt_ids)


class TestWorktreeManagerWithGit(unittest.TestCase):
    """Integration tests requiring a real git repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _init_git_repo(self.repo)
        self.store = _make_store(self.tmp)

    def tearDown(self):
        self.store.close()
        # Force-remove any lingering worktrees
        subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True)
        for branch_line in subprocess.run(
            ["git", "-C", str(self.repo), "branch"],
            capture_output=True, text=True,
        ).stdout.splitlines():
            br = branch_line.strip().lstrip("* ")
            if br.startswith("daemon/"):
                subprocess.run(
                    ["git", "-C", str(self.repo), "branch", "-D", br], capture_output=True
                )

    def _mgr(self):
        from lgwks_daemon import WorktreeManager
        return WorktreeManager(self.store, self.repo)

    def test_create_and_close(self):
        mgr = self._mgr()
        result = mgr.create("t1", "sess-x", "claude")
        self.assertTrue(result["created"])
        self.assertEqual(result["status"], "active")
        wt_path = Path(result["worktree_path"])
        self.assertTrue(wt_path.is_dir(), "worktree directory should exist")

        rec = self.store.get_worktree(result["worktree_id"])
        self.assertEqual(rec["status"], "active")

        closed = mgr.close(result["worktree_id"])
        self.assertTrue(closed["closed"])
        self.assertIsNone(closed["error"])
        self.assertFalse(wt_path.exists(), "worktree dir should be removed")
        self.assertEqual(self.store.get_worktree(result["worktree_id"])["status"], "closed")

    def test_referee_no_duplicate_for_session(self):
        mgr = self._mgr()
        r1 = mgr.create("t1", "sess-dup", "claude")
        r2 = mgr.create("t1", "sess-dup", "claude")
        self.assertTrue(r1["created"])
        self.assertFalse(r2["created"])
        self.assertEqual(r2["reason"], "session_already_has_active_worktree")
        self.assertEqual(r1["worktree_id"], r2["worktree_id"])
        # Only one worktree created
        active = self.store.list_worktrees("t1", active_only=True)
        self.assertEqual(len(active), 1)
        # Cleanup
        mgr.close(r1["worktree_id"])

    def test_multiple_sessions_get_separate_worktrees(self):
        mgr = self._mgr()
        r1 = mgr.create("t1", "sess-1", "claude")
        r2 = mgr.create("t1", "sess-2", "codex")
        self.assertTrue(r1["created"])
        self.assertTrue(r2["created"])
        self.assertNotEqual(r1["worktree_id"], r2["worktree_id"])
        active = self.store.list_worktrees("t1", active_only=True)
        self.assertEqual(len(active), 2)
        # Cleanup
        mgr.close(r1["worktree_id"])
        mgr.close(r2["worktree_id"])

    def test_close_nonexistent_raises(self):
        mgr = self._mgr()
        with self.assertRaises(ValueError):
            mgr.close("not-a-real-worktree-id")

    def test_close_already_closed_is_safe(self):
        mgr = self._mgr()
        r = mgr.create("t1", "sess-z", "gemini")
        mgr.close(r["worktree_id"])
        result = mgr.close(r["worktree_id"])
        self.assertFalse(result["closed"])
        self.assertEqual(result["reason"], "already_closed")

    def test_crdt_snapshot_written(self):
        mgr = self._mgr()
        r = mgr.create("t1", "sess-crdt", "claude")
        crdt_file = self.repo / "store" / "daemon" / "crdt" / "t1.json"
        self.assertTrue(crdt_file.exists(), "CRDT snapshot should be written")
        mgr.close(r["worktree_id"])
