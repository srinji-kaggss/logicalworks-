"""Tests for lgwks_crawl — fingerprinting, text extraction, link parsing.

Playwright integration tests are skipped if playwright is unavailable.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_crawl as crawl


class TestFingerprint(unittest.TestCase):
    def test_deterministic(self):
        a = crawl._pick_fingerprint(seed=0)
        b = crawl._pick_fingerprint(seed=0)
        self.assertEqual(a, b)

    def test_different_seeds(self):
        a = crawl._pick_fingerprint(seed=0)
        b = crawl._pick_fingerprint(seed=1)
        self.assertNotEqual(a["user_agent"], b["user_agent"])

    def test_fields_present(self):
        fp = crawl._pick_fingerprint(seed=2)
        for key in ("user_agent", "viewport", "locale", "timezone", "color_scheme", "reduced_motion"):
            self.assertIn(key, fp)


class TestTextExtraction(unittest.TestCase):
    def test_strips_tags(self):
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        self.assertEqual(crawl._text_from_html(html, 1000), "Hello **world**")

    def test_collapses_whitespace(self):
        html = "<p>A</p>\n\n\n\n<p>B</p>"
        self.assertEqual(crawl._text_from_html(html, 1000), "A\n\nB")

    def test_respects_max_chars(self):
        html = "<p>" + "x" * 10000 + "</p>"
        self.assertEqual(len(crawl._text_from_html(html, 100)), 100)


class TestLinkExtraction(unittest.TestCase):
    def test_extracts_basic_links(self):
        html = '<a href="https://example.com">Example</a>'
        links = crawl._extract_links(html, "https://base.com")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], "https://example.com")
        self.assertEqual(links[0]["text"], "Example")

    def test_skips_javascript(self):
        html = '<a href="javascript:void(0)">Click</a><a href="/page">Page</a>'
        links = crawl._extract_links(html, "https://base.com")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], "https://base.com/page")

    def test_deduplicates(self):
        html = '<a href="/dup">A</a><a href="/dup">B</a>'
        links = crawl._extract_links(html, "https://base.com")
        self.assertEqual(len(links), 1)


class TestCrawlBlocked(unittest.TestCase):
    def test_blocks_localhost(self):
        result = crawl.crawl_page("http://localhost:8080/admin")
        self.assertFalse(result.ok)
        self.assertIn("blocked", result.reason)

    def test_blocks_private_ip(self):
        result = crawl.crawl_page("http://192.168.1.1/")
        self.assertFalse(result.ok)
        self.assertIn("blocked", result.reason)


if __name__ == "__main__":
    unittest.main()
