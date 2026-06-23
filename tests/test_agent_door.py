"""Contract tests for the single AGENT front door (lgwks_agent).

Spec: spec/second-harness/SPEC-front-door-factory-v1.md §8 — golden per plan
kind, guards S1–S3, and a capability-coverage proof that every retired door's
concept (do / wf-run / x / route) is still reachable through the one door.

These exercise compile_plan / _effect_class / act directly (no network, no
model) with synthetic WorldViews so they are deterministic and fast.
"""
from __future__ import annotations

import unittest

import lgwks_agent as ag


def _wv(pathways=None, selections=None, risk="allow"):
    """Minimal WorldView matching spec §3, enough to drive compile_plan/act."""
    return {
        "attention": {}, "retrieval": [], "last_state": {},
        "insights": {"scores": {}, "selections": selections or [], "flags": []},
        "pathways": pathways or [],
        "risk": {"verdict": risk},
    }


class TestEffectTaxonomyFailClosed(unittest.TestCase):
    def test_known_reads_are_read(self):
        for v in ("doctor", "extract", "review", "solve", "gate aup",
                  "state fabric query", "ops workflow health-check", "graph viz"):
            self.assertEqual(ag._effect_class(v), "read", v)

    def test_network_verbs_and_urls_are_network(self):
        self.assertEqual(ag._effect_class("crawl"), "network")
        self.assertEqual(ag._effect_class("research"), "network")
        self.assertEqual(ag._effect_class("doctor", url="https://x.test"), "network")

    def test_unknown_and_mutating_verbs_fail_closed_to_write(self):
        # the whole point: an unrecognized verb is NEVER auto-runnable
        for v in ("repo merge", "repo sync", "model-hub train", "ops daemon start",
                  "some-brand-new-verb", "ops workflow ship"):
            self.assertEqual(ag._effect_class(v), "write", v)


class TestPlanGoldenPerKind(unittest.TestCase):
    def test_single_read_routes_to_engine_selection(self):
        plan = ag.compile_plan("doctor", _wv(pathways=["doctor"]))
        self.assertEqual(plan["kind"], "single")
        self.assertEqual(plan["intent_class"], "doctor")   # S7: 1:1 with verb
        self.assertEqual(plan["effect_class"], "read")
        self.assertEqual(plan["approval"], "none")
        self.assertEqual([s["verb"] for s in plan["steps"]], ["doctor"])

    def test_workflow_kind_for_workflow_selection(self):
        plan = ag.compile_plan("prove what happened", _wv(pathways=["ops workflow prove"]))
        self.assertEqual(plan["kind"], "workflow")
        self.assertEqual(plan["intent_class"], "ops workflow prove")

    def test_batch_kind_for_brace_expression(self):
        plan = ag.compile_plan("echo {a,b}", _wv())
        self.assertEqual(plan["kind"], "batch")
        self.assertGreaterEqual(len(plan["steps"]), 2)

    def test_no_engine_selection_is_honest_unresolved(self):
        plan = ag.compile_plan("an utterly vague wish", _wv())
        self.assertEqual(plan["intent_class"], "unresolved")
        self.assertEqual(plan["steps"], [])


class TestSecurityGuards(unittest.TestCase):
    def setUp(self):
        self._orig = ag.worldview

    def tearDown(self):
        ag.worldview = self._orig

    def _stub_wv(self, **kw):
        ag.worldview = lambda intent, repo, top: _wv(**kw)

    def test_s1_write_blocked_without_approval(self):
        self._stub_wv(pathways=["repo merge"])
        out = ag.act("merge pr 5", execute=True)            # no --yes
        self.assertTrue(out["blocked"])
        self.assertFalse(out["executed"])
        self.assertIn("approval", out["block_reason"])

    def test_s3_risk_block_returns_plan_only(self):
        self._stub_wv(pathways=["doctor"], risk="block")
        out = ag.act("doctor", execute=True)
        self.assertTrue(out["blocked"])
        self.assertFalse(out["executed"])
        self.assertEqual(out["block_reason"], "risk gate blocked the intent")

    def test_dry_run_never_executes(self):
        self._stub_wv(pathways=["doctor"])
        out = ag.act("doctor", execute=False)               # perceive only
        self.assertFalse(out["executed"])
        self.assertIsNotNone(out["plan"])


class TestCapabilityCoverageRetiredDoors(unittest.TestCase):
    """Spec §8: every deleted door's concept stays reachable via the one door."""

    def test_x_concept_reachable_as_batch(self):
        self.assertEqual(ag.compile_plan("run {x,y}", _wv())["kind"], "batch")

    def test_wf_run_concept_reachable_as_workflow(self):
        self.assertEqual(
            ag.compile_plan("audit", _wv(pathways=["ops workflow audit-trail"]))["kind"],
            "workflow")

    def test_do_concept_reachable_as_review(self):
        plan = ag.compile_plan("review the diff", _wv(pathways=["review"]))
        self.assertIn("review", [s["verb"] for s in plan["steps"]])

    def test_route_concept_reachable_as_worldview(self):
        # `route map/engine` folded into the door: act() always carries a worldview
        orig = ag.worldview
        ag.worldview = lambda intent, repo, top: _wv(pathways=["doctor"])
        try:
            out = ag.act("doctor", execute=False)
            self.assertIn("worldview", out)
            self.assertIn("insights", out["worldview"])
        finally:
            ag.worldview = orig


if __name__ == "__main__":
    unittest.main()
