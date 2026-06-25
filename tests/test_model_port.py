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


class TestLocalitySelector(unittest.TestCase):
    """S2 (#337): model_port is the ONE selector across the locality axis.

    LOCAL Mesh is the private default; CLOUD models.dev is strictly opt-in and
    must be configured; AETHERIUS is a reserved (deferred) slot. The model id is
    resolved from the law (local) or the models.dev card (cloud), never a literal.
    """

    def setUp(self):
        self._saved_loc = os.environ.get("LGWKS_MODEL_LOCALITY")
        os.environ.pop("LGWKS_MODEL_LOCALITY", None)

    def tearDown(self):
        if self._saved_loc is None:
            os.environ.pop("LGWKS_MODEL_LOCALITY", None)
        else:
            os.environ["LGWKS_MODEL_LOCALITY"] = self._saved_loc
        os.environ.pop("LGWKS_CLOUD_EMBED_MODEL", None)

    def test_default_locality_is_local_private(self):
        # privacy-first: with nothing set, the plane is LOCAL (no network)
        self.assertEqual(mp.active_locality(), mp.LOCAL)

    def test_unknown_locality_falls_back_to_local(self):
        os.environ["LGWKS_MODEL_LOCALITY"] = "mars"
        self.assertEqual(mp.active_locality(), mp.LOCAL, "must fail-safe to private, never cloud")

    def test_local_resolves_embed_id_from_law_not_literal(self):
        sel = mp.resolve_model("embed", locality=mp.LOCAL)
        self.assertIsNotNone(sel)
        self.assertEqual(sel["locality"], mp.LOCAL)
        law_name = mesh.model_name_for_role("embed", trust_class="sensor")
        self.assertEqual(sel["law_name"], law_name, "id must come from MESH_LAW")
        # hub catalog key is the law name minus its org — reconstructable by hand
        self.assertEqual(sel["runtime_id"], law_name.split("/")[-1])

    def test_cloud_is_opt_in_unconfigured_defers(self):
        # CLOUD selected but no ref configured → None (never silently local)
        self.assertIsNone(mp.resolve_model("embed", locality=mp.CLOUD))

    def test_cloud_resolves_via_models_dev_card(self):
        import lgwks_models_dev as md
        os.environ["LGWKS_CLOUD_EMBED_MODEL"] = "acme/embed-1"
        fake = {"ref": "acme/embed-1", "locality": "cloud", "context": 8192}
        orig = md.resolve
        md.resolve = lambda ref: fake if ref == "acme/embed-1" else None
        try:
            sel = mp.resolve_model("embed", locality=mp.CLOUD)
        finally:
            md.resolve = orig
        self.assertIsNotNone(sel)
        self.assertEqual(sel["locality"], mp.CLOUD)
        self.assertEqual(sel["runtime_id"], "acme/embed-1")
        self.assertEqual(sel["card"], fake)

    def test_aetherius_slot_is_reserved_defers(self):
        self.assertIsNone(mp.resolve_model("embed", locality=mp.AETHERIUS))


class TestRunEmbedRoutesThroughPort(unittest.TestCase):
    """S2: lgwks_run.embed resolves its model id via the port/law, not a literal.

    Behavioural no-literal proof: capture the id handed to hub.mlx_embed and assert
    it equals the law-resolved hub key — so a future law rename moves the runtime
    with it, and there is no second copy of the id to drift.
    """

    def test_embed_uses_port_resolved_id(self):
        import lgwks_model_hub as hub
        import lgwks_run
        captured: dict[str, object] = {}
        orig = hub.mlx_embed

        def _fake(text, model_name="ModernBERT-base-mlx-4bit"):  # noqa: ANN001
            captured["model_name"] = model_name
            return {"ok": True, "vector": [0.1] * 8, "is_semantic": True}

        hub.mlx_embed = _fake
        try:
            vec, label, is_sem = lgwks_run.embed("hi", embed_on=True, provider="auto")
        finally:
            hub.mlx_embed = orig
        law_name = mesh.model_name_for_role("embed", trust_class="sensor")
        self.assertEqual(captured["model_name"], law_name.split("/")[-1],
                         "embed must use the law-resolved id, not a literal")
        self.assertTrue(is_sem)


if __name__ == "__main__":
    unittest.main()
