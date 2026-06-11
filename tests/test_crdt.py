"""Tests for lgwks_crdt — I9 CRDT state (T1–T6).

All tests map to SEC proof clauses from PLANS-NEXT-4.md §PACKET I9
(authority: INGESTION-LAYER §6, INGESTION-PLAN §I9).

  T1: convergence       — same update multiset in N permutations across M replicas
                         → all replicas converge to byte-identical state (SEC proof).
  T2: idempotent_add    — adding the same cid-fact twice is a no-op (G-Set; I1 dedup).
  T3: cvrdt_laws        — merge is commutative, associative, idempotent (property tests).
  T4: orset_add_wins    — concurrent add + remove → element present (OR-Set semantics).
  T5: lww_determinism   — tie-break uses (seq, head), NOT wall-clock; same inputs → same winner.
  T6: serialise_roundtrip — serialise + deserialise round-trip produces identical state.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_crdt
from lgwks_crdt import (
    SCHEMA,
    GSet,
    ORSet,
    LWWRegister,
    merge_state,
    serialise,
    deserialise,
)


# ---------------------------------------------------------------------------
# T1 — SEC convergence (byte-identical across random permutations)
# ---------------------------------------------------------------------------

class TestConvergence(unittest.TestCase):
    """T1: apply the same update multiset in N random permutations → byte-identical state."""

    N_PERMS = 8
    M_REPLICAS = 4
    ELEMS = [f"cid-{i:04d}" for i in range(12)]

    def _apply_gset_ops(self, ops: list[str]) -> GSet:
        s = GSet()
        for cid in ops:
            s = s.add(cid)
        return s

    def test_gset_convergence(self):
        rng = random.Random(42)
        states = []
        for _ in range(self.N_PERMS):
            ops = list(self.ELEMS)
            rng.shuffle(ops)
            states.append(self._apply_gset_ops(ops))

        # Merge all states pairwise into one
        merged = states[0]
        for s in states[1:]:
            merged = merged.merge(s)

        ref = json.dumps(serialise(merged), sort_keys=True)
        # Every permutation should converge to the same state via pairwise merge
        for perm_state in states:
            self.assertEqual(
                perm_state.value(), merged.value(),
                msg="T1: GSet must converge regardless of application order",
            )
        # byte-identical serialisation
        for perm_state in states:
            m2 = merged.merge(perm_state)
            got = json.dumps(serialise(m2), sort_keys=True)
            self.assertEqual(got, ref, "T1: byte-identical GSet convergence required")

    def test_orset_convergence(self):
        rng = random.Random(99)
        # Build identical add operations across replicas
        base_tags = {cid: rng.randbytes(8).hex() for cid in self.ELEMS[:6]}
        def _apply(ops):
            s = ORSet()
            for cid, tag in ops:
                s = s.add(cid, tag)
            return s

        ops = [(cid, tag) for cid, tag in base_tags.items()]
        states = []
        for _ in range(self.N_PERMS):
            shuffled = list(ops)
            rng.shuffle(shuffled)
            states.append(_apply(shuffled))

        merged = states[0]
        for s in states[1:]:
            merged = merged.merge(s)

        ref_value = merged.value()
        for s in states:
            self.assertEqual(s.value(), ref_value, "T1: OR-Set must converge")


# ---------------------------------------------------------------------------
# T2 — idempotent add
# ---------------------------------------------------------------------------

class TestIdempotentAdd(unittest.TestCase):
    """T2: adding the same cid twice is a no-op (G-Set; I1 cid dedup invariant)."""

    def test_gset_add_twice(self):
        s = GSet()
        s1 = s.add("cid-abc")
        s2 = s1.add("cid-abc")   # duplicate
        self.assertEqual(s1.value(), s2.value(), "T2: duplicate add must be a no-op")
        self.assertEqual(len(s2.value()), 1, "T2: exactly one element after duplicate add")

    def test_gset_add_many_duplicates(self):
        s = GSet()
        for _ in range(100):
            s = s.add("cid-repeat")
        self.assertEqual(len(s.value()), 1, "T2: 100 duplicate adds → one element")

    def test_orset_add_same_elem_different_tags(self):
        s = ORSet()
        s = s.add("elem-a", "tag-1")
        s = s.add("elem-a", "tag-2")   # same elem, new tag
        self.assertIn("elem-a", s.value(), "T2: OR-Set elem with multiple tags is visible")

    def test_merge_idempotent(self):
        s = GSet()
        for i in range(5):
            s = s.add(f"cid-{i}")
        merged = s.merge(s)
        self.assertEqual(merged.value(), s.value(), "T2: merge(a,a) == a (idempotent)")


# ---------------------------------------------------------------------------
# T3 — CvRDT laws
# ---------------------------------------------------------------------------

class TestCvRDTLaws(unittest.TestCase):
    """T3: merge is commutative, associative, idempotent — property tests over random states."""

    def _random_gset(self, rng: random.Random, n: int = 8) -> GSet:
        s = GSet()
        for _ in range(rng.randint(0, n)):
            s = s.add(f"cid-{rng.randint(0, 20):04d}")
        return s

    def _random_orset(self, rng: random.Random) -> ORSet:
        s = ORSet()
        elems = [f"e{i}" for i in range(rng.randint(1, 6))]
        for e in elems:
            tag = rng.randbytes(8).hex()
            s = s.add(e, tag)
        return s

    def _random_lww(self, rng: random.Random) -> LWWRegister:
        r = LWWRegister()
        for _ in range(rng.randint(1, 5)):
            seq = rng.randint(0, 100)
            head = rng.randbytes(16).hex()
            r = r.set(rng.randint(0, 1000), head=head, seq=seq)
        return r

    def _check_laws(self, a, b, c, label: str) -> None:
        # Commutative
        self.assertEqual(
            a.merge(b).value() if hasattr(a.merge(b), "value") else a.merge(b),
            b.merge(a).value() if hasattr(b.merge(a), "value") else b.merge(a),
            f"T3 {label}: merge must be commutative",
        )
        # Idempotent
        self.assertEqual(
            a.merge(a).value() if hasattr(a.merge(a), "value") else a.merge(a),
            a.value() if hasattr(a, "value") else a,
            f"T3 {label}: merge(a,a) must equal a (idempotent)",
        )

    def test_gset_laws(self):
        rng = random.Random(7)
        for _ in range(30):
            a = self._random_gset(rng)
            b = self._random_gset(rng)
            c = self._random_gset(rng)
            # Commutative
            self.assertEqual(a.merge(b).value(), b.merge(a).value(), "T3: GSet commutative")
            # Associative
            self.assertEqual(
                a.merge(b).merge(c).value(),
                a.merge(b.merge(c)).value(),
                "T3: GSet associative",
            )
            # Idempotent
            self.assertEqual(a.merge(a).value(), a.value(), "T3: GSet idempotent")

    def test_lww_commutative(self):
        rng = random.Random(13)
        for _ in range(30):
            a = self._random_lww(rng)
            b = self._random_lww(rng)
            ab = a.merge(b)
            ba = b.merge(a)
            self.assertEqual(ab, ba, "T3: LWW merge must be commutative")

    def test_lww_idempotent(self):
        rng = random.Random(17)
        for _ in range(20):
            a = self._random_lww(rng)
            self.assertEqual(a.merge(a), a, "T3: LWW merge(a,a) must equal a")


# ---------------------------------------------------------------------------
# T4 — OR-Set add-wins
# ---------------------------------------------------------------------------

class TestORSetAddWins(unittest.TestCase):
    """T4: concurrent add + remove of same element → element present (add-wins)."""

    def test_concurrent_add_remove(self):
        # Replica A: adds elem with tag-1
        ra = ORSet().add("elem-x", "tag-1")
        # Replica B: starts from same state, removes the elem
        rb = ra.remove("elem-x", frozenset(["tag-1"]))
        # Replica A concurrently adds with a NEW tag (this is the concurrent add)
        ra2 = ra.add("elem-x", "tag-2")
        # Merge A2 + B: tag-2 was never observed by B → survives remove → add-wins
        merged = ra2.merge(rb)
        self.assertIn("elem-x", merged.value(),
                      "T4: concurrent add (new tag) must survive remove (add-wins)")

    def test_remove_only_observed_tags(self):
        s = ORSet()
        s = s.add("e", "t1")
        s = s.add("e", "t2")
        observed = frozenset(["t1"])
        s = s.remove("e", observed)   # only cancel t1
        self.assertIn("e", s.value(), "T4: element still visible when only some tags removed")

    def test_remove_all_tags(self):
        s = ORSet()
        s = s.add("e", "t1")
        s = s.remove("e")   # remove all
        self.assertNotIn("e", s.value(), "T4: element gone after all tags removed")


# ---------------------------------------------------------------------------
# T5 — LWW determinism (no wall-clock)
# ---------------------------------------------------------------------------

class TestLWWDeterminism(unittest.TestCase):
    """T5: tie-break uses (seq, head) NOT wall-clock; same inputs → same winner."""

    def test_higher_seq_wins(self):
        r = LWWRegister()
        r1 = r.set("value-A", head="aaa", seq=5)
        r2 = r.set("value-B", head="bbb", seq=10)
        merged = r1.merge(r2)
        self.assertEqual(merged.value(), "value-B", "T5: higher seq must win")

    def test_equal_seq_head_breaks_tie(self):
        r = LWWRegister()
        r1 = r.set("low", head="aaa", seq=5)
        r2 = r.set("high", head="zzz", seq=5)   # same seq, higher head bytes
        merged = r1.merge(r2)
        self.assertEqual(merged.value(), "high", "T5: equal seq → higher head wins")

    def test_deterministic_across_runs(self):
        """T5: identical (seq, head) → identical winner on two separate runs."""
        def _run():
            r = LWWRegister()
            r = r.set("a", head="abc123", seq=7)
            r2 = LWWRegister()
            r2 = r2.set("b", head="abc124", seq=7)
            return r.merge(r2).value()

        self.assertEqual(_run(), _run(), "T5: deterministic merge across runs")

    def test_no_wallclock_dependency(self):
        """T5: result must not change when time.monotonic is patched (wall-clock free)."""
        import time as _time
        orig = _time.monotonic
        _time.monotonic = lambda: 0.0
        try:
            r1 = LWWRegister().set("x", head="h1", seq=3)
            r2 = LWWRegister().set("y", head="h2", seq=4)
            result = r1.merge(r2).value()
        finally:
            _time.monotonic = orig
        self.assertEqual(result, "y", "T5: LWW result must be independent of wall-clock")


# ---------------------------------------------------------------------------
# T6 — serialise / deserialise round-trip
# ---------------------------------------------------------------------------

class TestSerialiseRoundtrip(unittest.TestCase):
    """T6: serialise + deserialise produces identical state."""

    def test_gset_roundtrip(self):
        s = GSet()
        for i in range(5):
            s = s.add(f"cid-{i:04d}")
        d = serialise(s)
        self.assertEqual(d["schema"], SCHEMA)
        self.assertEqual(d["type"], "gset")
        s2 = deserialise(d)
        self.assertEqual(s.value(), s2.value(), "T6: GSet round-trip must match")

    def test_orset_roundtrip(self):
        s = ORSet()
        s = s.add("e1", "t1")
        s = s.add("e2", "t2")
        s = s.remove("e1", frozenset(["t1"]))
        d = serialise(s)
        self.assertEqual(d["schema"], SCHEMA)
        self.assertEqual(d["type"], "orset")
        s2 = deserialise(d)
        self.assertEqual(s.value(), s2.value(), "T6: OR-Set round-trip must match")

    def test_lww_roundtrip(self):
        r = LWWRegister().set(42, head="headhash", seq=7)
        d = serialise(r)
        self.assertEqual(d["schema"], SCHEMA)
        self.assertEqual(d["type"], "lww")
        r2 = deserialise(d)
        self.assertEqual(r.value(), r2.value(), "T6: LWW round-trip must match")
        self.assertEqual(r, r2, "T6: LWW round-trip must be identical")

    def test_type_mismatch_raises(self):
        with self.assertRaises(TypeError):
            merge_state(GSet(), ORSet())


if __name__ == "__main__":
    unittest.main()
