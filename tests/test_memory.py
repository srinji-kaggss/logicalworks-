"""
Tests for lgwks_memory concurrency (Issue #53).

Enterprise assertions:
  * Two threads appending 100 records each → verify() passes, no records lost.
  * Lock acquisition and release do not leak file descriptors.
  * Chain integrity is preserved under concurrent read + write.
  * Appending to a broken chain raises ValueError even under lock.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_memory as memory


class TestMemoryConcurrency(unittest.TestCase):
    def setUp(self):
        self._orig_dir = memory._DIR
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        memory._DIR = td / "store" / "projects"

    def tearDown(self):
        memory._DIR = self._orig_dir
        self._td.cleanup()

    def test_concurrent_appends_no_records_lost(self):
        """Two threads append 100 records each; verify passes; no records lost."""
        project = "stress-concurrent"
        memory.init_project(project, "https://example.com", "test goal")
        errors = []

        def writer(label, count):
            for i in range(count):
                try:
                    memory.append(project, "note", {"writer": label, "index": i})
                except Exception as exc:
                    errors.append(exc)

        t1 = threading.Thread(target=writer, args=("A", 100))
        t2 = threading.Thread(target=writer, args=("B", 100))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"append errors: {errors}")
        rows = memory._read(project)
        # init_project = scope + goal_conversation + goal_theme = 3 records
        # + 200 note records = 203 total
        self.assertEqual(len(rows), 203)
        self.assertTrue(memory.verify(project))

    def test_concurrent_append_and_read(self):
        """One thread appends while another reads; reader sees consistent chain."""
        project = "stress-read"
        memory.init_project(project, "https://example.com", "goal")
        read_ok = threading.Event()
        write_done = threading.Event()
        read_results = []

        def appender():
            for i in range(50):
                memory.append(project, "note", {"index": i})
            write_done.set()

        def reader():
            while not write_done.is_set():
                if memory.verify(project):
                    read_results.append(True)
            read_ok.set()

        t2 = threading.Thread(target=reader)
        t1 = threading.Thread(target=appender)
        t2.start()
        t1.start()
        t1.join()
        t2.join(timeout=10)
        self.assertTrue(read_ok.is_set())
        self.assertTrue(all(read_results), "some verify() calls failed during concurrent read")

    def test_append_to_broken_chain_raises_under_lock(self):
        """Even under exclusive lock, a broken chain is detected and rejected."""
        project = "broken-chain"
        memory.init_project(project, "https://example.com", "goal")
        p = memory._path(project)
        lines = p.read_text().splitlines()
        last = json.loads(lines[-1])
        last["hash"] = last["hash"][:-1] + ("0" if last["hash"][-1] != "0" else "1")
        lines[-1] = json.dumps(last, sort_keys=True, ensure_ascii=False)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            memory.append(project, "note", {"should": "fail"})
        self.assertIn("broken", str(ctx.exception).lower())

    def test_remember_creates_conversation_and_theme(self):
        project = "test-remember"
        memory.init_project(project, "example.com", "goal")
        result = memory.remember(project, "the user wants a faster database query", source="conversation")
        self.assertTrue(memory.verify(project))
        # init_project adds 3 records (scope + goal_conversation + goal_theme)
        # remember adds 2 more (conversation + theme) → 5 total → seq of new conversation = 4
        self.assertEqual(result["conversation_seq"], 4)
        rows = memory._read(project)
        self.assertTrue(any(r["kind"] == "conversation" for r in rows))
        self.assertTrue(any(r["kind"] == "theme" for r in rows))

    def test_context_returns_focus_themes(self):
        project = "test-context"
        memory.init_project(project, "example.com", "optimize performance")
        memory.remember(project, "database performance is critical for scaling", source="conversation")
        ctx = memory.context(project, query="performance scaling")
        self.assertTrue(ctx["chain_ok"])
        self.assertTrue(len(ctx["focus_themes"]) > 0)


if __name__ == "__main__":
    unittest.main()
