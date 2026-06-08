"""
Tests for U9: lgwks_synthesizer.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lgwks_synthesizer as synthesizer


class TestSynthesizer(unittest.TestCase):

    def setUp(self):
        # Clean environment controls
        self.old_mock = os.environ.get("LGWKS_TEST_SYNTH_MOCK")
        self.old_type = os.environ.get("LGWKS_TEST_SYNTH_MOCK_TYPE")
        self.old_no_models = os.environ.get("LGWKS_NO_MODELS")
        os.environ["LGWKS_TEST_SYNTH_MOCK"] = "1"
        if "LGWKS_NO_MODELS" in os.environ:
            del os.environ["LGWKS_NO_MODELS"]

    def tearDown(self):
        if self.old_mock is not None:
            os.environ["LGWKS_TEST_SYNTH_MOCK"] = self.old_mock
        elif "LGWKS_TEST_SYNTH_MOCK" in os.environ:
            del os.environ["LGWKS_TEST_SYNTH_MOCK"]
        if self.old_type is not None:
            os.environ["LGWKS_TEST_SYNTH_MOCK_TYPE"] = self.old_type
        elif "LGWKS_TEST_SYNTH_MOCK_TYPE" in os.environ:
            del os.environ["LGWKS_TEST_SYNTH_MOCK_TYPE"]
        if self.old_no_models is not None:
            os.environ["LGWKS_NO_MODELS"] = self.old_no_models
        elif "LGWKS_NO_MODELS" in os.environ:
            del os.environ["LGWKS_NO_MODELS"]

    def test_strength_gate_failed_skips_synthesis(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            input_data = {
                "schema": "lgwks.synth.input.v1",
                "package_id": "pkg:1",
                "repo": str(tmp),
                "l_budget": 0.15,
            }
            # Failing strength gate (pass: False)
            strength_gate = {"pass": False, "checks": {"actionability": False}}
            
            res = synthesizer.run_synthesis(input_data, strength_gate=strength_gate)
            
            self.assertEqual(res["synth_status"], "skipped")
            self.assertEqual(res["reason"], "artifact_strength_gate_failed")

    def test_synthesis_success_and_metering(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            input_data = {
                "schema": "lgwks.synth.input.v1",
                "package_id": "pkg:123",
                "repo": str(tmp),
                "l_budget": 0.15,
            }
            # Passing strength gate
            strength_gate = {"pass": True, "checks": {}}
            
            os.environ["LGWKS_TEST_SYNTH_MOCK_TYPE"] = "success"
            res = synthesizer.run_synthesis(input_data, strength_gate=strength_gate)
            
            self.assertEqual(res["schema"], "lgwks.synth.output.v1")
            self.assertFalse(res["l_exceeded"])
            self.assertEqual(res["l_score"], 0.0)
            self.assertTrue(len(res["claims"]) > 0)
            
            for c in res["claims"]:
                self.assertIn("origin_type", c)
                self.assertIn("basis", c)
                
            # Verify metering file was written
            meter_file = tmp / "store" / "synth-meter.jsonl"
            self.assertTrue(meter_file.exists())
            lines = meter_file.read_text().splitlines()
            self.assertTrue(lines)
            last_record = json.loads(lines[-1])
            self.assertEqual(last_record["schema"], "lgwks.synth.meter.v1")
            self.assertEqual(last_record["package_id"], "pkg:123")
            self.assertEqual(last_record["status"], "success")

    def test_l_budget_exceeded(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            input_data = {
                "schema": "lgwks.synth.input.v1",
                "package_id": "pkg:456",
                "repo": str(tmp),
                "l_budget": 0.15,
            }
            # Passing strength gate
            strength_gate = {"pass": True, "checks": {}}
            
            os.environ["LGWKS_TEST_SYNTH_MOCK_TYPE"] = "exceed_budget"
            res = synthesizer.run_synthesis(input_data, strength_gate=strength_gate)
            
            self.assertTrue(res["l_exceeded"])
            self.assertEqual(res["l_score"], 0.6667)
            self.assertEqual(res["claims"], [])
            
            # Verify metering file recorded exceed_budget
            meter_file = tmp / "store" / "synth-meter.jsonl"
            last_record = json.loads(meter_file.read_text().splitlines()[-1])
            self.assertEqual(last_record["status"], "exceeded_budget")

    def test_provider_unavailable(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            input_data = {
                "schema": "lgwks.synth.input.v1",
                "package_id": "pkg:789",
                "repo": str(tmp),
                "l_budget": 0.15,
            }
            # Passing strength gate
            strength_gate = {"pass": True, "checks": {}}
            
            # Disable mock and force no models env
            os.environ["LGWKS_NO_MODELS"] = "1"
            del os.environ["LGWKS_TEST_SYNTH_MOCK"]
            
            res = synthesizer.run_synthesis(input_data, strength_gate=strength_gate)
            
            self.assertEqual(res["synth_status"], "unavailable")
            self.assertEqual(res["reason"], "no_provider_reachable")
            
            # Verify metering file recorded failed_no_provider
            meter_file = tmp / "store" / "synth-meter.jsonl"
            last_record = json.loads(meter_file.read_text().splitlines()[-1])
            self.assertEqual(last_record["status"], "failed_no_provider")


if __name__ == "__main__":
    unittest.main()
