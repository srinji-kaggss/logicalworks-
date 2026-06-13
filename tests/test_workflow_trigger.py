"""Tests for lgwks.workflow.trigger.v1 (#121 — event-chain grammar).

Maps to the issue's acceptance bullets:
  1. the contract expresses ≥2 cross-event workflow examples and matches them;
  2. trigger evaluation is replayable from stored events (deterministic);
  3. triggers PROPOSE actions but never execute directly.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import lgwks_capability_action as ca
import lgwks_daemon_event as de
import lgwks_workflow_trigger as wt

TENANT = "repo:demo"


def _event(kind, source, trust, ts, payload=None):
    return de.build_event(
        tenant_id=TENANT, agent_id="claude", session_id="sess-1",
        actor="agent", client="claude", lane="telemetry",
        kind=kind, scope="agent_local", payload=payload or {},
        source=source, trust=trust, ts=ts,
    )


# Example 1 — repo+test chain: a diff followed by a failed test → propose a review.
TRIGGER_REVIEW = {
    "schema": "lgwks.workflow.trigger.v1",
    "trigger_id": "repo-test-fail-review",
    "pattern": [
        {"source": "repo", "kind": "repo_diff"},
        {"source": "terminal", "kind": "terminal_output", "payload_truthy": "test_failed"},
    ],
    "required_evidence": [
        {"type": "same_field", "field": "session_id"},
        {"type": "within_ms", "ms": 3_600_000},
    ],
    "confidence": {"score": 1.0, "basis": "rule"},
    "cooldown": {"max_fires": 1},
    "policy": "ask",
    "lowers_to": {"verb": "review", "effect_class": "read", "reversibility": "reversible"},
}

# Example 2 — research+code chain: a browser action then a code change → ingest+link.
TRIGGER_INGEST = {
    "schema": "lgwks.workflow.trigger.v1",
    "trigger_id": "research-then-code-ingest",
    "pattern": [
        {"source": "browser", "kind": "browser_action"},
        {"source": "repo", "kind": "file_change"},
    ],
    "required_evidence": [{"type": "same_field", "field": "session_id"}],
    "confidence": {"score": 0.8, "basis": "rule"},
    "policy": "act",
    "lowers_to": {"verb": "codebase index", "effect_class": "write", "reversibility": "reversible"},
}


class TestTwoChains(unittest.TestCase):
    """Acceptance 1: express + match two distinct cross-event chains."""

    def test_repo_test_fail_chain(self):
        events = [
            _event("repo_diff", "repo", "deterministic", "2026-06-13T10:00:00+00:00"),
            _event("terminal_output", "terminal", "deterministic", "2026-06-13T10:05:00+00:00",
                   {"test_failed": True}),
        ]
        props = wt.evaluate_triggers(events, [TRIGGER_REVIEW])
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["action"]["verb"], "review")
        self.assertEqual(props[0]["policy"], "ask")

    def test_research_code_chain(self):
        events = [
            _event("browser_action", "browser", "model_proposed", "2026-06-13T09:00:00+00:00"),
            _event("file_change", "repo", "deterministic", "2026-06-13T09:10:00+00:00"),
        ]
        props = wt.evaluate_triggers(events, [TRIGGER_INGEST])
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["action"]["verb"], "codebase index")
        # weakest trust across the chain rides onto the proposal (model_proposed < deterministic)
        self.assertEqual(props[0]["action"]["provenance"]["trust"], "model_proposed")

    def test_no_match_when_evidence_missing(self):
        # diff + terminal_output but test did NOT fail → required_evidence fails.
        events = [
            _event("repo_diff", "repo", "deterministic", "2026-06-13T10:00:00+00:00"),
            _event("terminal_output", "terminal", "deterministic", "2026-06-13T10:05:00+00:00",
                   {"test_failed": False}),
        ]
        self.assertEqual(wt.evaluate_triggers(events, [TRIGGER_REVIEW]), [])

    def test_no_match_out_of_window(self):
        events = [
            _event("repo_diff", "repo", "deterministic", "2026-06-13T10:00:00+00:00"),
            _event("terminal_output", "terminal", "deterministic", "2026-06-13T23:00:00+00:00",
                   {"test_failed": True}),  # 13h later — outside the 1h window
        ]
        self.assertEqual(wt.evaluate_triggers(events, [TRIGGER_REVIEW]), [])


class TestReplayDeterminism(unittest.TestCase):
    """Acceptance 2: evaluation over the same slice yields identical proposals."""

    def test_identical_proposals(self):
        events = [
            _event("browser_action", "browser", "model_proposed", "2026-06-13T09:00:00+00:00"),
            _event("file_change", "repo", "deterministic", "2026-06-13T09:10:00+00:00"),
        ]
        a = wt.evaluate_triggers(events, [TRIGGER_INGEST])
        b = wt.evaluate_triggers(events, [TRIGGER_INGEST])
        self.assertEqual(a, b)
        self.assertEqual(a[0]["action"]["replay"]["idempotency_key"],
                         b[0]["action"]["replay"]["idempotency_key"])


class TestNonExecution(unittest.TestCase):
    """Acceptance 3: triggers PROPOSE, never execute."""

    def test_proposals_are_unconfirmed(self):
        events = [
            _event("browser_action", "browser", "deterministic", "2026-06-13T09:00:00+00:00"),
            _event("file_change", "repo", "deterministic", "2026-06-13T09:10:00+00:00"),
        ]
        props = wt.evaluate_triggers(events, [TRIGGER_INGEST])
        # a proposal is never auto-confirmed — it must pass the #120 gate later.
        self.assertNotIn("confirmed", props[0]["action"])

    def test_evaluation_never_calls_the_hand(self):
        events = [
            _event("repo_diff", "repo", "deterministic", "2026-06-13T10:00:00+00:00"),
            _event("terminal_output", "terminal", "deterministic", "2026-06-13T10:05:00+00:00",
                   {"test_failed": True}),
        ]
        with patch.object(ca, "execute_action", side_effect=AssertionError("the Hand must not run")):
            props = wt.evaluate_triggers(events, [TRIGGER_REVIEW])
        self.assertEqual(len(props), 1)  # produced a proposal, executed nothing


if __name__ == "__main__":
    unittest.main()
