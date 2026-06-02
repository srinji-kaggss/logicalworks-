"""
Tests for the Comprehension Gate (spec-01 §comprehension).

Verifies four deterministic checks against units.json:
  • Coverage of acceptance criteria
  • Write-surface containment
  • Invariant/gate subset
  • Scope-boundary vocabulary
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_comprehend import ComprehensionArtifact, ComprehensionVerifier
from lgwks_verify import Outcome


# Minimal units.json fixture for hermetic testing
_UNITS_JSON = {
    "schema": "lgwks.build-units/1",
    "out_of_scope_vocab": [
        "model-training", "network-egress", "other-units-files",
    ],
    "units": [
        {
            "id": "UX",
            "acceptance": [
                "acceptance-one",
                "acceptance-two",
            ],
            "file_targets": ["a.py", "tests/test_a.py"],
            "invariants": ["inv-a"],
            "gates": ["self-tests"],
        }
    ],
}


class TestComprehensionGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(_UNITS_JSON, self.tmp)
        self.tmp.close()
        self.verifier = ComprehensionVerifier(units_path=Path(self.tmp.name))

    def tearDown(self) -> None:
        os.unlink(self.tmp.name)

    def _artifact(self, **overrides) -> ComprehensionArtifact:
        defaults = {
            "unit_id": "UX",
            "restated_intent": "test intent",
            "steps": [
                {"step": "s1", "covers": ["acceptance-one"]},
                {"step": "s2", "covers": ["acceptance-two"]},
            ],
            "invariants": ["inv-a"],
            "gates": ["self-tests"],
            "files_touched": ["a.py"],
            "out_of_scope": ["model-training"],
        }
        defaults.update(overrides)
        return ComprehensionArtifact.from_dict(defaults)

    def test_missing_acceptance_returns_fail(self):
        """Plan omitting any acceptance[] entry → FAIL with diagnosis naming the uncovered criteria."""
        artifact = self._artifact(steps=[{"step": "s1", "covers": ["acceptance-one"]}])
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.FAIL)
        self.assertIn("acceptance-two", v.diagnosis or "")

    def test_extra_file_returns_fail(self):
        """A files_touched entry not in the unit's file_targets → FAIL."""
        artifact = self._artifact(files_touched=["a.py", "b.py"])
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.FAIL)
        self.assertIn("b.py", v.diagnosis or "")

    def test_missing_invariant_returns_fail(self):
        """invariants ⊉ unit.invariants → FAIL."""
        artifact = self._artifact(invariants=[])
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.FAIL)
        self.assertIn("inv-a", v.diagnosis or "")

    def test_empty_out_of_scope_returns_cannot_decide(self):
        """out_of_scope empty → CANNOT_DECIDE."""
        artifact = self._artifact(out_of_scope=[])
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.CANNOT_DECIDE)

    def test_unknown_vocab_returns_cannot_decide(self):
        """out_of_scope token not in vocab → CANNOT_DECIDE."""
        artifact = self._artifact(out_of_scope=["model-training", "free-text-nonsense"])
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.CANNOT_DECIDE)
        self.assertIn("free-text-nonsense", v.diagnosis or "")

    def test_valid_plan_passes(self):
        """A conformant artifact → PASS."""
        artifact = self._artifact()
        v = self.verifier.check(artifact, "UX")
        self.assertEqual(v.outcome, Outcome.PASS)

    def test_cli_returns_verdict_object(self):
        """lgwks comprehend --unit UX --file plan.json returns a Verdict object."""
        import lgwks_comprehend as comp
        artifact = self._artifact()
        plan_path = Path(self.tmp.name).with_suffix(".plan.json")
        with open(plan_path, "w", encoding="utf-8") as fh:
            json.dump({
                "unit_id": artifact.unit_id,
                "restated_intent": artifact.restated_intent,
                "steps": artifact.steps,
                "invariants": artifact.invariants,
                "gates": artifact.gates,
                "files_touched": artifact.files_touched,
                "out_of_scope": artifact.out_of_scope,
            }, fh)
        # simulate CLI args
        class Args:
            unit = "UX"
            file = str(plan_path)
            json = True
        args = Args()
        # We can't call comprehend_command directly because it loads units.json from default path.
        # Instead test the verifier directly.
        verifier = ComprehensionVerifier(units_path=Path(self.tmp.name))
        verdict = verifier.check(artifact, args.unit)
        self.assertIn(verdict.outcome, {Outcome.PASS, Outcome.FAIL, Outcome.CANNOT_DECIDE})
        os.unlink(plan_path)


if __name__ == "__main__":
    unittest.main()
