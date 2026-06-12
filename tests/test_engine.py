"""Tests for lgwks_engine — U6 Subconscious Engine.

T1  schema structure: required keys present and typed correctly
T2  determinism: same prompt -> identical output across calls
T3  latency: <1s warm
T4  graceful no-graph: returns valid schema even without entity_graph.db
T5  unknown prompt: graceful empty matches, no crash
T6  slop flag detection: hedges and multi-intent pattern trigger flags
T7  score bounds: C in [0,1], G in [0,1], P in [0.30, 0.90]
T8  pathways: top-3 verbs match first three selections
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_engine as eng


_PROMPT = "find all files changed in the last commit and check for SQL injection"


class TestEngineSchema(unittest.TestCase):
    def test_t1_required_keys(self):
        r = eng.run_engine(_PROMPT)
        self.assertEqual(r["schema"], "lgwks.engine.schema.v1")
        self.assertIn("prompt", r)
        self.assertIn("attention", r)
        self.assertIn("retrieval", r)
        self.assertIn("last_state", r)
        ins = r["insights"]
        self.assertIn("scores", ins)
        self.assertIn("selections", ins)
        self.assertIn("flags", ins)
        self.assertIn("actions_taken", ins)
        self.assertIn("pathways", r)
        scores = ins["scores"]
        self.assertIn("coverage_C", scores)
        self.assertIn("gap_G", scores)
        self.assertIn("confidence_P", scores)

    def test_t1_types(self):
        r = eng.run_engine(_PROMPT)
        self.assertIsInstance(r["retrieval"], list)
        self.assertIsInstance(r["insights"]["selections"], list)
        self.assertIsInstance(r["insights"]["flags"], list)
        self.assertIsInstance(r["pathways"], list)

    def test_t2_deterministic(self):
        r1 = eng.run_engine(_PROMPT)
        r2 = eng.run_engine(_PROMPT)
        self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))

    def test_t3_latency(self):
        t0 = time.time()
        eng.run_engine("summarise the last session")
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, f"engine took {elapsed:.3f}s (>1s)")

    def test_t4_no_graph_graceful(self):
        from pathlib import Path
        r = eng.run_engine(_PROMPT, db_path=Path("/nonexistent/path/graph.db"))
        self.assertEqual(r["schema"], "lgwks.engine.schema.v1")
        self.assertEqual(r["retrieval"], [])
        # scores still valid
        C = r["insights"]["scores"]["coverage_C"]
        self.assertGreaterEqual(C, 0.0)

    def test_t5_unknown_prompt_no_crash(self):
        r = eng.run_engine("xyzzy frobnicate the warp core")
        self.assertEqual(r["schema"], "lgwks.engine.schema.v1")
        self.assertIsInstance(r["insights"]["selections"], list)

    def test_t6_slop_flags(self):
        r = eng.run_engine("I think this should work, probably")
        self.assertIn("unverified_claim", r["insights"]["flags"])

    def test_t6_intent_drift_flag(self):
        r = eng.run_engine("fetch the file and also parse it and then store it and also index it")
        self.assertIn("intent_drift", r["insights"]["flags"])

    def test_t7_score_bounds(self):
        for prompt in [_PROMPT, "xyzzy frobnicate warp core", "embed a PDF"]:
            r = eng.run_engine(prompt)
            s = r["insights"]["scores"]
            self.assertGreaterEqual(s["coverage_C"], 0.0)
            self.assertLessEqual(s["coverage_C"], 1.0)
            # gap_G is None when the graph is absent (grounding unavailable)
            if s["gap_G"] is not None:
                self.assertGreaterEqual(s["gap_G"], 0.0)
                self.assertLessEqual(s["gap_G"], 1.0)
            # P is now a constant-free index over [0, 1] (was magic-bounded [0.30, 0.90])
            self.assertGreaterEqual(s["confidence_P"], 0.0)
            self.assertLessEqual(s["confidence_P"], 1.0)

    def test_t8_pathways_match_selections(self):
        r = eng.run_engine(_PROMPT)
        sels = r["insights"]["selections"]
        pathways = r["pathways"]
        expected = [s["verb"] for s in sels[:3]]
        self.assertEqual(pathways, expected)


if __name__ == "__main__":
    unittest.main()
