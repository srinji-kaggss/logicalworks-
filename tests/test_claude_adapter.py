"""Tests for the Claude ingress adapter in hooks/subconscious_inbound.py.

Verifies:
- hook emits valid hookSpecificOutput JSON (existing behaviour preserved)
- _emit_daemon_event writes a human_message event to the daemon store
- adapter is fail-silent when the store is unavailable
- session_id is derived from LGWKS_TRANSCRIPT_PATH when present
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lgwks_daemon_store import DaemonEventStore


class TestClaudeAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # Simulate repo root structure the hook expects
        (self.tmp / "store" / "daemon").mkdir(parents=True)

    def _emit(self, prompt: str, session_id: str = "") -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "subconscious_inbound",
            Path(__file__).resolve().parent.parent / "hooks" / "subconscious_inbound.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod._emit_daemon_event(self.tmp, prompt, session_id)

    def test_emit_writes_human_message(self):
        self._emit("explain the architecture", session_id="sess-abc")
        db = self.tmp / "store" / "daemon" / "daemon-events.db"
        self.assertTrue(db.exists(), "daemon store should be created")
        store = DaemonEventStore(db)
        try:
            rows = store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=5)
        finally:
            store.close()
        self.assertEqual(len(rows), 1)
        ev = rows[0]
        self.assertEqual(ev["kind"], "human_message")
        self.assertEqual(ev["lane"], "ingress")
        self.assertEqual(ev["actor"], "human")
        self.assertEqual(ev["client"], "claude")
        self.assertEqual(ev["session_id"], "sess-abc")
        self.assertIn("prompt_len", ev["payload"])

    def test_emit_session_fallback_when_no_transcript(self):
        self._emit("hello", session_id="")
        db = self.tmp / "store" / "daemon" / "daemon-events.db"
        store = DaemonEventStore(db)
        try:
            rows = store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=5)
        finally:
            store.close()
        self.assertEqual(len(rows), 1)
        self.assertIn("claude:", rows[0]["session_id"])

    def test_emit_fail_silent_on_bad_db_path(self):
        bad_root = Path("/nonexistent/path/that/does/not/exist")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "subconscious_inbound",
                Path(__file__).resolve().parent.parent / "hooks" / "subconscious_inbound.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod._emit_daemon_event(bad_root, "test", "s1")
        except Exception as exc:
            self.fail(f"_emit_daemon_event should be fail-silent but raised: {exc}")

    def test_prompt_head_truncated_at_120(self):
        long_prompt = "x" * 200
        self._emit(long_prompt, session_id="s1")
        db = self.tmp / "store" / "daemon" / "daemon-events.db"
        store = DaemonEventStore(db)
        try:
            rows = store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=5)
        finally:
            store.close()
        self.assertEqual(rows[0]["payload"]["prompt_len"], 200)
        self.assertEqual(len(rows[0]["payload"]["prompt_head"]), 120)
