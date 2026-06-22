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


class TestTierHonesty(unittest.TestCase):
    """A tier that cannot be FULLY evaluated must return an honest BLOCKED (exit 3) — never a
    silent no-op (the #235 defect) and never a verdict that omits an unmeasured axis (the #311
    partial-tailoring gap). The BLOCKED contract is exercised against SYNTHETIC profiles via the
    LGWKS_CI_TARGET_PROFILE seam, so its correctness does not depend on the real lgwks.profile.json
    being perpetually incomplete (the real profile is now fully tailored — #311). The positive
    tests assert the real profile's evidence actually evaluates GO."""

    import shutil as _shutil
    _ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

    def _run_ci(self, tier, target_profile, contents):
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(json.dumps(contents))
            path = f.name
        try:
            return subprocess.run(
                ["node", str(self._ROOT / "scripts" / "ci" / "run.mjs"), "--tier", tier],
                cwd=self._ROOT, text=True, capture_output=True, timeout=60,
                env={**os.environ, "LGWKS_CI_TARGET_PROFILE": path},
            )
        finally:
            os.unlink(path)

    @unittest.skipUnless(_shutil.which("node"), "node not available")
    def test_ci_runner_blocks_untailored_tier_with_seal(self):
        # A profile declaring NO tier evidence → nightly cannot return a verdict (unknown ≠ pass).
        proc = self._run_ci("nightly", "empty", {})
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("BLOCKED", proc.stdout)
        seals = list((self._ROOT / ".ci-runs").glob("*-nightly/seal.json"))
        self.assertTrue(seals, "expected a sealed BLOCKED record")
        payload = json.loads(sorted(seals, key=lambda p: p.stat().st_mtime)[-1].read_text())
        self.assertEqual(payload["verdict"], "BLOCKED")
        self.assertEqual(payload["tier"], "nightly")

    @unittest.skipUnless(_shutil.which("node"), "node not available")
    def test_ci_runner_blocks_partially_tailored_tier(self):
        # release requires simulate+sim+soak+latency; a profile with only simulate+sim must
        # instant-BLOCK on the missing soak/latency, naming them — NOT silently run partially.
        proc = self._run_ci("release", "partial", {"simulate": [{"x": 1}], "sim": [{"y": 1}]})
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("BLOCKED", proc.stdout)
        self.assertIn("soak", proc.stdout)  # names the missing block(s) (unknown ≠ pass)
        self.assertIn("latency", proc.stdout)

    @unittest.skipUnless(_shutil.which("node"), "node not available")
    def test_lgwks_verify_verb_delegates_to_tier_authority(self):
        # The verify verb must delegate non-commit tiers to scripts/ci/run.mjs (the single tier
        # authority), surfacing its honest verdict — here BLOCKED, via the synthetic-profile seam.
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(json.dumps({}))
            path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, str(self._ROOT / "lgwks"), "verify",
                 "--profile", "lgwks.profile.json", "--tier", "release"],
                cwd=self._ROOT, text=True, capture_output=True, timeout=60,
                env={**os.environ, "LGWKS_NO_MODELS": "1", "LGWKS_CI_TARGET_PROFILE": path},
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("BLOCKED", proc.stdout + proc.stderr)
        finally:
            os.unlink(path)

    @unittest.skipUnless(_shutil.which("node"), "node not available")
    def test_tier_evidence_is_tailored_and_evaluates_GO(self):
        """#311: the real profile's dynamic evidence is now tailored, so each lane returns a real
        verdict instead of BLOCKED. Tested at the lane level (the full tiers also run the heavy
        commit floor); each lane is gated exactly as scripts/ci/run.mjs wires it —
        simulate→well_crossed, sim→concurrent_safe, latency→latency_bounded, soak→envelope."""
        import subprocess
        profile = json.loads((self._ROOT / "lgwks.profile.json").read_text())
        for block in ("simulate", "sim", "soak", "latency"):
            self.assertTrue(profile.get(block), f"release requires a {block} block")
        keel = self._ROOT / "lgwks_verify" / "keel" / "src"
        lanes = [
            ("run-simulate.mjs", ["--concept", "well_crossed"]),
            ("run-sim.mjs", ["--concept", "concurrent_safe"]),
            ("run-latency.mjs", ["--concept", "latency_bounded"]),
            ("run-soak.mjs", []),  # envelope-relative; no concept
        ]
        for runner, extra in lanes:
            proc = subprocess.run(
                ["node", str(keel / runner), "--profile", "lgwks.profile.json", *extra],
                cwd=self._ROOT, text=True, capture_output=True, timeout=120,
                env={**os.environ, "LGWKS_NO_MODELS": "1"},
            )
            self.assertEqual(proc.returncode, 0, f"{runner}: {proc.stdout}\n{proc.stderr}")
            self.assertIn("GO", proc.stdout)


class TestMaturityScream(unittest.TestCase):
    """Multi-axis assessment must SCREAM: report all 20 Keel axes + the concept
    ladder, and count unmeasured axes as deficiencies (IEC 61508: no credit for
    an axis you didn't measure). Report-only — it does not block."""

    import shutil as _shutil
    _ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

    @unittest.skipUnless(_shutil.which("node"), "node not available")
    def test_maturity_reports_all_axes_and_unmeasured(self):
        import subprocess
        proc = subprocess.run(
            ["node", str(self._ROOT / "scripts" / "ci" / "maturity.mjs")],
            cwd=self._ROOT, text=True, capture_output=True, timeout=180,
            env={**os.environ, "LGWKS_NO_MODELS": "1"},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)  # report-only
        self.assertIn("MATURITY SCREAM", proc.stdout)
        self.assertIn("UNMEASURED", proc.stdout)
        summary = json.loads((self._ROOT / ".keel" / "maturity.json").read_text())
        self.assertEqual(summary["total"], 20)
        # The profile binds only a handful of atoms today, so most are unmeasured.
        self.assertGreater(summary["unmeasured"], 10)
        self.assertEqual(summary["evidenced"] + summary["failed"] + summary["unmeasured"], 20)
        # Ladder is present and ordered least->most stringent.
        self.assertTrue(summary["ladder"])
        self.assertEqual(summary["ladder"][-1]["id"], "Excellent")


if __name__ == "__main__":
    unittest.main()
