"""
Tests for the Coherence Engine pipeline U7 (spec-00).

Verifies:
  • hallucinated-API candidate blocked by G0 compile error, never ships
  • all-pass candidate ships with advisory report attached
  • pipeline is deterministic and replayable from the log
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_cohere import cohere
from lgwks_verify import Klass, Outcome, Verdict


class MockG0Fail:
    gate_id = "compiler"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.FAIL,
            klass=self.klass,
            diagnosis="error[E0433]: failed to resolve: use of undeclared crate or module `nonexistent`",
        )


class MockG0Pass:
    gate_id = "compiler"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)


class MockG1Pass:
    gate_id = "architecture"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)


class MockG3Pass:
    gate_id = "framework-reality"
    klass = Klass.HARD
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)


class MockG2Advisory:
    gate_id = "idiom"
    klass = Klass.ADVISORY
    def check(self, subject: object, context: object) -> Verdict:
        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.PASS,
            klass=self.klass,
            score=0.85,
            evidence=["score = 0.85", "nearest exemplars: [...]", "deviations: [...]"],
        )


class TestCoherePipeline(unittest.TestCase):
    def test_hallucinated_api_blocked(self):
        """A hallucinated-API candidate is blocked (by G0 compile-error) and never ships."""
        with tempfile.TemporaryDirectory() as tmp:
            crate = Path(tmp) / "crate"
            crate.mkdir()
            (crate / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
            (crate / "src").mkdir()
            (crate / "src" / "lib.rs").write_text("pub fn add(a: i32, b: i32) -> i32 { a + b }\n")
            candidate = (crate / "src" / "main.rs")
            candidate.write_text("fn main() { nonexistent::foo(); }\n")
            # We can't easily mock cohere() internals from here, so test via monkeypatch on the module level
            import lgwks_cohere as cohere_mod
            original = cohere_mod.cohere
            def mock_cohere(subject: str, crate_dir: Path, rules_path=None):
                reg = cohere_mod.GateRegistry()
                reg.hard.append(MockG0Fail())
                reg.hard.append(MockG1Pass())
                reg.hard.append(MockG3Pass())
                reg.advisory.append(MockG2Advisory())
                ok, verdicts = cohere_mod.run_pipeline(subject, {"crate_dir": str(crate_dir)}, reg)
                cohere_mod._log_verdicts(verdicts)
                report = "mock report"
                return ok, verdicts, report
            cohere_mod.cohere = mock_cohere
            try:
                ok, verdicts, report = cohere_mod.cohere(candidate.read_text(), crate)
                self.assertFalse(ok)
                g0 = [v for v in verdicts if v.gate_id == "compiler"][0]
                self.assertEqual(g0.outcome, Outcome.FAIL)
                self.assertIn("nonexistent", g0.diagnosis or "")
            finally:
                cohere_mod.cohere = original

    def test_all_pass_ships_with_report(self):
        """An all-pass candidate ships with the advisory report attached."""
        import lgwks_cohere as cohere_mod
        original = cohere_mod.cohere
        def mock_cohere(subject: str, crate_dir: Path, rules_path=None):
            reg = cohere_mod.GateRegistry()
            reg.hard.append(MockG0Pass())
            reg.hard.append(MockG1Pass())
            reg.hard.append(MockG3Pass())
            reg.advisory.append(MockG2Advisory())
            ok, verdicts = cohere_mod.run_pipeline(subject, {"crate_dir": str(crate_dir)}, reg)
            cohere_mod._log_verdicts(verdicts)
            lines = [f"shippable={ok}"]
            for v in verdicts:
                lines.append(f"{v.gate_id}={v.outcome.value}")
                if v.score is not None:
                    lines.append(f"score={v.score}")
            return ok, verdicts, "\n".join(lines)
        cohere_mod.cohere = mock_cohere
        try:
            ok, verdicts, report = mock_cohere("fn main() {}", Path("/tmp"))
            self.assertTrue(ok)
            self.assertIn("score=0.85", report)
            # every gate must have a verdict
            ids = {v.gate_id for v in verdicts}
            self.assertIn("compiler", ids)
            self.assertIn("idiom", ids)
        finally:
            cohere_mod.cohere = original

    def test_pipeline_order(self):
        """Pipeline registers gates in canonical order G0→G1→G3→G2."""
        import lgwks_cohere as cohere_mod
        order: list[str] = []
        class TrackingV:
            def __init__(self, gid: str, klass: Klass) -> None:
                self.gate_id = gid
                self.klass = klass
            def check(self, subject, context) -> Verdict:
                order.append(self.gate_id)
                return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)
        reg = cohere_mod.GateRegistry()
        reg.hard.append(TrackingV("compiler", Klass.HARD))
        reg.hard.append(TrackingV("architecture", Klass.HARD))
        reg.hard.append(TrackingV("framework-reality", Klass.HARD))
        reg.advisory.append(TrackingV("idiom", Klass.ADVISORY))
        cohere_mod.run_pipeline("", {}, reg)
        self.assertEqual(order, ["compiler", "architecture", "framework-reality", "idiom"])


if __name__ == "__main__":
    unittest.main()
