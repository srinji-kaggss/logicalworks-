"""Tests for lgwks_daemon — lifecycle shell over the durable event store."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

import lgwks_daemon as daemon_mod


class TestSessionDaemon(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir(exist_ok=True)
        self.daemon = daemon_mod.SessionDaemon(self.tmp)

    def tearDown(self):
        try:
            self.daemon.stop()
        except Exception:
            pass

    def test_doctor_reports_root(self):
        report = self.daemon.doctor()
        self.assertEqual(report["schema"], daemon_mod.DOCTOR_SCHEMA)
        self.assertTrue(any(check["name"] == "daemon_root" for check in report["checks"]))

    def test_start_status_stop(self):
        status = self.daemon.start()
        self.assertEqual(status["status"], "running")
        self.assertTrue(status["alive"])

        deadline = time.time() + 5.0
        heartbeat_seen = False
        while time.time() < deadline:
            current = self.daemon.status()
            if current["heartbeat_at"]:
                heartbeat_seen = True
                break
            time.sleep(0.1)
        self.assertTrue(heartbeat_seen, "daemon should write a heartbeat")

        stopped = self.daemon.stop()
        self.assertEqual(stopped["status"], "stopped")

    def test_double_start_refused(self):
        self.daemon.start()
        with self.assertRaises(RuntimeError):
            self.daemon.start()

    def test_start_with_transcript_path_persists(self):
        transcript = str(self.tmp / "transcript.jsonl")
        status = self.daemon.start(transcript_path=transcript)
        self.assertEqual(status["transcript_path"], transcript)

        state = json.loads(self.daemon.paths.state.read_text(encoding="utf-8"))
        self.assertEqual(state["transcript_path"], transcript)

    def test_start_writes_lifecycle_events(self):
        self.daemon.start()
        self.daemon.stop()
        from lgwks_daemon_store import DaemonEventStore

        store = DaemonEventStore(self.daemon.paths.db)
        try:
            rows = store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=10)
        finally:
            store.close()
        self.assertTrue(any(row["payload"]["event"] == "daemon_started" for row in rows))
        self.assertTrue(any(row["payload"]["event"] == "daemon_stopped" for row in rows))
