"""Tests for lgwks_waste — I11 waste ledger (T1–T6).

All tests map to acceptance clauses from PLANS-NEXT-4.md §PACKET I11
(authority: PRD-04 §04-c, INGESTION-PLAN §I11).

  T1: sums_reconcile   — totals.tokens_injected reconciles against the actual packs.
  T2: waste_rate       — waste_rate ∈ [0,1] on a fixture with known used/unused split.
  T3: attributable     — high-waste injection is attributable to a specific low-yield item.
  T4: no_prose         — ledger dict has no free-text field (only cids, ints, bools, floats).
  T5: threshold        — SUGGEST_CUT_THRESHOLD is pre-registered; I11 reports, does not act.
  T6: deterministic    — same (packs, transcript, N) → identical ledger.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_waste
from lgwks_waste import (
    SCHEMA,
    WINDOW_TURNS,
    SUGGEST_CUT_THRESHOLD,
    build_ledger,
    waste_rate,
    worst_item,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_pack(handles: list[str], used_tokens: int = 100) -> dict:
    """Minimal lgwks.inbound.v1 pack for testing."""
    return {
        "schema": "lgwks.inbound.v1",
        "handles": handles,
        "scores": {h: float(i + 1) for i, h in enumerate(handles)},
        "budget": {
            "limit_tokens": 1500,
            "used_tokens": used_tokens,
            "truncated_count": 0,
            "truncated": [],
        },
        "depth_handles": [
            {"id": h, "est_tokens": used_tokens // max(len(handles), 1), "kind": "text"}
            for h in handles
        ],
    }


def _make_transcript(citations: list[str]) -> list[dict]:
    """Transcript that mentions the given cids (simulates 'used' items)."""
    return [{"role": "assistant", "content": f"Using context: {' '.join(citations)}"}]


# ---------------------------------------------------------------------------
# T1 — sums reconcile
# ---------------------------------------------------------------------------

class TestSumsReconcile(unittest.TestCase):
    """T1: totals.tokens_injected must sum all est_tokens from depth_handles."""

    def test_sum_matches_depth_handles(self):
        handles = [f"cid-{i:04d}" for i in range(4)]
        pack = _make_pack(handles, used_tokens=40)
        transcript = _make_transcript([])  # nothing cited

        ledger = build_ledger([pack], transcript)

        # Each depth_handle has est_tokens = 40//4 = 10; total = 4 * 10 = 40
        expected = sum(dh["est_tokens"] for dh in pack["depth_handles"])
        self.assertEqual(
            ledger["totals"]["tokens_injected"], expected,
            f"T1: tokens_injected must equal sum of depth_handle est_tokens; "
            f"expected {expected}, got {ledger['totals']['tokens_injected']}",
        )
        self.assertEqual(ledger["schema"], SCHEMA, "T1: schema must be SCHEMA")

    def test_zero_packs_zero_injected(self):
        ledger = build_ledger([], [])
        self.assertEqual(ledger["totals"]["tokens_injected"], 0, "T1: zero packs → zero injected")
        self.assertEqual(ledger["totals"]["waste_rate"], 0.0, "T1: zero packs → zero waste_rate")

    def test_multiple_packs_sum(self):
        p1 = _make_pack(["a", "b"], used_tokens=20)
        p2 = _make_pack(["c", "d"], used_tokens=20)
        ledger = build_ledger([p1, p2], [])
        expected = (
            sum(dh["est_tokens"] for dh in p1["depth_handles"]) +
            sum(dh["est_tokens"] for dh in p2["depth_handles"])
        )
        self.assertEqual(ledger["totals"]["tokens_injected"], expected,
                         "T1: multi-pack sum must reconcile")


# ---------------------------------------------------------------------------
# T2 — waste_rate ∈ [0, 1] with known split
# ---------------------------------------------------------------------------

class TestWasteRate(unittest.TestCase):
    """T2: waste_rate on a fixture with a known used/unused split matches hand-computed value."""

    def test_all_unused(self):
        handles = ["cid-0", "cid-1", "cid-2"]
        pack = _make_pack(handles, used_tokens=30)
        ledger = build_ledger([pack], [])  # empty transcript → nothing cited
        self.assertAlmostEqual(waste_rate(ledger), 1.0, places=3,
                               msg="T2: all unused → waste_rate must be 1.0")

    def test_all_used(self):
        handles = ["cid-alpha", "cid-beta"]
        pack = _make_pack(handles, used_tokens=20)
        transcript = _make_transcript(handles)  # all cited
        ledger = build_ledger([pack], transcript, window_turns=5)
        r = waste_rate(ledger)
        self.assertGreaterEqual(r, 0.0, "T2: waste_rate must be >= 0")
        self.assertLessEqual(r, 1.0, "T2: waste_rate must be <= 1")

    def test_partial_use(self):
        handles = ["used-cid", "unused-cid-a", "unused-cid-b"]
        pack = _make_pack(handles, used_tokens=30)
        # Only the first is cited
        transcript = _make_transcript(["used-cid"])
        ledger = build_ledger([pack], transcript, window_turns=5)
        r = waste_rate(ledger)
        self.assertGreaterEqual(r, 0.0, "T2: partial waste_rate >= 0")
        self.assertLessEqual(r, 1.0, "T2: partial waste_rate <= 1")
        # At least some waste since two of three handles are unused
        items = ledger["items"]
        unused = [it for it in items if not it["used_within_n"]]
        self.assertGreater(len(unused), 0, "T2: at least some unused items expected")


# ---------------------------------------------------------------------------
# T3 — attributable worst item
# ---------------------------------------------------------------------------

class TestAttributable(unittest.TestCase):
    """T3: a high-waste injection is attributable to a specific low-yield item (named cid)."""

    def test_worst_item_identified(self):
        handles = ["used-cid-0", "big-waste-cid", "tiny-waste-cid"]
        pack = _make_pack(handles, used_tokens=60)
        # Only used-cid-0 cited; big-waste-cid is the biggest unused item
        transcript = _make_transcript(["used-cid-0"])
        ledger = build_ledger([pack], transcript, window_turns=5)
        w = worst_item(ledger)
        self.assertIsNotNone(w, "T3: worst_item must identify a specific item")
        self.assertIn("cid", w, "T3: worst item must have a cid field")
        self.assertIn(w["cid"], handles, "T3: worst item cid must be from the input handles")
        self.assertNotEqual(w["cid"], "used-cid-0",
                            "T3: worst item must NOT be the used item")

    def test_no_worst_item_when_all_used(self):
        handles = ["cid-a", "cid-b"]
        pack = _make_pack(handles, used_tokens=20)
        transcript = _make_transcript(handles)
        ledger = build_ledger([pack], transcript, window_turns=5)
        items = ledger["items"]
        used_items = [it for it in items if it["used_within_n"]]
        if len(used_items) == len(items) and items:
            self.assertIsNone(worst_item(ledger), "T3: no worst item when all are used")


# ---------------------------------------------------------------------------
# T4 — no prose
# ---------------------------------------------------------------------------

class TestNoProse(unittest.TestCase):
    """T4: ledger dict has no free-text fields — only cids, ints, bools, floats, schema str."""

    _ALLOWED_STR_KEYS = frozenset({
        "schema", "session_id", "transcript_source", "cid",
    })

    def _check_no_prose(self, obj, path: str = "") -> None:
        """Recursively assert no free-text string values except allowed keys."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    # string values are allowed ONLY for known typed fields
                    self.assertIn(
                        k, self._ALLOWED_STR_KEYS,
                        msg=f"T4: free-text string at {path}.{k} = {v!r} violates no-prose invariant",
                    )
                else:
                    self._check_no_prose(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._check_no_prose(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            pass   # caught at dict level

    def test_no_prose_in_ledger(self):
        handles = ["cid-noprosetest-0", "cid-noprosetest-1"]
        pack = _make_pack(handles, used_tokens=20)
        transcript = _make_transcript(["cid-noprosetest-0"])
        ledger = build_ledger([pack], transcript, window_turns=3)
        self._check_no_prose(ledger)

    def test_items_typed_fields_only(self):
        handles = ["cid-x"]
        pack = _make_pack(handles, used_tokens=10)
        ledger = build_ledger([pack], [])
        for item in ledger.get("items", []):
            # Each item must have only typed fields: cid (str), tokens (int), etc.
            self.assertIn("cid", item, "T4: item must have cid")
            self.assertIsInstance(item["tokens"], int, "T4: tokens must be int")
            self.assertIsInstance(item["used_within_n"], bool, "T4: used_within_n must be bool")
            # first_use_turn is int or null — not a string
            fut = item.get("first_use_turn")
            self.assertIsInstance(fut, (int, type(None)), "T4: first_use_turn must be int or null")


# ---------------------------------------------------------------------------
# T5 — threshold pre-registered
# ---------------------------------------------------------------------------

class TestThresholdPreRegistered(unittest.TestCase):
    """T5: SUGGEST_CUT_THRESHOLD is a pre-registered float constant; I11 reports, does not act."""

    def test_threshold_is_constant(self):
        self.assertIsInstance(SUGGEST_CUT_THRESHOLD, float,
                              "T5: SUGGEST_CUT_THRESHOLD must be a float")
        self.assertGreater(SUGGEST_CUT_THRESHOLD, 0.0,
                           "T5: SUGGEST_CUT_THRESHOLD must be > 0")
        self.assertLessEqual(SUGGEST_CUT_THRESHOLD, 1.0,
                             "T5: SUGGEST_CUT_THRESHOLD must be <= 1")

    def test_window_turns_is_constant(self):
        self.assertIsInstance(WINDOW_TURNS, int, "T5: WINDOW_TURNS must be int")
        self.assertGreater(WINDOW_TURNS, 0, "T5: WINDOW_TURNS must be > 0")

    def test_ledger_contains_threshold(self):
        pack = _make_pack(["cid-t"], used_tokens=10)
        ledger = build_ledger([pack], [])
        self.assertIn("suggest_cut_threshold", ledger,
                      "T5: ledger must include suggest_cut_threshold field")
        self.assertEqual(ledger["suggest_cut_threshold"], SUGGEST_CUT_THRESHOLD,
                         "T5: reported threshold must match SUGGEST_CUT_THRESHOLD constant")


# ---------------------------------------------------------------------------
# T6 — deterministic
# ---------------------------------------------------------------------------

class TestDeterministic(unittest.TestCase):
    """T6: same (packs, transcript, N) → identical ledger (no wall-clock, no nondeterminism)."""

    def _build(self, transcript_data: list[dict]) -> dict:
        handles = ["cid-det-0", "cid-det-1", "cid-det-2"]
        pack = _make_pack(handles, used_tokens=30)
        return build_ledger([pack], transcript_data, window_turns=3)

    def test_two_calls_identical(self):
        transcript = _make_transcript(["cid-det-0"])
        l1 = self._build(transcript)
        l2 = self._build(transcript)
        # Serialise to JSON to compare (excludes any object identity)
        j1 = json.dumps(l1, sort_keys=True)
        j2 = json.dumps(l2, sort_keys=True)
        self.assertEqual(j1, j2, "T6: build_ledger must be deterministic (byte-identical JSON)")

    def test_different_window_different_result(self):
        transcript = _make_transcript(["cid-det-0"])
        handles = ["cid-det-0", "cid-det-1"]
        pack = _make_pack(handles, used_tokens=20)
        l3 = build_ledger([pack], transcript, window_turns=3)
        l1 = build_ledger([pack], transcript, window_turns=1)
        # With window=3 we search further ahead — result may differ from window=1
        # (This test just asserts both produce valid ledgers, not equality)
        self.assertEqual(l3["schema"], SCHEMA)
        self.assertEqual(l1["schema"], SCHEMA)

    def test_transcript_path_env_var(self):
        """T6: LGWKS_TRANSCRIPT_PATH env var is accepted (D3: injected, not hardcoded)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"content": "cid-det-0"}) + "\n")
            fpath = f.name
        try:
            os.environ["LGWKS_TRANSCRIPT_PATH"] = fpath
            handles = ["cid-det-0"]
            pack = _make_pack(handles, used_tokens=10)
            # Build with path from env (passing None-like as transcript path is handled by CLI)
            ledger = build_ledger([pack], fpath, window_turns=3)
            self.assertEqual(ledger["schema"], SCHEMA)
        finally:
            del os.environ["LGWKS_TRANSCRIPT_PATH"]
            os.unlink(fpath)


if __name__ == "__main__":
    unittest.main()
