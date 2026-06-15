"""Tests for lgwks_oriented — the Structural Inference basement seam (#172).

Every assertion is a hand-checkable bit value: this is the calculator test
applied to the oriented objective itself.
"""

from __future__ import annotations

import math
import unittest

import lgwks_oriented as oriented


class TestPredictionErrorBits(unittest.TestCase):
    def test_surprisal_of_certain_outcome_is_zero(self):
        self.assertEqual(oriented.prediction_error_bits({"a": 1.0}, "a"), 0.0)

    def test_surprisal_of_fair_coin_is_one_bit(self):
        # -log2(0.5) = 1 bit, by hand
        self.assertAlmostEqual(oriented.prediction_error_bits({"h": 1, "t": 1}, "h"), 1.0)

    def test_quarter_probability_is_two_bits(self):
        # normalize {a:1,b:3} -> a=0.25 -> -log2(0.25)=2
        self.assertAlmostEqual(oriented.prediction_error_bits({"a": 1, "b": 3}, "a"), 2.0)

    def test_unsupported_outcome_is_infinite(self):
        self.assertEqual(oriented.prediction_error_bits({"a": 1.0}, "z"), math.inf)


class TestIntentDivergenceBits(unittest.TestCase):
    def test_flat_intent_is_zero_the_structural_limit(self):
        # preferred=None => no teleological pressure => collapses to #172
        self.assertEqual(oriented.intent_divergence_bits({"a": 1, "b": 1}, None), 0.0)

    def test_matching_preference_is_zero(self):
        # KL(P||P) = 0
        d = oriented.intent_divergence_bits({"a": 1, "b": 1}, {"a": 1, "b": 1})
        self.assertAlmostEqual(d, 0.0)

    def test_known_kl_value(self):
        # P={a:1}, Q={a:0.5,b:0.5} -> KL = 1*log2(1/0.5) = 1 bit, by hand
        d = oriented.intent_divergence_bits({"a": 1, "b": 1}, {"a": 1})
        self.assertAlmostEqual(d, 1.0)

    def test_unachievable_preference_is_infinite(self):
        # prefer 'z' the model can't achieve -> +inf bits (intent demands missing structure)
        self.assertEqual(oriented.intent_divergence_bits({"a": 1.0}, {"z": 1.0}), math.inf)


class TestOrientedLossNestedLimits(unittest.TestCase):
    def test_bayes_limit_flat_intent_frozen_structure(self):
        obj = oriented.oriented_loss(2.0, 3.0, 0.0, structure_frozen=True)
        self.assertEqual(obj.mode, "bayes")
        self.assertEqual(obj.total, 5.0)  # 2+3+0, weights 1

    def test_structural_limit_flat_intent_free_structure(self):
        obj = oriented.oriented_loss(2.0, 3.0, 0.0, structure_frozen=False)
        self.assertEqual(obj.mode, "structural")
        self.assertEqual(obj.total, 5.0)

    def test_oriented_when_intent_active(self):
        obj = oriented.oriented_loss(2.0, 3.0, 1.5, structure_frozen=False)
        self.assertEqual(obj.mode, "oriented")
        self.assertEqual(obj.total, 6.5)

    def test_default_args_are_bayes_limit(self):
        # a caller that hasn't supplied intent/structure gets today's behavior
        obj = oriented.oriented_loss(1.0, 1.0)
        self.assertEqual(obj.mode, "bayes")

    def test_schema_id_stable(self):
        obj = oriented.oriented_loss(0.0, 0.0)
        self.assertEqual(obj.schema, "lgwks.oriented.objective.v1")
        self.assertEqual(obj.as_dict()["schema"], "lgwks.oriented.objective.v1")


class TestVertexBirthGate(unittest.TestCase):
    def test_birth_justified_when_gain_exceeds_tau(self):
        # before=10, after=6, tau=3 -> 6 < 10-3=7 -> True
        self.assertTrue(oriented.vertex_birth_justified(10.0, 6.0, 3.0))

    def test_birth_rejected_when_gain_below_tau(self):
        # before=10, after=8, tau=3 -> 8 < 7 is False
        self.assertFalse(oriented.vertex_birth_justified(10.0, 8.0, 3.0))

    def test_birth_rejected_at_exact_threshold(self):
        # strict inequality: after == before-tau does not justify
        self.assertFalse(oriented.vertex_birth_justified(10.0, 7.0, 3.0))

    def test_negative_tau_rejected(self):
        with self.assertRaises(ValueError):
            oriented.vertex_birth_justified(10.0, 1.0, -1.0)


if __name__ == "__main__":
    unittest.main()
