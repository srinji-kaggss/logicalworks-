"""
Tests for the Tier-E Machine harness (build #3): cold-start refiner + champion/challenger governance.
Verifies the discriminative jobs (classify, gap-detect, specificity), the ABSTAIN membrane (won't guess
thin intent), agent keyword augmentation, and the calibration-gated promotion.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_machine as machine


class TestRefiner(unittest.TestCase):
    def test_classifies_known_intent(self):
        cls, conf = machine.classify_intent("should I invest in Canada Life, buy or hold")
        self.assertEqual(cls, "investment")
        self.assertGreater(conf, 0.0)

    def test_unknown_intent_is_honest(self):
        cls, conf = machine.classify_intent("xyzzy plugh frobnicate")
        self.assertEqual(cls, "unknown")
        self.assertEqual(conf, 0.0)

    def test_detect_gaps_finds_missing_slots(self):
        gaps = machine.detect_gaps("Canada Life", "investment")  # no timeframe, no decision verb
        self.assertIn("timeframe", gaps)
        self.assertIn("decision", gaps)

    def test_specificity_rewards_concrete_penalizes_vague(self):
        thin = machine.specificity("do stuff")
        rich = machine.specificity("should I buy Canada Life stock over a 3 year horizon given 2025 revenue")
        self.assertLess(thin, rich)

    def test_thin_intent_abstains_and_asks(self):
        r = machine.refine("Canada Life", actor="human", log=False)
        self.assertTrue(r["abstain"], "thin intent must bounce, not guess")
        self.assertTrue(r["questions"], "abstain carries leading questions for each gap")

    def test_specific_intent_proceeds(self):
        r = machine.refine("should I buy or hold Canada Life stock over a 3 year horizon", actor="human", log=False)
        self.assertFalse(r["abstain"])
        self.assertEqual(r["intent_class"], "investment")

    def test_agent_actor_augments_with_quality_keywords(self):
        r = machine.refine("compare Rust vs Go on speed", actor="agent", log=False)
        self.assertIn("avoid-slop", r["augmented"])
        self.assertNotIn("avoid-slop", r["intent"], "augmentation never mutates the original intent")

    def test_refine_logs_to_cognition_corpus(self):
        import lgwks_cognition
        tmp = tempfile.mkdtemp()
        lgwks_cognition._DIR = Path(tmp) / "cognition"
        machine.refine("should I invest in X over 2 years, buy or hold", actor="human", log=True)
        corpus = lgwks_cognition.CognitionLog("intent").corpus("intent_commit")
        self.assertEqual(len(corpus), 1, "every refine seeds the distillation corpus")


class TestGovernance(unittest.TestCase):
    def test_promote_blocks_calibration_regression(self):
        champion = {"calibration": [{"p": 0.9, "outcome": 1}, {"p": 0.1, "outcome": 0}]}   # well-calibrated
        challenger = {"calibration": [{"p": 0.1, "outcome": 1}, {"p": 0.9, "outcome": 0}]}  # badly calibrated
        d = machine.promote(challenger, champion)
        self.assertFalse(d["promote"], "a challenger that regresses calibration is NOT promoted")

    def test_promote_allows_held_calibration(self):
        champion = {"calibration": [{"p": 0.8, "outcome": 1}]}
        challenger = {"calibration": [{"p": 0.85, "outcome": 1}]}
        self.assertTrue(machine.promote(challenger, champion)["promote"])

    def test_snapshot_is_content_addressed(self):
        tmp = tempfile.mkdtemp()
        machine._DIR = Path(tmp) / "machine"
        a = machine.snapshot({"version": 1, "rules": "x"})
        b = machine.snapshot({"version": 1, "rules": "x"})
        self.assertEqual(a["hash"], b["hash"], "same state → same hash (turn-back id)")
        self.assertEqual(machine.freeze(a["hash"])["frozen"], a["hash"])


if __name__ == "__main__":
    unittest.main()
