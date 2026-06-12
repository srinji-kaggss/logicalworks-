"""Tests for P5: content-addressed archive/export tier (ExportManager)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lgwks_daemon_store import DaemonEventStore
from lgwks_daemon_export import ExportManager, EXPORT_SCHEMA, CLEANUP_SCHEMA


def _store(tmp: Path) -> DaemonEventStore:
    return DaemonEventStore(tmp / "daemon-events.db")


def _seed_run(store: DaemonEventStore, tmp: Path, run_id: str = "run-001") -> Path:
    """Create a minimal research run on disk and register it in the store."""
    run_dir = tmp / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    (run_dir / "data.txt").write_text("some research content")
    store.register_run("t1", {
        "run_id": run_id,
        "target": "https://example.com",
        "source": "https://example.com",
        "artifacts": {"root": str(run_dir)},
    })
    return run_dir


class TestExportRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = _store(self.tmp)
        self.run_dir = _seed_run(self.store, self.tmp)

    def tearDown(self):
        self.store.close()

    def _mgr(self) -> ExportManager:
        return ExportManager(self.store, self.tmp)

    def test_export_creates_archive(self):
        result = self._mgr().export_run("run-001")
        self.assertEqual(result["schema"], EXPORT_SCHEMA)
        self.assertTrue(result["verified"])
        archive = Path(result["export_path"])
        self.assertTrue(archive.exists(), "archive should exist on disk")
        self.assertTrue(archive.suffix == ".gz")
        self.assertEqual(len(result["export_hash"]), 64, "sha256 hex digest should be 64 chars")

    def test_export_records_in_store(self):
        self._mgr().export_run("run-001")
        state = self.store.get_run_export_state("run-001")
        self.assertIsNotNone(state["exported_at"])
        self.assertIsNotNone(state["export_hash"])
        self.assertIsNotNone(state["export_path"])

    def test_export_unknown_run_raises(self):
        with self.assertRaises(ValueError):
            self._mgr().export_run("not-a-run")

    def test_export_missing_run_dir_raises(self):
        import shutil
        shutil.rmtree(self.run_dir)
        with self.assertRaises(FileNotFoundError):
            self._mgr().export_run("run-001")

    def test_re_export_updates_record(self):
        mgr = self._mgr()
        r1 = mgr.export_run("run-001")
        r2 = mgr.export_run("run-001")
        # Both produce same hash (same content)
        self.assertEqual(r1["export_hash"], r2["export_hash"])

    def test_export_custom_dest(self):
        dest = self.tmp / "custom_exports"
        dest.mkdir()
        result = self._mgr().export_run("run-001", dest_dir=dest)
        self.assertTrue(Path(result["export_path"]).parent == dest)


class TestVerifyExport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = _store(self.tmp)
        _seed_run(self.store, self.tmp)

    def tearDown(self):
        self.store.close()

    def _mgr(self):
        return ExportManager(self.store, self.tmp)

    def test_verify_not_exported(self):
        result = self._mgr().verify_export("run-001")
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "not_exported")

    def test_verify_after_export(self):
        mgr = self._mgr()
        mgr.export_run("run-001")
        result = mgr.verify_export("run-001")
        self.assertTrue(result["verified"])
        self.assertEqual(result["stored_hash"], result["actual_hash"])

    def test_verify_tampered_archive_fails(self):
        mgr = self._mgr()
        mgr.export_run("run-001")
        state = self.store.get_run_export_state("run-001")
        # Tamper with the archive
        Path(state["export_path"]).write_bytes(b"tampered")
        result = mgr.verify_export("run-001")
        self.assertFalse(result["verified"])

    def test_verify_missing_archive(self):
        mgr = self._mgr()
        mgr.export_run("run-001")
        state = self.store.get_run_export_state("run-001")
        Path(state["export_path"]).unlink()
        result = mgr.verify_export("run-001")
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "archive_missing")


class TestCleanupRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = _store(self.tmp)
        self.run_dir = _seed_run(self.store, self.tmp)

    def tearDown(self):
        self.store.close()

    def _mgr(self):
        return ExportManager(self.store, self.tmp)

    def test_cleanup_blocked_without_export(self):
        result = self._mgr().cleanup_run("run-001")
        self.assertFalse(result["cleaned"])
        self.assertIn("export_not_verified", result["reason"])
        self.assertTrue(self.run_dir.is_dir(), "dir should still exist")

    def test_cleanup_after_verified_export(self):
        mgr = self._mgr()
        mgr.export_run("run-001")
        result = mgr.cleanup_run("run-001")
        self.assertTrue(result["cleaned"])
        self.assertFalse(self.run_dir.is_dir(), "dir should be removed")

    def test_cleanup_force_skips_verification(self):
        result = self._mgr().cleanup_run("run-001", force=True)
        self.assertTrue(result["cleaned"])
        self.assertTrue(result["force"])

    def test_cleanup_nonexistent_run_raises(self):
        with self.assertRaises(ValueError):
            self._mgr().cleanup_run("bogus-id")


class TestExportSession(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = _store(self.tmp)

    def tearDown(self):
        self.store.close()

    def _mgr(self):
        return ExportManager(self.store, self.tmp)

    def test_export_session_empty(self):
        result = self._mgr().export_session("t1", "sess-none")
        self.assertEqual(result["event_count"], 0)
        self.assertTrue(Path(result["export_path"]).exists())

    def test_export_session_with_events(self):
        import lgwks_daemon_event as ev
        for i in range(3):
            self.store.append(ev.build_event(
                tenant_id="t1", agent_id="claude", session_id="sess-exp",
                actor="agent", client="claude", lane="telemetry",
                kind="tool_call", scope="agent_local",
                ts=f"2026-06-12T00:00:{i:02d}+00:00",
                payload={"i": i},
            ))
        result = self._mgr().export_session("t1", "sess-exp")
        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["schema"], EXPORT_SCHEMA)
        self.assertTrue(result["verified"])
        export_path = Path(result["export_path"])
        lines = export_path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertIn("tool_call", line)

    def test_export_session_hash_is_deterministic(self):
        result1 = self._mgr().export_session("t1", "sess-hash")
        result2 = self._mgr().export_session("t1", "sess-hash")
        self.assertEqual(result1["export_hash"], result2["export_hash"])
