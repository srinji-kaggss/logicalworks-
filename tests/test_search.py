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
        # invariant: each LIVE floor endpoint is retried up to 2× before giving up.
        # Track the actual roster, not a hardcoded count — dead endpoints are retired
        # from rotation rather than kept as pure latency.
        assert mock_curl.call_count == 2 * len(search._FLOOR_ENDPOINTS)

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


class TestScholarParsing(unittest.TestCase):
    def test_extracts_result_blocks(self):
        html = (
            '<div class="gs_r"><div class="gs_ri">'
            '<h3 class="gs_rt"><a href="https://example.com/paper">Attention Is All You Need</a></h3>'
            '<div class="gs_a">A Vaswani et al. - NeurIPS 2017</div>'
            '<div class="gs_rs">We propose a new simple network architecture...</div>'
            '</div></div>'
            '<div class="gs_r"><div class="gs_ri">'
            '<h3 class="gs_rt"><a href="https://example.com/paper2">BERT: Pre-training</a></h3>'
            '<div class="gs_a">J Devlin et al. - NAACL 2019</div>'
            '<div class="gs_rs">We introduce a new language representation model...</div>'
            '</div></div>'
        )
        rows = search._parse_scholar(html, k=4, via="scholar")
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Attention Is All You Need")
        self.assertEqual(rows[0]["url"], "https://example.com/paper")
        self.assertIn("Vaswani", rows[0]["snippet"])
        if len(rows) >= 2:
            self.assertEqual(rows[1]["title"], "BERT: Pre-training")

    def test_skips_malformed_blocks(self):
        html = '<div class="gs_r"><div class="gs_ri">no link here</div></div>'
        rows = search._parse_scholar(html, k=4, via="scholar")
        self.assertEqual(rows, [])


class TestScholarSearch(unittest.TestCase):
    @patch.object(search, "_curl", return_value="")
    def test_returns_empty_when_blocked(self, mock_curl):
        rows = search.scholar("machine learning", k=3)
        self.assertEqual(rows, [])
        self.assertTrue(mock_curl.call_count <= 3)


class TestSweepIncludesAcademic(unittest.TestCase):
    @patch.object(search, "search", return_value=[{"title": "Web result", "url": "https://example.com"}])
    @patch.object(search, "scholar", return_value=[{"title": "Paper result", "url": "https://scholar.example.com"}])
    def test_scholar_arm_included(self, mock_scholar, mock_search):
        result = search.sweep("machine learning", k_per_arm=2)
        self.assertIn("academic", result["arms_hit"])
        self.assertEqual(result["arms_hit"]["academic"], 1)
        urls = [r["url"] for r in result["results"]]
        self.assertIn("https://scholar.example.com", urls)


class TestUnwrap(unittest.TestCase):
    def test_ddg_redirect(self):
        assert search._unwrap("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath") == "https://example.com/path"

    def test_plain_url(self):
        assert search._unwrap("https://example.com/path") == "https://example.com/path"


class TestEmptyResultContract(unittest.TestCase):
    """[] from search()/sweep() means 'no usable results from attempted providers', NOT 'no evidence
    exists'. Every empty result must carry a provider_attempt_trace explaining why (issue: harden the
    empty-result contract)."""

    def test_search_empty_carries_provider_attempt_trace(self):
        # All providers fail/return nothing -> search() still returns [], but last_search_trace()
        # must explain which providers were attempted and why each yielded nothing.
        orig = search._PROVIDERS
        search._PROVIDERS = [
            ("cli", lambda q, k: []),
            ("open", lambda q, k: []),
        ]
        try:
            out = search.search("no such evidence anywhere", k=3)
            trace = search.last_search_trace()
        finally:
            search._PROVIDERS = orig
        self.assertEqual(out, [])
        self.assertTrue(trace, "empty search() result must carry a non-empty provider_attempt_trace")
        self.assertEqual({t["provider"] for t in trace}, {"cli", "open"})
        for entry in trace:
            self.assertTrue(entry["attempted"])
            self.assertTrue(entry["error_or_reason"], f"{entry['provider']} must explain why it yielded nothing")

    def test_search_trace_records_provider_exceptions_not_just_empties(self):
        # A provider that raises must still appear in the trace (never silently vanish).
        def boom(q, k):
            raise RuntimeError("provider transport failure")
        orig = search._PROVIDERS
        search._PROVIDERS = [("cli", boom), ("open", lambda q, k: [])]
        try:
            out = search.search("anything", k=3)
            trace = search.last_search_trace()
        finally:
            search._PROVIDERS = orig
        self.assertEqual(out, [])
        cli_entry = next(t for t in trace if t["provider"] == "cli")
        self.assertIn("RuntimeError", cli_entry["error_or_reason"])
        self.assertIn("provider transport failure", cli_entry["error_or_reason"])

    def test_search_nonempty_result_still_populates_trace(self):
        # The trace contract holds even on the happy path — never silently stale.
        hit = {"title": "Found", "url": "https://example.com/x", "snippet": "", "via": "open"}
        orig = search._PROVIDERS
        search._PROVIDERS = [("cli", lambda q, k: []), ("open", lambda q, k: [hit])]
        try:
            out = search.search("Canada Life", k=3)
            trace = search.last_search_trace()
        finally:
            search._PROVIDERS = orig
        self.assertEqual(len(out), 1)
        self.assertEqual(len(trace), 2)
        self.assertEqual(trace[0]["error_or_reason"], "returned no results")
        self.assertEqual(trace[1]["error_or_reason"], "")  # the winning provider

    def test_sweep_empty_carries_provider_attempt_trace(self):
        # When every arm's underlying providers fail/return nothing, sweep() must still report
        # has_evidence=False AND a non-empty provider_attempt_trace naming every empty arm.
        orig_providers = search._PROVIDERS
        orig_scholar = search.scholar
        search._PROVIDERS = [("cli", lambda q, k: []), ("open", lambda q, k: [])]
        search.scholar = lambda q, k=6: []
        try:
            result = search.sweep("no evidence query", k_per_arm=2)
        finally:
            search._PROVIDERS = orig_providers
            search.scholar = orig_scholar
        self.assertFalse(result["has_evidence"])
        self.assertEqual(result["results"], [])
        self.assertTrue(result.get("arms_empty"), "every arm must be reported empty")
        trace = result.get("provider_attempt_trace")
        self.assertTrue(trace, "sweep() with no evidence must carry a non-empty provider_attempt_trace")
        traced_arms = {entry["arm"] for entry in trace}
        self.assertEqual(traced_arms, set(result["arms_empty"]))
        for entry in trace:
            self.assertIn("provider", entry)
            self.assertTrue(entry.get("error_or_reason"), f"arm {entry['arm']} trace entry missing a reason")

    def test_sweep_does_not_change_existing_keys_or_types(self):
        # Additive-only contract: existing consumers (lgwks_search_engine.resolve_fact) read
        # has_evidence / results / arms_hit / arms_empty as before — those must be unaffected.
        orig_providers = search._PROVIDERS
        orig_scholar = search.scholar
        hit = {"title": "Found", "url": "https://example.com/x", "snippet": "", "via": "open"}
        search._PROVIDERS = [("cli", lambda q, k: []), ("open", lambda q, k: [hit])]
        search.scholar = lambda q, k=6: []
        try:
            result = search.sweep("Canada Life", k_per_arm=2)
        finally:
            search._PROVIDERS = orig_providers
            search.scholar = orig_scholar
        self.assertIsInstance(result["results"], list)
        self.assertIsInstance(result["arms_hit"], dict)
        self.assertIsInstance(result["arms_empty"], list)
        self.assertIsInstance(result["has_evidence"], bool)
        self.assertTrue(result["has_evidence"])
        self.assertIsInstance(result["provider_attempt_trace"], list)  # new key, additive only

    def test_research_queue_propagates_provider_attempt_trace_per_subquery(self):
        # The temporal multi-subquery path must not drop the trace the single-sweep path carries.
        orig_sweep = search.sweep
        def fake_sweep(query, k_per_arm=4):
            return {
                "query": query, "results": [], "arms_hit": {"general": 0},
                "arms_empty": ["general"], "has_evidence": False,
                "provider_attempt_trace": [
                    {"arm": "general", "provider": "open", "attempted": True,
                     "error_or_reason": "returned no results"},
                ],
            }
        search.sweep = fake_sweep
        try:
            pack = search.research_queue("Canada Life annual reports and MD&A (2022-2024)")
        finally:
            search.sweep = orig_sweep
        self.assertTrue(pack["provider_attempt_trace"], "multi-subquery path must not drop the trace")
        self.assertTrue(all("subquery" in e for e in pack["provider_attempt_trace"]))


if __name__ == "__main__":
    unittest.main()
