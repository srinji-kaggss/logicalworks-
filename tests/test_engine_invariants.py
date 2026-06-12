"""Invariant audit for lgwks_engine — U6.1 (issue #83).

This is the *agnostic* audit: it certifies the math by algebraic invariants that
must hold for ANY inputs, not by a domain-specific ground-truth set. The pure
operators (_decisiveness, _aggregate) are tested directly with synthetic inputs;
run_engine is checked for the degeneracy regression and score bounds.

I1 range          I2 determinism      I3 monotonicity     I4 cardinality-invariance
I6 null-collapse  I7 boundary         relabel-invariance  (regression: G != 1 - C)

Deferred (NOT audited here — see #83): I8 padding/verbosity-invariance (needs
offline demand-weighting), N novelty (needs the Qwen embedding layer).
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_engine as eng


class TestDecisiveness(unittest.TestCase):
    def test_i1_range(self):
        for scores in ([], [0.0], [1.0], [3.0, 1.0], [0.5, 0.5, 0.5], [1.333, 1.0, 1.0]):
            d = eng._decisiveness(scores)
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, 1.0)

    def test_i3_monotonicity(self):
        # a clearer dominant match -> higher decisiveness
        tie = eng._decisiveness([0.5, 0.5])
        clear = eng._decisiveness([0.9, 0.1])
        dominant = eng._decisiveness([0.99, 0.01])
        self.assertLess(tie, clear)
        self.assertLess(clear, dominant)
        self.assertAlmostEqual(tie, 0.0, places=3)

    def test_i4_cardinality_invariance(self):
        # adding a zero-score (non-matching) capability must not change d
        base = eng._decisiveness([3.0, 1.0])
        padded = eng._decisiveness([3.0, 1.0, 0.0, 0.0, 0.0])
        self.assertEqual(base, padded)

    def test_relabel_invariance(self):
        # d depends only on the score multiset, never on order/labels
        self.assertEqual(eng._decisiveness([3.0, 1.0, 0.5]),
                         eng._decisiveness([0.5, 3.0, 1.0]))

    def test_i7_boundary(self):
        self.assertEqual(eng._decisiveness([]), 0.0)        # nothing -> not decisive
        self.assertEqual(eng._decisiveness([2.0]), 1.0)     # single match -> fully decisive
        self.assertEqual(eng._decisiveness([1.0, 1.0]), 0.0)  # tie -> not decisive


class TestAggregate(unittest.TestCase):
    def test_i1_range(self):
        for axes in ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.5, 0.3, 0.9), (0.6, None, 0.4)):
            p = eng._aggregate(*axes)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_i6_null_collapse(self):
        # any zero axis collapses the index to 0
        self.assertEqual(eng._aggregate(0.0, 0.9, 0.9), 0.0)
        self.assertEqual(eng._aggregate(0.9, 0.0, 0.9), 0.0)
        self.assertEqual(eng._aggregate(0.9, 0.9, 0.0), 0.0)

    def test_none_axes_drop_out(self):
        # an unavailable (None) axis drops out rather than zeroing the index
        self.assertEqual(eng._aggregate(0.5, None, 0.5), eng._aggregate(0.5, 0.5))
        self.assertGreater(eng._aggregate(0.5, None, 0.5), 0.0)

    def test_i3_monotonicity(self):
        base = eng._aggregate(0.5, 0.5, 0.5)
        higher = eng._aggregate(0.5, 0.5, 0.9)
        self.assertLess(base, higher)

    def test_i7_boundary(self):
        self.assertEqual(eng._aggregate(1.0, 1.0, 1.0), 1.0)  # perfect -> 1
        self.assertEqual(eng._aggregate(), 0.0)               # nothing available -> 0

    def test_non_finite_dropped_not_maxed(self):
        # inf/nan must NOT become max confidence (min(1.0, nan) bug) — they drop out.
        self.assertEqual(eng._aggregate(float("inf"), 0.5), eng._aggregate(0.5))
        self.assertEqual(eng._aggregate(float("nan"), 0.5), eng._aggregate(0.5))
        self.assertTrue(math.isfinite(eng._decisiveness([float("inf"), 1.0])))
        self.assertTrue(math.isfinite(eng._decisiveness([float("nan"), float("nan")])))


class TestRunEngineContract(unittest.TestCase):
    PROMPT = "refactor the auth module and check for SQL injection"

    def test_degeneracy_regression(self):
        # The whole point of #83. Force the ungrounded branch for determinism.
        s = eng.run_engine(self.PROMPT, db_path=Path("/nonexistent/graph.db"))["insights"]["scores"]
        C, P = s["coverage_C"], s["confidence_P"]
        # Old engine ALWAYS returned gap_G = round(1 - C, 3) (a float, never None);
        # the new one returns None when ungrounded -> the "G = 1 - C" construction is gone.
        self.assertIsNone(s["gap_G"])
        self.assertEqual(s["grounding_status"], "unavailable")
        # P is no longer the old magic-constant closed form in C.
        old_P = round(0.30 + 0.58 * C * (1.0 - 0.2 * max(0.0, 1.0 - C)), 3)
        self.assertNotEqual(P, old_P)
        self.assertIn("decisiveness_d", s)

    def test_i1_run_bounds(self):
        for p in [self.PROMPT, "embed a PDF", "xyzzy frobnicate", ""]:
            s = eng.run_engine(p)["insights"]["scores"]
            self.assertGreaterEqual(s["coverage_C"], 0.0)
            self.assertLessEqual(s["coverage_C"], 1.0)
            self.assertGreaterEqual(s["decisiveness_d"], 0.0)
            self.assertLessEqual(s["decisiveness_d"], 1.0)
            self.assertGreaterEqual(s["confidence_P"], 0.0)
            self.assertLessEqual(s["confidence_P"], 1.0)
            self.assertIn(s["grounding_status"], ("grounded", "unresolved", "unavailable"))

    def test_i2_determinism(self):
        a = eng.run_engine(self.PROMPT)
        b = eng.run_engine(self.PROMPT)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_corrupt_graph_is_unavailable_not_zero_grounded(self):
        # A corrupt/unreadable DB must read as grounding *unavailable* (drops out),
        # NOT as "queried, grounded nothing" (which would silently zero P).
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"this is not a sqlite database")
            bad = Path(f.name)
        try:
            s = eng.run_engine(self.PROMPT, db_path=bad)["insights"]["scores"]
            self.assertEqual(s["grounding_status"], "unavailable")
            self.assertIsNone(s["gap_G"])
        finally:
            bad.unlink(missing_ok=True)

    def test_ungrounded_does_not_zero_confidence(self):
        # no graph -> grounding unavailable, but a covered+decisive prompt still
        # yields P > 0 (grounding drops out; it does not force confidence to 0).
        s = eng.run_engine(self.PROMPT, db_path=Path("/nonexistent/graph.db"))["insights"]["scores"]
        self.assertEqual(s["grounding_status"], "unavailable")
        self.assertIsNone(s["gap_G"])
        if s["coverage_C"] > 0 and s["decisiveness_d"] > 0:
            self.assertGreater(s["confidence_P"], 0.0)


if __name__ == "__main__":
    unittest.main()
