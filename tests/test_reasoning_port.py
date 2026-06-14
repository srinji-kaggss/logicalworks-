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


if __name__ == "__main__":
    unittest.main()
