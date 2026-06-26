"""Tests for lgwks_reasoning_port — the runtime-neutral deep-reasoning seam.

P1  no model present → agent_handoff (the new "rented brain" = the agent)
P2  LGWKS_NO_MODELS → agent_handoff (kill-switch)
P3  LGWKS_REASONING_BACKEND=agent forces agent_handoff
P4  persona=co_scientist → co-scientist framing carried in the handoff request
P5  agent target respected (param + LGWKS_AGENT)
P6  no model AND no agent → deferred to human (NEVER fabricates text)
P7  never returns mode=local / fabricated text when no weights present
P8  handoff envelope is well-formed + deterministic
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_reasoning_port as rp


class TestReasoningPort(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("LGWKS_NO_MODELS", "LGWKS_REASONING_BACKEND", "LGWKS_AGENT")}
        # hermetic default: kill-switch on → never touch weights
        os.environ["LGWKS_NO_MODELS"] = "1"
        os.environ.pop("LGWKS_REASONING_BACKEND", None)
        os.environ.pop("LGWKS_AGENT", None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_p1_no_model_hands_off(self):
        r = rp.reason("plan a migration")
        self.assertEqual(r["mode"], "agent_handoff")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["model"])

    def test_p2_kill_switch(self):
        self.assertEqual(rp.resolve_backend(), "agent_handoff")

    def test_p3_forced_agent(self):
        os.environ.pop("LGWKS_NO_MODELS", None)
        os.environ["LGWKS_REASONING_BACKEND"] = "agent"
        self.assertEqual(rp.resolve_backend(), "agent_handoff")

    def test_p4_co_scientist_framing(self):
        r = rp.reason("is X a good idea?", persona="co_scientist")
        framing = r["handoff"]["request"]["framing"]
        self.assertIn("co-scientist", framing.lower())
        self.assertEqual(r["persona"], "co_scientist")

    def test_p5_agent_target(self):
        r = rp.reason("debug this", agent="codex")
        self.assertEqual(r["handoff"]["to"], "codex")
        os.environ["LGWKS_AGENT"] = "gemini"
        self.assertEqual(rp.reason("x")["handoff"]["to"], "gemini")

    def test_p6_no_agent_defers_to_human(self):
        r = rp.reason("hard question", agent="none")
        self.assertEqual(r["mode"], "deferred")
        self.assertFalse(r["ok"])
        self.assertEqual(r["deferred"]["to"], "human")
        self.assertNotIn("text", r)  # never fabricated

    def test_p7_no_fabrication_without_weights(self):
        for persona in ("default", "co_scientist"):
            r = rp.reason("anything", persona=persona)
            self.assertNotEqual(r["mode"], "local")
            self.assertNotIn("text", r)

    def test_p8_handoff_deterministic_and_wellformed(self):
        a = rp.reason("same prompt", persona="co_scientist", agent="claude")
        b = rp.reason("same prompt", persona="co_scientist", agent="claude")
        self.assertEqual(a, b)
        self.assertEqual(a["schema"], "lgwks.reasoning.result.v0")
        self.assertEqual(a["handoff"]["request"]["prompt"], "same prompt")
        self.assertEqual(a["handoff"]["reason"], "deep_reasoning_exceeds_local_tier")


class TestCloudReasoningTier(unittest.TestCase):
    """The OPT-IN cloud plane: model SELECTED via models.dev, EXECUTED via the
    OpenRouter Tongue — never a direct provider/api.anthropic.com call (#333 rebuild)."""

    _ENVKEYS = ("LGWKS_NO_MODELS", "LGWKS_REASONING_BACKEND", "LGWKS_MODEL_LOCALITY")

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self._ENVKEYS}
        for k in self._ENVKEYS:
            os.environ.pop(k, None)  # kill-switch OFF, backend auto

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_cloud_is_opt_in_never_chosen_on_local_plane(self):
        # Default LOCAL plane: even with the cloud seam fully configured, cloud is
        # never silently chosen.
        import lgwks_model_port as mp
        import lgwks_openrouter as orr
        with mock.patch.object(mp, "active_locality", return_value=mp.LOCAL), \
             mock.patch.object(mp, "resolve_model",
                               return_value={"role": "proposal", "runtime_id": "anthropic/claude-x"}), \
             mock.patch.object(orr, "is_configured", return_value=True):
            self.assertNotEqual(rp.resolve_backend(), "cloud_tongue")

    def test_cloud_opted_in_but_unconfigured_hands_off(self):
        # locality=cloud but no models.dev model resolves → defer to agent_handoff,
        # never fall back to a local model.
        os.environ["LGWKS_MODEL_LOCALITY"] = "cloud"
        import lgwks_model_port as mp
        with mock.patch.object(mp, "resolve_model", return_value=None):
            self.assertFalse(rp._cloud_available())
            self.assertEqual(rp.resolve_backend(), "agent_handoff")

    def test_cloud_routes_through_models_dev_and_openrouter(self):
        os.environ["LGWKS_MODEL_LOCALITY"] = "cloud"
        import lgwks_model_port as mp
        import lgwks_openrouter as orr
        card = {"role": "proposal", "locality": "cloud",
                "runtime_id": "anthropic/claude-sonnet-4-6", "card": {"id": "x"}}
        with mock.patch.object(mp, "resolve_model", return_value=card), \
             mock.patch.object(orr, "is_configured", return_value=True), \
             mock.patch.object(orr, "generate_json",
                               return_value={"reasoning": "cloud proposal text"}) as gj:
            self.assertEqual(rp.resolve_backend(), "cloud_tongue")
            r = rp.reason("plan a migration")
            self.assertEqual(r["mode"], "cloud")
            self.assertEqual(r["model"], "anthropic/claude-sonnet-4-6")
            self.assertEqual(r["text"], "cloud proposal text")
            # Canonical seam: the models.dev-selected ref was executed through the
            # OpenRouter Tongue — the model id passed to generate_json is the card's.
            self.assertEqual(gj.call_args.kwargs.get("model"), "anthropic/claude-sonnet-4-6")

    def test_cloud_failure_falls_back_to_handoff_no_fabrication(self):
        os.environ["LGWKS_MODEL_LOCALITY"] = "cloud"
        import lgwks_model_port as mp
        import lgwks_openrouter as orr
        card = {"role": "proposal", "runtime_id": "anthropic/claude-sonnet-4-6"}
        with mock.patch.object(mp, "resolve_model", return_value=card), \
             mock.patch.object(orr, "is_configured", return_value=True), \
             mock.patch.object(orr, "generate_json", return_value=None):  # throttled / fail-closed
            r = rp.reason("hard question")
            self.assertEqual(r["mode"], "agent_handoff")
            self.assertNotIn("text", r)  # never fabricates on cloud failure


if __name__ == "__main__":
    unittest.main()
