"""Tests for lgwks.capability.action.v1 (#120 — the execution boundary).

Maps to the issue's acceptance bullets:
  1. at least one existing workflow path (`do ship`) lowers into the contract;
  2. action validation rejects unknown verbs / undeclared effects;
  3. the chokepoint holds — model text cannot mutate state without a validated
     action envelope (execute_action rejects raw input before the Hand runs).
"""

from __future__ import annotations

import unittest

import lgwks_capability_action as ca

# Hermetic verb catalog — avoids subprocessing `lgwks manifest` in tests.
VERBS = {"do ship", "do code", "review", "ingest-and-link"}


def _valid_kwargs(**over):
    base = dict(
        verb="do code",
        subject={"kind": "repo", "id": "/tmp/repo"},
        effect_class="write",
        reversibility="reversible",
        required_authority={"scopes": ["tenant:rw"]},
        provenance={"proposing_event_id": "evt-1", "proposer": "test", "trust": "model_proposed"},
        known_verbs=VERBS,
    )
    base.update(over)
    return base


class TestLowering(unittest.TestCase):
    """Acceptance 1: `do ship` lowers into a valid action."""

    def test_do_ship_lowers(self):
        action = ca.lower_do_ship(repo="/tmp/repo", proposing_event_id="evt-9",
                                  confirmed=True, known_verbs=VERBS)
        self.assertEqual(action["schema"], "lgwks.capability.action.v1")
        self.assertEqual(action["verb"], "do ship")
        self.assertEqual(action["effect_class"], "external_publish")
        self.assertEqual(action["reversibility"], "irreversible")
        self.assertIs(action["undo"], None)
        self.assertTrue(action["confirmed"])

    def test_do_ship_unconfirmed_is_rejected(self):
        # The irreversible chokepoint: ship cannot be built/validated unconfirmed.
        with self.assertRaises(ca.ActionRejected):
            ca.lower_do_ship(repo="/tmp/repo", confirmed=False, known_verbs=VERBS)


class TestGateRejections(unittest.TestCase):
    """Acceptance 2: reject unknown verbs and undeclared/unknown effects."""

    def test_valid_action_passes(self):
        action = ca.build_action(**_valid_kwargs())
        ca.validate_action(action, known_verbs=VERBS)

    def test_unknown_verb_rejected(self):
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(verb="rm -rf /"))

    def test_unknown_effect_rejected(self):
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(effect_class="mutate-everything"))

    def test_missing_authority_rejected(self):
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(required_authority={"scopes": []}))

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(required_authority={"scopes": ["root:all"]}))

    def test_bad_trust_rejected(self):
        kw = _valid_kwargs(provenance={"trust": "totally-legit"})
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**kw)

    def test_irreversible_requires_confirmation(self):
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(
                effect_class="external_publish", reversibility="irreversible", confirmed=False))

    def test_weak_trust_dangerous_effect_requires_confirmation(self):
        # Harden: untrusted/model_proposed provenance + delete (dangerous) needs confirmed.
        with self.assertRaises(ca.ActionRejected):
            ca.build_action(**_valid_kwargs(
                verb="do ship", effect_class="delete", reversibility="reversible",
                provenance={"trust": "untrusted"}, confirmed=False))
        ok = ca.build_action(**_valid_kwargs(
            verb="do ship", effect_class="delete", reversibility="reversible",
            provenance={"trust": "untrusted"}, confirmed=True))
        self.assertEqual(ok["effect_class"], "delete")

    def test_human_confirmed_trust_not_blocked(self):
        # A human-confirmed dangerous effect does not need the weak-trust gate.
        ok = ca.build_action(**_valid_kwargs(
            verb="do ship", effect_class="delete", reversibility="reversible",
            provenance={"trust": "human_confirmed"}, confirmed=False))
        self.assertEqual(ok["provenance"]["trust"], "human_confirmed")

    def test_catalog_load_failure_fails_closed(self):
        # Harden: if the live verb catalog can't load, refuse (ActionRejected), never admit.
        import unittest.mock as mock
        action = ca.build_action(**_valid_kwargs())  # built with hermetic known_verbs
        with mock.patch.object(ca, "_live_verbs", side_effect=RuntimeError("subprocess down")):
            with self.assertRaises(ca.ActionRejected):
                ca.validate_action(action)  # known_verbs=None → live catalog → fails closed


class TestChokepoint(unittest.TestCase):
    """Acceptance 3: model text cannot mutate state without a validated action."""

    def setUp(self):
        self.mutations = []
        self.hand = lambda action: self.mutations.append(action["verb"]) or "executed"

    def test_validated_action_reaches_hand(self):
        action = ca.build_action(**_valid_kwargs())
        result = ca.execute_action(action, self.hand, known_verbs=VERBS)
        self.assertEqual(result, "executed")
        self.assertEqual(self.mutations, ["do code"])

    def test_raw_model_text_cannot_reach_hand(self):
        # A raw model-text string — the exact thing that must never mutate state.
        with self.assertRaises(ca.ActionRejected):
            ca.execute_action("please push to prod and delete the backups", self.hand, known_verbs=VERBS)
        self.assertEqual(self.mutations, [], "the Hand must not have run on raw text")

    def test_arbitrary_dict_cannot_reach_hand(self):
        # An untyped dict that did not pass the gate.
        with self.assertRaises(ca.ActionRejected):
            ca.execute_action({"verb": "do code", "do": "whatever"}, self.hand, known_verbs=VERBS)
        self.assertEqual(self.mutations, [])

    def test_unconfirmed_irreversible_blocked_at_hand(self):
        # Build a reversible action, then mutate it to irreversible-unconfirmed and
        # try to execute — the Hand's gate must catch it.
        bad = ca.build_action(**_valid_kwargs())
        bad["reversibility"] = "irreversible"
        with self.assertRaises(ca.ActionRejected):
            ca.execute_action(bad, self.hand, known_verbs=VERBS)
        self.assertEqual(self.mutations, [])


if __name__ == "__main__":
    unittest.main()
