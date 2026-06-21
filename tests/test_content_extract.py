"""Tests for lgwks_content_extract — the boilerplate-pruning HTML extractor seam.

"wget but better": wget mirrors raw HTML; we prune nav/chrome/ads to the content
core. The pruning heuristic is ported from crawl4ai's PruningContentFilter onto
the CPython stdlib html.parser (zero dependency chain).
"""
from __future__ import annotations

import unittest

import lgwks_content_extract as ce


_PAGE = """
<html><body>
<nav class="navbar"><a href=/>Home</a> <a href=/about>About</a> <a href=/blog>Blog</a></nav>
<header><a href=/login>Login</a></header>
<aside class="sidebar"><ul><li><a href=/1>link1</a></li><li><a href=/2>link2</a></li></ul></aside>
<main><article>
<h1>Retirement Accounts</h1>
<p>An RRSP minimum transfer requires form T2033. The settlement window is T plus one
business day, and the receiving institution must acknowledge within five business days.</p>
<p>Contribution room accumulates annually and unused room carries forward indefinitely.</p>
</article></main>
<footer class="site-footer">Copyright 2026. <a href=/privacy>Privacy</a> <a href=/terms>Terms</a></footer>
</body></html>
"""


class TestPruning(unittest.TestCase):
    def test_keeps_main_content(self):
        text = ce.extract_main_content(_PAGE)
        self.assertIn("T2033", text)
        self.assertIn("Contribution room", text)
        self.assertIn("Retirement Accounts", text)

    def test_strips_nav_header_aside_footer(self):
        text = ce.extract_main_content(_PAGE)
        for boilerplate in ("About", "Blog", "Login", "link1", "Privacy", "Terms"):
            self.assertNotIn(boilerplate, text, f"{boilerplate!r} boilerplate survived pruning")

    def test_excluded_tags_dropped_in_pruned_html(self):
        pruned = ce.prune_html(_PAGE)
        for tag in ("<nav", "<footer", "<aside", "<header", "<script", "<style"):
            self.assertNotIn(tag, pruned)
        self.assertIn("<article", pruned)

    def test_high_link_density_block_pruned(self):
        # a div that is mostly links (link farm) scores low and is removed
        html = (
            "<body><div class='links'>"
            + " ".join(f"<a href=/{i}>l{i}</a>" for i in range(20))
            + "</div><article><p>"
            + ("Real substantive sentence about settlement rules. " * 6)
            + "</p></article></body>"
        )
        text = ce.extract_main_content(html)
        self.assertIn("substantive sentence", text)
        self.assertNotIn("l19", text)

    def test_empty_and_garbage_input_safe(self):
        self.assertEqual(ce.extract_main_content(""), "")
        self.assertEqual(ce.prune_html(None), "")  # type: ignore[arg-type]
        # malformed HTML must not raise
        ce.extract_main_content("<div><p>unclosed <span> tags <a href=x>")

    def test_tiny_page_falls_back_to_full_convert(self):
        # too small to survive pruning thresholds → fall back, don't return empty
        text = ce.extract_main_content("<html><body><p>Hi</p></body></html>")
        self.assertIn("Hi", text)

    def test_deterministic(self):
        self.assertEqual(ce.extract_main_content(_PAGE), ce.extract_main_content(_PAGE))


if __name__ == "__main__":
    unittest.main()
