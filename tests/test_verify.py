"""
Tests for the Verifier oracle (spec-01).

Verifies the three L4 invariants:
  • HARD short-circuits on first non-PASS
  • internal exception → CANNOT_DECIDE, never PASS
  • Verdict JSON round-trip for cognition-log append-only semantics
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_verify import GateRegistry, Klass, Outcome, Verdict, Verifier, run_pipeline


class HardFailVerifier:
    gate_id = "hard-fail"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.FAIL, klass=self.klass, diagnosis="always fails")


class HardPassVerifier:
    gate_id = "hard-pass"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)


class AdvisoryPassVerifier:
    gate_id = "advisory-pass"
    klass = Klass.ADVISORY
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass, score=0.8)


class RaisingVerifier:
    gate_id = "raising"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        raise RuntimeError("boom")


class TestPipeline(unittest.TestCase):
    def test_hard_short_circuits_on_first_non_pass(self):
        """run_pipeline returns (False, verdicts) on the first HARD non-PASS verdict."""
        reg = GateRegistry(
            hard=[HardPassVerifier(), HardFailVerifier(), HardPassVerifier()],
            advisory=[AdvisoryPassVerifier()],
        )
        ok, verdicts = run_pipeline("subject", "context", reg)
        self.assertFalse(ok)
        self.assertEqual(len(verdicts), 2)  # first pass, then fail, then short-circuit
        self.assertEqual(verdicts[0].outcome, Outcome.PASS)
        self.assertEqual(verdicts[1].outcome, Outcome.FAIL)

    def test_internal_exception_mapped_to_cannot_decide(self):
        """A verifier raising internally is caught and mapped to CANNOT_DECIDE, never PASS."""
        reg = GateRegistry(hard=[RaisingVerifier()])
        ok, verdicts = run_pipeline("subject", "context", reg)
        self.assertFalse(ok)
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0].outcome, Outcome.CANNOT_DECIDE)
        self.assertIn("boom", verdicts[0].diagnosis or "")

    def test_verdict_json_roundtrip(self):
        """Every Verdict is JSON-serialisable for the cognition-log."""
        v = Verdict(
            gate_id="g1",
            outcome=Outcome.CANNOT_DECIDE,
            klass=Klass.HARD,
            score=None,
            evidence=["e1", "e2"],
            diagnosis="d1",
        )
        d = v.to_dict()
        payload = json.dumps(d)
        loaded = json.loads(payload)
        restored = Verdict.from_dict(loaded)
        self.assertEqual(restored.gate_id, v.gate_id)
        self.assertEqual(restored.outcome, v.outcome)
        self.assertEqual(restored.klass, v.klass)
        self.assertEqual(restored.score, v.score)
        self.assertEqual(restored.evidence, v.evidence)
        self.assertEqual(restored.diagnosis, v.diagnosis)

    def test_advisory_fail_is_unrepresentable(self):
        """ADVISORY outcome ∈ {PASS, CANNOT_DECIDE} only."""
        with self.assertRaises(ValueError):
            Verdict(gate_id="a", outcome=Outcome.FAIL, klass=Klass.ADVISORY)

    def test_advisory_cannot_decide_is_allowed(self):
        """ADVISORY CANNOT_DECIDE is representable."""
        v = Verdict(gate_id="a", outcome=Outcome.CANNOT_DECIDE, klass=Klass.ADVISORY)
        self.assertEqual(v.outcome, Outcome.CANNOT_DECIDE)


if __name__ == "__main__":
    unittest.main()
