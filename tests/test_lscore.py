"""
Tests for the L-Score calculator and structured Evidence (Issue #52).

Enterprise assertions:
  * LCalculator produces correct L from synthetic verdict pipelines
  * Evidence structures round-trip through JSON
  * Legacy string evidence is auto-coerced with conservative origin_type=INVENTED
  * A pipeline with only grounded evidence has L=0
  * A pipeline with only invented evidence has L=1
  * check_gate_evidence_completeness flags missing provenance on non-PASS verdicts
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_verify import (
    Evidence, Klass, LCalculator, LScore, OriginType, Outcome, Verdict,
    check_gate_evidence_completeness,
)


class TestEvidence(unittest.TestCase):
    def test_evidence_roundtrip(self):
        """Evidence JSON round-trip preserves all fields."""
        ev = Evidence(
            source_url="https://example.com/src",
            tier="primary",
            origin_type=OriginType.GROUNDED,
            transform_hash="abc123",
        )
        d = ev.to_dict()
        loaded = Evidence.from_dict(d)
        self.assertEqual(loaded, ev)

    def test_verdict_json_with_structured_evidence(self):
        """Verdict with structured evidence round-trips."""
        v = Verdict(
            gate_id="g1",
            outcome=Outcome.PASS,
            klass=Klass.HARD,
            evidence=[
                Evidence(source_url="https://x", tier="primary", origin_type=OriginType.GROUNDED),
                Evidence(tier="secondary", origin_type=OriginType.INFERRED),
            ],
        )
        d = v.to_dict()
        s = json.dumps(d)
        loaded = Verdict.from_dict(json.loads(s))
        self.assertEqual(loaded.gate_id, "g1")
        self.assertEqual(len(loaded.provenance), 2)
        self.assertEqual(loaded.provenance[0].origin_type, OriginType.GROUNDED)
        self.assertEqual(loaded.provenance[1].origin_type, OriginType.INFERRED)

    def test_legacy_string_evidence_coerced_to_invented(self):
        """Legacy string evidence must be auto-coerced with conservative origin_type=INVENTED
        to prevent false-confidence claims."""
        v = Verdict(
            gate_id="legacy-gate",
            outcome=Outcome.PASS,
            klass=Klass.HARD,
            evidence=["old string evidence"],
        )
        prov = v.provenance
        self.assertEqual(len(prov), 1)
        self.assertEqual(prov[0].origin_type, OriginType.INVENTED)
        self.assertEqual(prov[0].tier, "legacy_string")


class TestLCalculator(unittest.TestCase):
    def test_all_grounded_l_is_zero(self):
        """Pipeline with only grounded evidence → L=0."""
        verdicts = [
            Verdict("bot", Outcome.PASS, Klass.HARD, evidence=[
                Evidence(origin_type=OriginType.GROUNDED, tier="primary"),
                Evidence(origin_type=OriginType.GROUNDED, tier="primary"),
            ]),
        ]
        score = LCalculator.from_verdicts(verdicts)
        self.assertEqual(score.L, 0.0)
        self.assertEqual(score.total_claims, 2)
        self.assertEqual(score.grounded_claims, 2)

    def test_all_invented_l_is_one(self):
        """Pipeline with only invented evidence → L=1."""
        verdicts = [
            Verdict("llm", Outcome.PASS, Klass.ADVISORY, evidence=[
                Evidence(origin_type=OriginType.INVENTED, tier="primary"),
            ]),
        ]
        score = LCalculator.from_verdicts(verdicts)
        self.assertEqual(score.L, 1.0)
        self.assertEqual(score.invented_claims, 1)

    def test_mixed_pipeline(self):
        """Mixed provenance yields L in (0,1)."""
        verdicts = [
            Verdict("bot", Outcome.PASS, Klass.HARD, evidence=[
                Evidence(origin_type=OriginType.GROUNDED),
                Evidence(origin_type=OriginType.GROUNDED),
                Evidence(origin_type=OriginType.GROUNDED),
            ]),
            Verdict("bert", Outcome.PASS, Klass.HARD, evidence=[
                Evidence(origin_type=OriginType.INFERRED),
                Evidence(origin_type=OriginType.INFERRED),
            ]),
            Verdict("llm", Outcome.CANNOT_DECIDE, Klass.ADVISORY, evidence=[
                Evidence(origin_type=OriginType.INVENTED),
            ]),
        ]
        score = LCalculator.from_verdicts(verdicts)
        self.assertEqual(score.total_claims, 6)
        self.assertEqual(score.grounded_claims, 3)
        self.assertEqual(score.inferred_claims, 2)
        self.assertEqual(score.invented_claims, 1)
        self.assertAlmostEqual(score.L, 1 / 6, places=6)

    def test_empty_evidence_defaults_to_invented(self):
        """A verdict with no evidence counts as one invented claim."""
        verdicts = [Verdict("empty", Outcome.PASS, Klass.HARD, evidence=[])]
        score = LCalculator.from_verdicts(verdicts)
        self.assertEqual(score.total_claims, 1)
        self.assertEqual(score.invented_claims, 1)
        self.assertEqual(score.L, 1.0)

    def test_lscore_report_format(self):
        score = LScore(total_claims=10, invented_claims=3, inferred_claims=2, grounded_claims=5, L=0.3)
        self.assertIn("L=0.3000", LCalculator.to_report(score))
        self.assertIn("grounded=5", LCalculator.to_report(score))


class TestEvidenceCompleteness(unittest.TestCase):
    def test_complete_when_pass(self):
        ok, reasons = check_gate_evidence_completeness([
            Verdict("g1", Outcome.PASS, Klass.HARD, evidence=[Evidence(origin_type=OriginType.GROUNDED)]),
        ])
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_incomplete_when_fail_without_evidence(self):
        ok, reasons = check_gate_evidence_completeness([
            Verdict("g1", Outcome.FAIL, Klass.HARD, evidence=[]),
        ])
        self.assertFalse(ok)
        self.assertIn("g1", reasons[0])

    def test_incomplete_when_cannot_decide_without_evidence(self):
        ok, reasons = check_gate_evidence_completeness([
            Verdict("g1", Outcome.CANNOT_DECIDE, Klass.HARD, evidence=[]),
        ])
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 1)


if __name__ == "__main__":
    unittest.main()
