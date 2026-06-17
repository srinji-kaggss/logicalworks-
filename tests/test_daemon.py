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

    # --- #227 F1: canonical tenant resolution (emit/packet symmetry) ---
    def test_tenant_for_default_and_override(self):
        paths = self.daemon.paths
        self.assertEqual(daemon_mod._tenant_for(paths), f"repo:{self.tmp.name}")
        self.assertEqual(daemon_mod._tenant_for(paths, "demo"), "demo")
        # blank/whitespace override falls back to the canonical repo tenant
        self.assertEqual(daemon_mod._tenant_for(paths, "   "), f"repo:{self.tmp.name}")

    # --- #227 F2: already-running start is structured, not a traceback ---
    def test_start_command_already_running_is_structured(self):
        import argparse
        import contextlib
        import io

        self.daemon.start()
        args = argparse.Namespace(repo=str(self.tmp), transcript_path=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = daemon_mod._start_command(args)
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["schema"], "lgwks.daemon.start.v0")
        self.assertEqual(out["status"], "already_running")
        self.assertTrue(out["ok"])
        self.assertFalse(out["started"])

    # --- #227 F3: doctor flags the live transcript binding ---
    def test_transcript_binding_flags_subagent(self):
        sub = self.tmp / "projects" / "slug" / "subagents"
        sub.mkdir(parents=True)
        tpath = sub / "agent-abc.jsonl"
        tpath.write_text("", encoding="utf-8")
        self.daemon.start(transcript_path=str(tpath))
        check = next(c for c in self.daemon.doctor()["checks"] if c["name"] == "transcript_binding")
        self.assertFalse(check["ok"])
        self.assertIn("subagent", check["detail"])

    def test_transcript_binding_flags_missing(self):
        self.daemon.start(transcript_path=str(self.tmp / "nope.jsonl"))
        check = next(c for c in self.daemon.doctor()["checks"] if c["name"] == "transcript_binding")
        self.assertFalse(check["ok"])
        self.assertIn("missing", check["detail"])

    def test_transcript_binding_ok_for_real_transcript_and_non_fatal(self):
        tpath = self.tmp / "transcript.jsonl"
        tpath.write_text("", encoding="utf-8")
        self.daemon.start(transcript_path=str(tpath))
        report = self.daemon.doctor()
        check = next(c for c in report["checks"] if c["name"] == "transcript_binding")
        self.assertTrue(check["ok"])
        # transcript binding is degraded-but-non-fatal: overall doctor stays ok
        self.assertTrue(report["ok"])
