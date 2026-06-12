"""Tests for the Codex ingress adapter in hooks/codex_inbound.py."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from lgwks_daemon_store import DaemonEventStore


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "codex_inbound",
        Path(__file__).resolve().parent.parent / "hooks" / "codex_inbound.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCodexAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store" / "daemon").mkdir(parents=True)
        self.mod = _load_mod()

    def _rows(self) -> list[dict]:
        db = self.tmp / "store" / "daemon" / "daemon-events.db"
        store = DaemonEventStore(db)
        try:
            return store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=10)
        finally:
            store.close()

    def test_emit_writes_human_message(self):
        self.mod._emit_daemon_event(self.tmp, "analyze the codebase", "sess-codex-1")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        ev = rows[0]
        self.assertEqual(ev["kind"], "human_message")
        self.assertEqual(ev["client"], "codex")
        self.assertEqual(ev["actor"], "human")
        self.assertEqual(ev["session_id"], "sess-codex-1")

    def test_emit_session_fallback(self):
        self.mod._emit_daemon_event(self.tmp, "hello", "")
        rows = self._rows()
        self.assertIn("codex:", rows[0]["session_id"])

    def test_emit_fail_silent_bad_path(self):
        try:
            self.mod._emit_daemon_event(Path("/nonexistent/nowhere"), "test", "s1")
        except Exception as exc:
            self.fail(f"should be fail-silent but raised: {exc}")

    def test_prompt_head_truncated(self):
        self.mod._emit_daemon_event(self.tmp, "z" * 200, "s1")
        rows = self._rows()
        self.assertEqual(rows[0]["payload"]["prompt_len"], 200)
        self.assertEqual(len(rows[0]["payload"]["prompt_head"]), 120)

    def test_content_key_fallback(self):
        """Codex may send 'content' instead of 'prompt'."""
        self.mod._emit_daemon_event(self.tmp, "via content key", "s1")
        rows = self._rows()
        self.assertEqual(rows[0]["payload"]["prompt_len"], len("via content key"))
