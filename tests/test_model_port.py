"""Tests for lgwks_model_port — the unified escalating cognition harness.

The contract this locks (Director's law):
  M1  the ladder prefers DETERMINISM — a deterministic rung that resolves wins
      and no model is ever touched (model is the last resort, not the default)
  M2  LGWKS_NO_MODELS suppresses the weight tiers (sensor/generative); the
      deterministic tier still runs
  M3  fail-closed — when nothing resolves the envelope is mode=deferred with
      value=None: the harness NEVER fabricates (INV-3)
  M4  LAW IS TRUTH — the model id in an envelope comes from MESH_LAW, not a literal
  M5  a below-threshold resolve is held as a degraded best-effort, not lost
  M6  every call returns the one uniform lgwks.model.port.v1 envelope shape
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_model_mesh as mesh
import lgwks_model_port as mp


class TestEscalation(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("LGWKS_NO_MODELS")
        os.environ.pop("LGWKS_NO_MODELS", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LGWKS_NO_MODELS", None)
        else:
            os.environ["LGWKS_NO_MODELS"] = self._saved

    def test_m1_deterministic_wins_without_touching_model(self):
        touched = {"sensor": False, "generative": False}

        def det():
            return {"v": 1}

        def sensor():
            touched["sensor"] = True
            return {"v": 2}

        env = mp.escalate("classify", [
            mp.Attempt("sensor", sensor, model="should-not-run"),
            mp.Attempt("deterministic", det),
        ])
        self.assertEqual(env["mode"], "deterministic")
        self.assertEqual(env["value"], {"v": 1})
        self.assertFalse(touched["sensor"], "model tier ran even though deterministic resolved")

    def test_m2_kill_switch_suppresses_weight_tiers(self):
        os.environ["LGWKS_NO_MODELS"] = "1"
        ran = {"sensor": False}

        def sensor():
            ran["sensor"] = True
            return {"ok": 1}

        env = mp.escalate("classify", [mp.Attempt("sensor", sensor)])
        self.assertFalse(ran["sensor"], "sensor ran under the kill-switch")
        self.assertEqual(env["mode"], "deferred")
        outcomes = [t["outcome"] for t in env["escalation"]]
        self.assertIn("suppressed", outcomes)

    def test_m3_fail_closed_never_fabricates(self):
        env = mp.escalate("extract", [
            mp.Attempt("deterministic", lambda: None),
            mp.Attempt("generative", lambda: None, model="x"),
        ])
        self.assertFalse(env["ok"])
        self.assertEqual(env["mode"], "deferred")
        self.assertIsNone(env["value"])

    def test_m5_below_threshold_held_as_degraded(self):
        env = mp.escalate("classify", [
            mp.Attempt("sensor", lambda: {"schema": "X"},
                       confidence=lambda r: 0.3, model="m"),
        ], threshold=0.6)
        self.assertEqual(env["mode"], "degraded")
        self.assertEqual(env["value"], {"schema": "X"})
        self.assertAlmostEqual(env["confidence"], 0.3)

    def test_m6_envelope_shape(self):
        env = mp.escalate("extract", [mp.Attempt("deterministic", lambda: [1])])
        for key in ("schema", "role", "ok", "mode", "tier", "model", "trust",
                    "value", "confidence", "escalation", "why"):
            self.assertIn(key, env)
        self.assertEqual(env["schema"], "lgwks.model.port.v1")

    def test_error_in_rung_escalates_not_crashes(self):
        def boom():
            raise RuntimeError("backend down")

        env = mp.escalate("extract", [
            mp.Attempt("sensor", boom, model="m"),
            mp.Attempt("generative", lambda: ["recovered"], model="g"),
        ])
        self.assertEqual(env["value"], ["recovered"])
        outcomes = {t["outcome"] for t in env["escalation"]}
        self.assertIn("error", outcomes)


class TestRoleHelpers(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("LGWKS_NO_MODELS")
        os.environ["LGWKS_NO_MODELS"] = "1"  # hermetic: never touch weights

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LGWKS_NO_MODELS", None)
        else:
            os.environ["LGWKS_NO_MODELS"] = self._saved

    def test_extract_resolves_deterministically(self):
        env = mp.extract_entities("reach me at a@b.com on 2026-06-15")
        self.assertEqual(env["mode"], "deterministic")
        types = {m["type"] for m in env["value"]}
        self.assertIn("EMAIL", types)
        self.assertIn("DATE", types)

    def test_extract_empty_defers(self):
        env = mp.extract_entities("   ")
        self.assertEqual(env["mode"], "deferred")
        self.assertIsNone(env["value"])

    def test_classify_defers_without_model(self):
        env = mp.classify("some page text")
        self.assertEqual(env["mode"], "deferred")  # sensor suppressed by kill-switch

    def test_embed_degrades_to_audit_vector(self):
        env = mp.embed("hello")
        self.assertTrue(env["ok"])
        self.assertEqual(env["mode"], "degraded")
        self.assertIsNotNone(env["value"]["det"])
        self.assertIsNone(env["value"]["sem"], "no model → no semantic vector")

    def test_m4_reason_pins_model_id_from_law(self):
        env = mp.reason("is this safe?")
        expected = mesh.model_name_for_role("proposal", trust_class="generative")
        self.assertEqual(env["model"], expected)
        self.assertTrue(env["model"], "law must supply a proposal model id")


if __name__ == "__main__":
    unittest.main()
