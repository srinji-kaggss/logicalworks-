"""Unit tests for lgwks_search_engine._is_library_query heuristic."""

from __future__ import annotations

import unittest

from lgwks_search_engine import _is_library_query


class TestLgwksSearchEngineCoverage(unittest.TestCase):
    """Coverage tests for the private _is_library_query function."""

    def test_is_library_query_true_for_technical_terms(self):
        """Assert True when query contains a technical keyword (e.g. 'hook')."""
        self.assertTrue(
            _is_library_query("how do I use the useState hook", "react"),
            "Expected True: query contains 'hook' which is a recognized technical keyword",
        )

    def test_is_library_query_false_for_generic_query(self):
        """Assert False when query lacks any recognized technical keyword."""
        self.assertFalse(
            _is_library_query("what is the weather today", "react"),
            "Expected False: query contains no technical keyword (api, hook, class, function, method)",
        )


if __name__ == "__main__":
    unittest.main()
