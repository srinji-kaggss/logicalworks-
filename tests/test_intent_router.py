"""
test_intent_router — tests for the deterministic intent router (Finding H3).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lgwks_intent_router as router

class TestIntentRouter(unittest.TestCase):
    def test_heuristic_classify_basic(self):
        # Research
        res = router._heuristic_classify("crawl this website")
        self.assertEqual(res["category"], "research")
        self.assertGreater(res["confidence"], 0.4)
        self.assertIn("matched keywords", res["reason"])
        
        # Code
        res = router._heuristic_classify("fix this bug and review the changes")
        self.assertEqual(res["category"], "code")
        
        # Empty
        res = router._heuristic_classify("")
        self.assertEqual(res["category"], "unknown")
        self.assertEqual(res["confidence"], 0.0)

    def test_density_based_scoring(self):
        # High density (1/1)
        high = router._heuristic_classify("crawl")
        # Low density (1/10)
        low = router._heuristic_classify("I was wondering if you could please crawl this thing")
        
        self.assertGreater(high["confidence"], low["confidence"])

    def test_taxonomy_derivation(self):
        cats = router.get_categories()
        self.assertIn("research", cats)
        self.assertIn("code", cats)
        self.assertIn("unknown", cats)
        
        # Ensure it's sorted
        self.assertEqual(cats[:-1], sorted(cats[:-1]))
        self.assertEqual(cats[-1], "unknown")

    def test_route_mapping(self):
        res = router.route("find latest research papers")
        self.assertEqual(res["category"], "research")
        self.assertEqual(res["verb"], "jarvis crawl")
        self.assertIn("--prompt", res["args"])

    def test_classify_full_cycle(self):
        # Force heuristic path
        res = router.classify("review this PR")
        self.assertEqual(res["method"], "heuristic")
        self.assertEqual(res["category"], "code")
        self.assertTrue("matched keywords" in res["reason"])

if __name__ == "__main__":
    unittest.main()
