"""Test coverage for lgwks_map — backfill #349."""

import unittest

import lgwks_map


class TestLgwksMapCoverage(unittest.TestCase):
    """Tests for lgwks_map.map_intent."""

    def test_map_intent_returns_expected_dict_shape(self):
        """map_intent returns a dict with the documented schema keys."""
        result = lgwks_map.map_intent("crawl a website and extract data")
        self.assertIsInstance(result, dict)
        # Verify all documented keys are present.
        expected_keys = {
            "schema", "query", "query_tokens",
            "verb_count", "matched", "matches", "note",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        # Light type checks on known fields.
        self.assertEqual(result["schema"], "lgwks.map.v1")
        self.assertEqual(result["query"], "crawl a website and extract data")
        self.assertIsInstance(result["query_tokens"], list)
        self.assertIsInstance(result["verb_count"], int)
        self.assertIsInstance(result["matched"], int)
        self.assertIsInstance(result["matches"], list)
        self.assertIsInstance(result["note"], str)

    def test_map_intent_is_deterministic(self):
        """Calling map_intent twice with the same intent returns equal results."""
        intent = "crawl a website and extract data"
        result1 = lgwks_map.map_intent(intent)
        result2 = lgwks_map.map_intent(intent)
        self.assertEqual(result1, result2)


if __name__ == "__main__":
    unittest.main()
