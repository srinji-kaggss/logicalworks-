"""Tests for lgwks_search — retry logic, UA rotation, backoff, source validity."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import lgwks_search as search


class TestUaRotation(unittest.TestCase):
    def test_pick_ua_cycles_pool(self):
        seen = {search._pick_ua(i) for i in range(10)}
        assert len(seen) == len(search._UA_POOL)

    def test_pick_ua_deterministic(self):
        assert search._pick_ua(0) == search._pick_ua(0)
        assert search._pick_ua(1) == search._pick_ua(1)
        assert search._pick_ua(0) != search._pick_ua(1)


class TestBackoff(unittest.TestCase):
    def test_increases_with_attempt(self):
        assert search._backoff(0) < search._backoff(1)
        assert search._backoff(1) < search._backoff(2)

    def test_capped_at_two_seconds(self):
        assert search._backoff(100) <= 2.15   # base 2.0 + max jitter 0.15

    def test_jitter_non_zero(self):
        assert search._backoff(0) != search._backoff(1)


class TestCurl(unittest.TestCase):
    @patch("subprocess.run")
    def test_uses_provided_ua(self, mock_run):
        mock_run.return_value.stdout = "ok"
        search._curl("https://example.com", ua="CustomBot/1.0")
        cmd = mock_run.call_args[0][0]
        assert "-A" in cmd
        idx = cmd.index("-A")
        assert cmd[idx + 1] == "CustomBot/1.0"

    @patch("subprocess.run")
    def test_defaults_to_pool_first(self, mock_run):
        mock_run.return_value.stdout = "ok"
        search._curl("https://example.com")
        cmd = mock_run.call_args[0][0]
        assert search._UA_POOL[0] in cmd


class TestOpenRetry(unittest.TestCase):
    @patch.object(search, "_curl", return_value="")
    @patch.object(search, "time")
    def test_retries_each_endpoint_twice(self, mock_time, mock_curl):
        """When _curl returns empty, _open should try each endpoint up to 2× before giving up."""
        mock_time.sleep = lambda x: None
        results = search._open("test query", 4, sleep=mock_time.sleep)
        assert results == []
        # 3 endpoints × 2 retries = up to 6 curl calls
        assert mock_curl.call_count == 6

    @patch.object(search, "_curl", side_effect=["short", "", "", "", "", ""])
    @patch.object(search, "time")
    def test_skips_too_short_bodies(self, mock_time, mock_curl):
        """Bodies shorter than _MIN_BODY are treated as blocked and skipped."""
        mock_time.sleep = lambda x: None
        results = search._open("test query", 4, sleep=mock_time.sleep)
        assert results == []
        # first call returned "short" (<200), so it retried same endpoint, then rotated
        assert mock_curl.call_count >= 2


class TestSourceValidity(unittest.TestCase):
    def test_captcha_rejection(self):
        ok, diag = search.source_validity("Please complete the CAPTCHA to continue.")
        assert not ok
        assert "CAPTCHA" in diag

    def test_login_wall_rejection(self):
        ok, diag = search.source_validity("Please sign in to view this content.")
        assert not ok
        assert "login" in diag

    def test_empty_rejection(self):
        ok, diag = search.source_validity("   ")
        assert not ok
        assert "empty" in diag

    def test_normal_text_accepted(self):
        ok, diag = search.source_validity("This is a real article with lots of content and paragraphs.")
        assert ok
        assert diag is None


class TestUnwrap(unittest.TestCase):
    def test_ddg_redirect(self):
        assert search._unwrap("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath") == "https://example.com/path"

    def test_plain_url(self):
        assert search._unwrap("https://example.com/path") == "https://example.com/path"


if __name__ == "__main__":
    unittest.main()
