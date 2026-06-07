"""
Tests for gate-honesty fixes (#29).

Verifies three regression boundaries:
  1. refine() on high-specificity unknown intent → classifier_coverage_gap, not blame-question
  2. public search → relevance-labelled or filtered (no silent canon-as-relevance)
  3. source_validity() → CAPTCHA/bot-challenge/login-wall rejected before ingest
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_machine as machine
import lgwks_public as public
import lgwks_search as search


class TestRefineHonesty(unittest.TestCase):
    def test_high_specificity_unknown_does_not_blame_human(self):
        """refine('Tabulate Seventeen Discrete Telemetry Samples Numbered 2026 Precisely') does NOT abstain
        blaming the human; it proceeds or returns classifier_coverage_gap."""
        intent = "Tabulate Seventeen Discrete Telemetry Samples Numbered 2026 Precisely"
        r = machine.refine(intent, log=False)
        self.assertFalse(r["abstain"])
        self.assertTrue(r.get("classifier_coverage_gap", False))
        self.assertEqual(r["questions"], [])
        self.assertEqual(r["intent_class"], "unknown")

    def test_low_specificity_unknown_still_abstains(self):
        """Low specificity unknown intent still legitimately abstains — user was vague."""
        r = machine.refine("do stuff", log=False)
        self.assertTrue(r["abstain"])
        self.assertFalse(r.get("classifier_coverage_gap", False))


class TestPublicRelevance(unittest.TestCase):
    def test_records_labelled_or_filtered(self):
        """public output is either relevance-filtered above a similarity floor OR carries an explicit
        ranking label (no silent canon-as-relevance)."""
        # We can't hit the network in tests, so exercise the labelling logic directly.
        records = [
            {"title": "Quantum entanglement in neural networks", "url": "http://example.com/1"},
            {"title": "Totally unrelated title about baking", "url": "http://example.com/2"},
        ]
        query = "machine learning quantum"
        labelled = public._label_records(records, query)
        self.assertTrue(all("relevance_score" in rec for rec in labelled))
        self.assertTrue(all("ranking" in rec for rec in labelled))
        self.assertTrue(all("relevance_floor" in rec for rec in labelled))
        # At least one should have the honest canon label because its title shares few/no terms
        labels = [r.get("ranking", "") for r in labelled]
        self.assertTrue(any("citation-canon" in lbl for lbl in labels))
        self.assertTrue(any("relevance-verified" in lbl for lbl in labels))


class TestSourceValidity(unittest.TestCase):
    def test_captcha_fixture_rejected(self):
        """A CAPTCHA/bot-challenge fixture page is rejected by crawl's source-validity gate,
        not ingested into concepts."""
        html = "<html><body>Please complete the CAPTCHA to continue.</body></html>"
        ok, diag = search.source_validity(html, "http://example.com")
        self.assertFalse(ok)
        self.assertIn("CAPTCHA", diag or "")

    def test_login_wall_rejected(self):
        """Login-wall with password field is rejected."""
        html = '<html><body><input type="password" name="pwd"></body></html>'
        ok, diag = search.source_validity(html, "http://example.com")
        self.assertFalse(ok)
        self.assertIn("password", diag or "")

    def test_empty_body_rejected(self):
        """Near-empty body is rejected."""
        ok, diag = search.source_validity("   ", "http://example.com")
        self.assertFalse(ok)
        self.assertIn("empty", diag or "")

    def test_normal_page_passes(self):
        """A normal article body passes."""
        html = "<html><body><p>This is a detailed article about machine learning and artificial intelligence.</p></body></html>"
        ok, diag = search.source_validity(html, "http://example.com")
        self.assertTrue(ok)

    def test_url_challenge_fragment_rejected(self):
        html = "<html><body><p>This is legitimate content with enough visible text to pass.</p></body></html>"
        ok, diag = search.source_validity(html, "http://example.com/captcha-verify")
        self.assertFalse(ok)
        self.assertIn("URL challenge fragment", diag or "")

    def test_non_security_challenge_article_passes(self):
        html = "<html><body><p>This is a legitimate article body with enough content to pass every text check.</p></body></html>"
        ok, diag = search.source_validity(html, "https://example.com/blog/coding-challenge-results")
        self.assertTrue(ok)
        self.assertIsNone(diag)

    def test_high_script_ratio_rejected(self):
        html = (
            '<html><head><script src="a.js"></script><script src="b.js"></script>'
            '<script src="c.js"></script><script src="d.js"></script></head>'
            '<body><p>Short.</p></body></html>'
        )
        ok, diag = search.source_validity(html, "http://example.com")
        self.assertFalse(ok)
        self.assertIn("script-to-content", diag or "")


if __name__ == "__main__":
    unittest.main()
