"""Tests for lgwks_content_extract BM25 query-relevance filtering (#261 pillar 3).

Covers: (1) topical relevance ranking, (2) regression guard (query="" byte-identical),
(3) determinism, (4) edge cases (empty/garbage HTML, empty/no-match queries).
"""
from __future__ import annotations

import unittest

import lgwks_content_extract as ce


class TestBM25QueryFilter(unittest.TestCase):
    """BM25 query relevance filtering."""

    # Test page with clear topic blocks
    _PAGE_RETIREMENT = """
<html><body>
<main>
<article>
<h1>Retirement Planning Guide</h1>
<p>Retirement is a major life transition. An RRSP minimum transfer requires form T2033.
The settlement window is T plus one business day, and the receiving institution must
acknowledge within five business days. Contribution room accumulates annually.</p>
</article>
<section>
<h2>Investment Options</h2>
<p>Stocks provide long-term growth potential. Bonds offer stable income. Real estate
investments can diversify your portfolio. Dividend-yielding stocks are popular for
generating passive income during retirement.</p>
</section>
<section>
<h2>Vacation Planning</h2>
<p>Many retirees enjoy travel. Popular vacation destinations include Hawaii, Europe,
and the Caribbean. Consider booking flights for your travel in advance for better
prices. Hotels with loyalty programs offer rewards points on every vacation.</p>
</section>
</main>
</body></html>
"""

    def test_query_keeps_topical_block(self):
        """Query='RRSP T2033' should keep retirement/transfer block, deprioritize vacation."""
        # Extract with query
        result = ce.extract_main_content(self._PAGE_RETIREMENT, query="RRSP T2033")

        # Topical block (T2033, settlement) should be present
        self.assertIn("T2033", result, "Query-relevant block removed")
        self.assertIn("RRSP", result, "Query-relevant term missing")
        # Vacation block (flights, hotels) should be filtered out or deprioritized
        # We keep ~50% of blocks, so the least-relevant should be dropped
        self.assertNotIn("Hawaii", result, "Off-topic vacation block not filtered")

    def test_query_filters_irrelevant_content(self):
        """Query='vacation travel' should keep travel content, drop RRSP/investments."""
        result = ce.extract_main_content(self._PAGE_RETIREMENT, query="vacation travel")

        # Travel content should survive
        self.assertIn("travel", result.lower())
        # RRSP details should be filtered
        self.assertNotIn("T2033", result, "Query irrelevant block not filtered")

    def test_empty_query_byte_identical_no_query(self):
        """Regression guard: query='' must return byte-identical to no-query call."""
        result_no_query = ce.extract_main_content(self._PAGE_RETIREMENT)
        result_empty_query = ce.extract_main_content(self._PAGE_RETIREMENT, query="")

        self.assertEqual(
            result_no_query, result_empty_query,
            "query='' not byte-identical to no-query"
        )

    def test_query_deterministic(self):
        """Same query on same HTML must produce identical output."""
        result1 = ce.extract_main_content(self._PAGE_RETIREMENT, query="RRSP")
        result2 = ce.extract_main_content(self._PAGE_RETIREMENT, query="RRSP")

        self.assertEqual(result1, result2, "BM25 filtering not deterministic")

    def test_empty_html_with_query_safe(self):
        """Empty HTML + query must not raise."""
        result = ce.extract_main_content("", query="test")
        self.assertEqual(result, "")

    def test_garbage_html_with_query_safe(self):
        """Malformed HTML + query must not raise."""
        result = ce.extract_main_content(
            "<div><p>unclosed <span> tags <a href=x>", query="span"
        )
        # Should not raise; should return something
        self.assertIsInstance(result, str)

    def test_query_with_no_matching_terms(self):
        """Query with no matching terms should fall back gracefully."""
        result = ce.extract_main_content(
            self._PAGE_RETIREMENT, query="xyzabc123notinpage"
        )
        # Should keep at least top 50% of blocks (even with zero scores)
        self.assertIn("Retirement", result, "All blocks removed on no-match query")

    def test_query_single_term(self):
        """Single query term should work."""
        result = ce.extract_main_content(self._PAGE_RETIREMENT, query="stocks")
        self.assertIn("Stocks", result, "Single-term query failed")

    def test_query_multiple_terms(self):
        """Multiple query terms should boost relevance."""
        result = ce.extract_main_content(self._PAGE_RETIREMENT, query="RRSP settlement form T2033")
        # Should contain the RRSP section with multiple matching terms
        self.assertIn("RRSP", result)

    def test_whitespace_only_query_treated_as_empty(self):
        """Whitespace-only query should behave like empty query."""
        result_whitespace = ce.extract_main_content(self._PAGE_RETIREMENT, query="   ")
        result_no_query = ce.extract_main_content(self._PAGE_RETIREMENT)

        self.assertEqual(
            result_whitespace, result_no_query,
            "Whitespace-only query not treated as empty"
        )

    def test_case_insensitive_matching(self):
        """Query matching should be case-insensitive."""
        result_lower = ce.extract_main_content(self._PAGE_RETIREMENT, query="rrsp")
        result_upper = ce.extract_main_content(self._PAGE_RETIREMENT, query="RRSP")

        # Both should produce the same result
        self.assertEqual(result_lower, result_upper, "Case sensitivity in query matching")

    def test_tiny_page_with_query(self):
        """Very small page + query should not crash."""
        html = "<html><body><p>Hi there</p></body></html>"
        result = ce.extract_main_content(html, query="there")
        self.assertIn("Hi", result)

    def test_query_with_max_chars(self):
        """Query filter + max_chars should both apply."""
        result = ce.extract_main_content(
            self._PAGE_RETIREMENT, query="RRSP", max_chars=100
        )
        self.assertLessEqual(len(result), 100)
        # Should still be query-filtered (or we'd get vacation text)
        self.assertNotIn("Hawaii", result)


class TestBM25BlockSplitting(unittest.TestCase):
    """Internal block-splitting logic."""

    def test_split_into_blocks_basic(self):
        """Blocks split by blank lines."""
        text = "Line 1\nLine 2\n\nBlock 2 line 1\nBlock 2 line 2"
        blocks = ce._split_into_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertIn("Line 1", blocks[0])
        self.assertIn("Block 2", blocks[1])

    def test_split_into_blocks_single_block(self):
        """Text with no blank lines = single block."""
        text = "Single block\nwith multiple lines\nbut no gaps"
        blocks = ce._split_into_blocks(text)
        self.assertEqual(len(blocks), 1)

    def test_split_into_blocks_filters_tiny_blocks(self):
        """Blocks with < 2 tokens filtered out."""
        text = "Word\n\nTwo words here\n\nX"
        blocks = ce._split_into_blocks(text)
        # "Word" and "X" have only 1 token each; should be filtered
        self.assertGreater(len(blocks), 0)
        # The "Two words here" block should be present
        self.assertTrue(any("Two" in b for b in blocks))


class TestBM25Tokenization(unittest.TestCase):
    """Tokenization logic."""

    def test_tokenize_basic(self):
        """Simple tokenization."""
        tokens = ce._tokenize_text("Hello world")
        self.assertEqual(tokens, ["hello", "world"])

    def test_tokenize_case_insensitive(self):
        """Tokens lowercase."""
        tokens = ce._tokenize_text("RRSP Form T2033")
        self.assertEqual(tokens, ["rrsp", "form", "t2033"])

    def test_tokenize_punctuation_stripped(self):
        """Punctuation removed."""
        tokens = ce._tokenize_text("Hello, world!")
        self.assertEqual(tokens, ["hello", "world"])

    def test_tokenize_empty(self):
        """Empty text."""
        tokens = ce._tokenize_text("")
        self.assertEqual(tokens, [])


class TestBM25CanonicalRouting(unittest.TestCase):
    """Cohesion guard (#223): block scoring routes to the canonical
    lgwks_pipeline.bm25_score. This module must NOT mint its own BM25 copy."""

    def test_no_local_bm25_duplicate(self):
        """A local _bm25_score would re-fork a primitive that already exists."""
        self.assertFalse(
            hasattr(ce, "_bm25_score"),
            "lgwks_content_extract must not define a local BM25 copy; "
            "route block scoring to lgwks_pipeline.bm25_score (#223).",
        )

    def test_canonical_primitive_behaves(self):
        """The primitive this module relies on ranks matches over non-matches."""
        from lgwks_pipeline import bm25_score
        self.assertGreater(bm25_score(["retirement"], ["retirement", "planning"]), 0.0)
        self.assertEqual(bm25_score(["xyz"], ["retirement", "planning"]), 0.0)
        self.assertEqual(bm25_score([], ["retirement"]), 0.0)


if __name__ == "__main__":
    unittest.main()
