"""Tests for lgwks_algorithms — the L4 narrow-ML catalog (deterministic, stdlib)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lgwks_algorithms as alg


class TestSpikeDetection(unittest.TestCase):
    def test_rolling_z_flags_spike(self):
        series = [10.0] * 20 + [100.0]
        v = alg.rolling_z_score(series, threshold=3.0)
        self.assertTrue(v.flag)
        self.assertGreater(v.score, 3.0)

    def test_rolling_z_quiet_on_flat(self):
        series = [10.0, 10.1, 9.9, 10.0, 10.2, 9.8, 10.05]
        self.assertFalse(alg.rolling_z_score(series).flag)

    def test_rolling_z_empty_safe(self):
        v = alg.rolling_z_score([])
        self.assertFalse(v.flag)
        self.assertEqual(v.score, 0.0)

    def test_ewma_smooths_and_is_deterministic(self):
        s = [1.0, 2.0, 3.0, 4.0, 5.0]
        a, b = alg.ewma(s), alg.ewma(s)
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(s))
        self.assertLess(a[-1], s[-1])  # smoothed lags the raw rise

    def test_ewma_deviation_flags_breakout(self):
        series = [5.0, 5.1, 4.9, 5.0, 5.05, 4.95, 50.0]
        self.assertTrue(alg.ewma_deviation(series, threshold=3.0).flag)


class TestLogistic(unittest.TestCase):
    def test_fit_separates_linearly_separable(self):
        # x>0 -> 1, x<0 -> 0 on a single feature
        X = [[-3.0], [-2.0], [-1.0], [1.0], [2.0], [3.0]]
        y = [0, 0, 0, 1, 1, 1]
        m = alg.fit_logistic(X, y, epochs=600, lr=0.3)
        self.assertGreater(m.predict_proba([4.0]), 0.7)
        self.assertLess(m.predict_proba([-4.0]), 0.3)

    def test_fit_is_deterministic(self):
        X, y = [[0.0], [1.0], [2.0], [3.0]], [0, 0, 1, 1]
        self.assertEqual(alg.fit_logistic(X, y).weights, alg.fit_logistic(X, y).weights)

    def test_fit_rejects_mismatched(self):
        with self.assertRaises(ValueError):
            alg.fit_logistic([[1.0]], [0, 1])


class TestCatalog(unittest.TestCase):
    def test_catalog_status_separates_live_and_deferred(self):
        s = alg.catalog_status()
        self.assertIn("rolling_z_score", s["live"])
        self.assertIn("logistic_regression", s["live"])
        self.assertIn("lightgbm", s["deferred"])
        self.assertEqual(s["deferred"]["lightgbm"], "lightgbm")


if __name__ == "__main__":
    unittest.main()
