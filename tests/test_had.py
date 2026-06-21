"""Tests for lgwks_had — the Human Assumption Decoder (intent math).
Uses an injected fake classifier so the decode is deterministic without the live eye."""
from __future__ import annotations

import os
import sys
import unittest
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lgwks_had as had


@dataclass
class FakeResult:
    label: str
    top_k: list = field(default_factory=list)
    margin: float = 0.0
    plan_only: bool = False
    confidence: float = 0.0


def _clf(label, top_k, margin, plan_only=False):
    return lambda _text: FakeResult(label=label, top_k=top_k, margin=margin, plan_only=plan_only)


class TestAccept(unittest.TestCase):
    def test_clear_low_risk_intent_accepted(self):
        ir = had.decode("show me the manifest",
                        classify_fn=_clf("manifest", [("manifest", 0.80), ("review", 0.60)], 0.20))
        self.assertEqual(ir.operation, "manifest")
        self.assertEqual(ir.risk, "low")
        a = ir.assumption_ledger[0]
        self.assertEqual(a.status, "accepted_for_low_risk_execution")
        self.assertTrue(ir.routing["execute"])
        self.assertFalse(ir.needs_human())


class TestAbstain(unittest.TestCase):
    def test_high_risk_intent_goes_to_human_even_if_confident(self):
        # confident classification, but a destructive verb must not auto-execute (T0)
        ir = had.decode("delete the production table",
                        classify_fn=_clf("gh harden delete", [("gh harden delete", 0.85), ("x", 0.55)], 0.30))
        self.assertIn(ir.risk, ("high", "critical"))
        self.assertEqual(ir.assumption_ledger[0].status, "human_review")
        self.assertFalse(ir.routing["execute"])
        self.assertTrue(ir.needs_human())

    def test_ambiguous_low_margin_goes_to_review(self):
        ir = had.decode("blarg qux",
                        classify_fn=_clf("wf doctor", [("wf doctor", 0.68), ("wf code", 0.679)], 0.001,
                                         plan_only=True))
        self.assertEqual(ir.assumption_ledger[0].status, "human_review")
        self.assertFalse(ir.routing["execute"])

    def test_empty_utterance_no_execute(self):
        ir = had.decode("", classify_fn=_clf("x", [], 0.0))
        self.assertFalse(ir.routing["execute"])
        self.assertEqual(ir.operation, "")


class TestLedgerShape(unittest.TestCase):
    def test_counter_hypotheses_recorded(self):
        ir = had.decode("crawl a site",
                        classify_fn=_clf("crawl",
                                         [("crawl", 0.83), ("workflow research", 0.79),
                                          ("substrate map", 0.78)], 0.04))
        self.assertEqual(ir.assumption_ledger[0].counter_hypotheses,
                         ["workflow research", "substrate map"])

    def test_schema_conformant_dict(self):
        ir = had.decode("show manifest", classify_fn=_clf("manifest", [("manifest", 0.8)], 0.2))
        d = ir.to_dict()
        for key in ("request_id", "operation", "risk", "routing", "audit", "assumption_ledger"):
            self.assertIn(key, d)
        entry = d["assumption_ledger"][0]
        for key in ("assumption_id", "candidate_hidden_assumption", "posterior_probability", "status"):
            self.assertIn(key, entry)

    def test_deterministic(self):
        fn = _clf("manifest", [("manifest", 0.8), ("x", 0.6)], 0.2)
        self.assertEqual(had.decode("show manifest", classify_fn=fn).to_dict(),
                         had.decode("show manifest", classify_fn=fn).to_dict())


if __name__ == "__main__":
    unittest.main()
