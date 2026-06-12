"""Tests for the Gemini ingress adapter in hooks/gemini_inbound.py."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from lgwks_daemon_store import DaemonEventStore


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "gemini_inbound",
        Path(__file__).resolve().parent.parent / "hooks" / "gemini_inbound.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGeminiAdapter(unittest.TestCase):
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
        self.mod._emit_daemon_event(self.tmp, "summarize the docs", "sess-gemini-1")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        ev = rows[0]
        self.assertEqual(ev["kind"], "human_message")
        self.assertEqual(ev["client"], "gemini")
        self.assertEqual(ev["actor"], "human")
        self.assertEqual(ev["session_id"], "sess-gemini-1")

    def test_emit_session_fallback(self):
        self.mod._emit_daemon_event(self.tmp, "hello", "")
        rows = self._rows()
        self.assertIn("gemini:", rows[0]["session_id"])

    def test_emit_fail_silent_bad_path(self):
        try:
            self.mod._emit_daemon_event(Path("/nonexistent/nowhere"), "test", "s1")
        except Exception as exc:
            self.fail(f"should be fail-silent but raised: {exc}")

    def test_prompt_head_truncated(self):
        self.mod._emit_daemon_event(self.tmp, "g" * 200, "s1")
        rows = self._rows()
        self.assertEqual(rows[0]["payload"]["prompt_len"], 200)
        self.assertEqual(len(rows[0]["payload"]["prompt_head"]), 120)

    def test_extract_prompt_flat_keys(self):
        """_extract_prompt handles top-level text/content keys."""
        mod = self.mod
        self.assertEqual(mod._extract_prompt({"prompt": "hello"}), "hello")
        self.assertEqual(mod._extract_prompt({"text": "world"}), "world")
        self.assertEqual(mod._extract_prompt({"content": "foo"}), "foo")

    def test_extract_prompt_parts_format(self):
        """_extract_prompt handles Gemini multipart parts format."""
        mod = self.mod
        payload = {"parts": [{"text": "multipart prompt"}]}
        self.assertEqual(mod._extract_prompt(payload), "multipart prompt")

    def test_extract_prompt_empty(self):
        mod = self.mod
        self.assertEqual(mod._extract_prompt({}), "")
        self.assertEqual(mod._extract_prompt({"parts": []}), "")
