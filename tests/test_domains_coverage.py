"""DOMAINS coverage gate (R7.2) — the hand-maintained verb→domain taxonomy must not drift from the live CLI dispatcher.

This test enforces two invariants:
  1. No stale DOMAINS entry: every verb listed in DOMAINS must resolve to a real registered dispatcher verb
     (i.e. present in the parser's `.choices.keys()`, which includes aliases).
  2. Every live verb classified exactly once: every verb in command_names() (non-alias verbs) must be
     classified into exactly ONE domain — domain_for(verb) must NOT return "Other", AND the verb must
     appear in exactly one domain's list (never two).

Failures are fixed by:
  - Invariant 1 failure: REMOVE stale entries from lgwks_cli_introspect.py::DOMAINS.
  - Invariant 2 failure: ADD the unclassified verb to the correct domain in DOMAINS (use judgment from
    verb name + existing domain groupings). Only use OTHER_ALLOWED if the verb genuinely belongs in no
    domain (rare; document reason).

The gate is tight — it prevents silent drift where DOMAINS becomes out-of-sync with the real CLI.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_cli_introspect as ci

# ── allow-list for unclassified verbs (rare; each entry documented) ─────────────────

# Verbs that genuinely belong in no domain and are intentionally unclassified.
# Format: verb → reason. This list should be empty in normal operation.
OTHER_ALLOWED: dict[str, str] = {
    # Example: "fetch": "legacy compat alias, no domain needed",
}


class TestDomainsCoverage(unittest.TestCase):
    """DOMAINS taxonomy must stay in sync with the live CLI dispatcher."""

    def _scan(self) -> tuple[list[str], list[str]]:
        """Return (stale_domains_entries, unclassified_live_verbs)."""
        stale_entries: list[str] = []
        unclassified: list[str] = []

        # Load the live parser and extract all verbs (including aliases).
        try:
            parser = ci.load_parser()
            sub_action = ci.command_action(parser)
            if sub_action is None or not getattr(sub_action, "choices", None):
                # Parser broken; this test can't run. Report as failure rather than skip.
                raise RuntimeError("Cannot introspect live parser: no subparsers found")
            all_live_verbs = set(sub_action.choices.keys())
        except Exception as e:
            raise RuntimeError(f"Cannot load live parser for introspection: {e}") from e

        # Invariant 1: Check DOMAINS entries against live verbs.
        for domain, verbs_in_domain in ci.DOMAINS.items():
            for verb in verbs_in_domain:
                if verb not in all_live_verbs:
                    stale_entries.append(
                        f"{domain}: '{verb}' is not a registered verb "
                        f"(remove from DOMAINS)"
                    )

        # Invariant 2: Check that every live (non-alias) verb is classified exactly once.
        live_names = ci.command_names()
        domain_counts: dict[str, int] = {}

        for verb in live_names:
            domain = ci.domain_for(verb)
            if domain == "Other" and verb not in OTHER_ALLOWED:
                unclassified.append(
                    f"'{verb}' is unclassified (domain_for() → 'Other') — "
                    f"add to the correct domain in DOMAINS"
                )
            # Check for double-listing (a verb in multiple domains is a data error).
            domain_counts[verb] = domain_counts.get(verb, 0) + 1
            # This counter should always be 1 (or 0 if we never found it), but let's verify
            # by checking the DOMAINS dict directly.

        # Direct check: count how many domains list each verb.
        verb_domain_count: dict[str, int] = {}
        for domain, verbs_in_domain in ci.DOMAINS.items():
            for verb in verbs_in_domain:
                verb_domain_count[verb] = verb_domain_count.get(verb, 0) + 1

        for verb in live_names:
            count = verb_domain_count.get(verb, 0)
            if count > 1:
                unclassified.append(
                    f"'{verb}' is listed in {count} domains (expected exactly 1) — "
                    f"remove duplicates from DOMAINS"
                )

        return stale_entries, unclassified

    def test_no_stale_domains_entries(self):
        """Invariant 1: every DOMAINS entry must be a registered verb."""
        stale, _ = self._scan()
        self.assertEqual(
            stale, [],
            "DOMAINS contains stale entries (verbs no longer in the live CLI) — "
            "remove them from lgwks_cli_introspect.py::DOMAINS:\n  "
            + "\n  ".join(stale),
        )

    def test_every_live_verb_classified_once(self):
        """Invariant 2: every live verb must be classified exactly once."""
        _, unclassified = self._scan()
        self.assertEqual(
            unclassified, [],
            "live verbs are unclassified or double-listed — "
            "add to correct domain (or OTHER_ALLOWED if genuinely unclassified) in DOMAINS:\n  "
            + "\n  ".join(unclassified),
        )


if __name__ == "__main__":
    unittest.main()
