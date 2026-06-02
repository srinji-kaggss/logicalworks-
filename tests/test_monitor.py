"""Tests for lgwks_monitor — snapshot, diff, and change detection."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import lgwks_monitor as monitor


class TestNormalize(unittest.TestCase):
    def test_collapse_empty_lines(self):
        assert monitor._normalize("a\n\n  \nb") == ["a", "b"]

    def test_strips_whitespace(self):
        assert monitor._normalize("  hello  ") == ["hello"]


class TestHash(unittest.TestCase):
    def test_deterministic(self):
        assert monitor._hash("hello") == monitor._hash("hello")

    def test_different_text_different_hash(self):
        assert monitor._hash("hello") != monitor._hash("world")


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        # Clean monitor index between tests to prevent leakage
        if monitor._INDEX.exists():
            monitor._INDEX.unlink()

    @patch("lgwks_extract.extract", return_value={"ok": True, "text": "page content here", "kind": "html"})
    @patch("lgwks_cache.put", return_value={"hash": "abc123", "bytes": 100})
    def test_new_snapshot(self, mock_cache, mock_extract):
        r = monitor.snapshot("https://example.com")
        self.assertTrue(r["changed"])
        self.assertEqual(r["text"], "page content here")
        self.assertEqual(r["previous_hash"], "")

    @patch("lgwks_extract.extract", return_value={"ok": False, "text": "", "kind": "html"})
    def test_failed_extraction(self, mock_extract):
        r = monitor.snapshot("https://example.com")
        self.assertFalse(r["changed"])
        self.assertEqual(r["error"], "extraction failed")


class TestDiff(unittest.TestCase):
    def setUp(self):
        if monitor._INDEX.exists():
            monitor._INDEX.unlink()

    @patch("lgwks_monitor.snapshot", return_value={
        "url": "https://example.com",
        "hash": "hash2",
        "timestamp": time.time(),
        "kind": "html",
        "changed": True,
        "previous_hash": "hash1",
        "text": "line one\nline two\nline three",
    })
    def test_no_prior_snapshot(self, mock_snap):
        r = monitor.diff("https://example.com", hours=1)
        self.assertFalse(r["changed"])
        self.assertIn("no snapshot", r["note"])

    @patch("lgwks_monitor.snapshot")
    @patch("lgwks_cache.get_text", side_effect=["old content here", None])
    def test_detects_change(self, mock_cache_get, mock_snap):
        # seed an old snapshot
        monitor._append_index({
            "url": "https://example.com",
            "hash": "hash1",
            "timestamp": time.time() - 3600,
            "kind": "html",
            "bytes": 50,
            "previous_hash": "",
        })
        mock_snap.return_value = {
            "url": "https://example.com",
            "hash": "hash2",
            "timestamp": time.time(),
            "kind": "html",
            "changed": True,
            "previous_hash": "hash1",
            "text": "new content here",
        }
        r = monitor.diff("https://example.com", hours=1)
        self.assertTrue(r["changed"] or len(r["added_lines"]) > 0 or len(r["removed_lines"]) > 0)


class TestCheck(unittest.TestCase):
    def setUp(self):
        if monitor._INDEX.exists():
            monitor._INDEX.unlink()

    @patch("lgwks_monitor.diff", return_value={"url": "https://a.com", "changed": True, "added_lines": [], "removed_lines": [], "percent_changed": 10.0})
    def test_summary_counts(self, mock_diff):
        r = monitor.check(["https://a.com", "https://b.com"], hours=8)
        self.assertEqual(r["checked"], 2)


class TestStatus(unittest.TestCase):
    def setUp(self):
        if monitor._INDEX.exists():
            monitor._INDEX.unlink()

    def test_empty_status(self):
        r = monitor.status()
        self.assertEqual(r["tracked_urls"], 0)


if __name__ == "__main__":
    unittest.main()
