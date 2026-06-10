"""Tests for lgwks_score — I5 deterministic schema scoring (T1–T5).

TDD: tests written first. All five map to proof clauses from the I5 spec comment
(issue #59, authority: INGESTION-LAYER §4.2/§4.4/§4.5).

  T1: marginal identity   — (1/m) Σ_k score(i,k,j) = cosine(i,j) to ≤1e-6
  T2: directionality      — directed R_k gives asymmetric scores; symmetric gives equality
  T3: cross-model cid     — same canonical content → identical cid + canonical bytes
  T4: MDL separation      — conformant ≥ 0.20; Δ(conformant − corrupted) ≥ 0.15
  T5: replay/determinism  — same schema → byte-identical operators; same instance → identical scores
"""

from __future__ import annotations

import hashlib
import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_score import (
    RELATIONS,
    RELATIONS_SCHEMA,
    SCHEMA,
    FactoredRelation,
    build_operators,
    canonicalize,
    content_cid,
    score_mdl,
    score_triple,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _l2_normalize(floats: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in floats))
    if n < 1e-12:
        raise ValueError("zero vector")
    return [x / n for x in floats]


def _make_embedding(seed: int, dim: int = 16) -> list[float]:
    """Deterministic L2-normalized embedding. Identical seed+dim → identical result."""
    floats = []
    for i in range(dim):
        raw = hashlib.sha256(struct.pack(">II", seed, i)).digest()
        val = struct.unpack(">i", raw[:4])[0] / (2 ** 31)
        floats.append(val)
    return _l2_normalize(floats)


def _make_conformant_instance(seed: int) -> dict:
    """Deterministic conformant triple instance for MDL corpus."""
    rel = list(RELATIONS.keys())[seed % len(RELATIONS)]
    h_src = hashlib.sha256(f"node_{seed}".encode()).hexdigest()
    h_tgt = hashlib.sha256(f"node_{seed + 1000}".encode()).hexdigest()
    return {
        "i_cid": f"blake2b:{h_src}",
        "k": rel,
        "j_cid": f"blake2b:{h_tgt}",
        "weight": round(0.5 + (seed % 10) * 0.05, 4),
        "confidence_score": round(0.7 + (seed % 5) * 0.06, 4),
        "source_file": f"lgwks_module_{seed % 20}.py",
        "source_location": f"L{(seed % 500) + 1}",
        "schema_version": RELATIONS_SCHEMA,
    }


def _make_corrupted_instance(seed: int, corruption: str) -> dict:
    base = _make_conformant_instance(seed)
    if corruption == "drop_relation":
        # Drop all structural/schema fields AND use malformed (non-blake2b) identifiers
        # so the dict can't benefit from the "blake2b:..." prefix it learned from training.
        h = hashlib.sha256(f"corrupt_drop_{seed}".encode()).hexdigest()
        return {"i_cid": h[:20], "j_cid": h[20:40]}
    if corruption == "wrong_type":
        # Replace CID strings (dominant 73-byte values) with integers + corrupt relation type.
        # CBOR integer nodes diverge completely from the "blake2b:..." string patterns in the dict.
        h = hashlib.sha256(f"corrupt_type_{seed}".encode()).hexdigest()
        return {
            "i_cid": int(h[:8], 16),
            "k": None,
            "j_cid": int(h[8:16], 16),
            "weight": base["weight"],
            "confidence_score": base["confidence_score"],
        }
    if corruption == "key_shuffle":
        h = hashlib.sha256(f"corrupt_{seed}".encode()).hexdigest()
        return {
            "x1": h[:16],
            "x2": h[16:32],
            "x3": float(int(h[32:40], 16) % 100),
            "x4": float(int(h[40:48], 16) % 100),
        }
    raise ValueError(f"unknown corruption: {corruption!r}")


# ---------------------------------------------------------------------------
# T1 — Marginal identity (§4.2)
# ---------------------------------------------------------------------------

class TestMarginalIdentity(unittest.TestCase):
    """(1/m) Σ_k score(i,k,j) must equal cosine(i,j) to ≤1e-6 with all default operators."""

    DIM = 16
    N = 6

    def setUp(self):
        self.embs = [_make_embedding(i, self.DIM) for i in range(self.N)]
        self.ops = build_operators(self.DIM)

    def _cosine(self, a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def test_marginal_identity_all_pairs(self):
        m = len(self.ops)
        for i in range(self.N):
            for j in range(self.N):
                expected = self._cosine(self.embs[i], self.embs[j])
                rescal_avg = sum(
                    score_triple(self.embs[i], rel, self.embs[j])
                    for rel in self.ops.values()
                ) / m
                self.assertAlmostEqual(
                    rescal_avg, expected, delta=1e-6,
                    msg=f"T1 failed pair ({i},{j}): rescal_avg={rescal_avg}, cosine={expected}",
                )


# ---------------------------------------------------------------------------
# T2 — Directionality (§4.5)
# ---------------------------------------------------------------------------

class TestDirectionality(unittest.TestCase):
    """Directed R_k (non-identity P_k) must give score(i,k,j) ≠ score(j,k,i).
    Identity P_k (symmetric) must give equality."""

    DIM = 8

    def setUp(self):
        self.e1 = _l2_normalize([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        self.e2 = _l2_normalize([8.0, 1.0, 3.0, 5.0, 2.0, 7.0, 4.0, 6.0])

    def test_directed_relation_asymmetric(self):
        # Cyclic shift of first 3 dims: 0→1→2→0. NOT self-inverse → P_k^T ≠ P_k → asymmetric scores.
        # A swap (0↔1) is self-inverse (P^T=P) so score(i→j)=score(j→i); cyclic avoids that trap.
        perm = (1, 2, 0) + tuple(range(3, self.DIM))
        directed = FactoredRelation(
            relation_id="test_directed",
            perm=perm,
            signs=None,
            mask=None,
            direction="directed",
        )
        s_ij = score_triple(self.e1, directed, self.e2)
        s_ji = score_triple(self.e2, directed, self.e1)
        self.assertNotAlmostEqual(
            s_ij, s_ji, places=7,
            msg=f"T2 directed must be asymmetric: s(i→j)={s_ij}, s(j→i)={s_ji}",
        )

    def test_symmetric_relation_equal(self):
        sym = FactoredRelation(
            relation_id="test_symmetric",
            perm=None,
            signs=None,
            mask=None,
            direction="symmetric",
        )
        s_ij = score_triple(self.e1, sym, self.e2)
        s_ji = score_triple(self.e2, sym, self.e1)
        self.assertAlmostEqual(
            s_ij, s_ji, places=12,
            msg=f"T2 identity P_k must be symmetric: s(i→j)={s_ij}, s(j→i)={s_ji}",
        )

    def test_default_operators_have_identity_perm(self):
        ops = build_operators(self.DIM)
        for rel_id, rel in ops.items():
            self.assertIsNone(rel.perm, f"v1 default: {rel_id!r} must have perm=None")
            self.assertIsNone(rel.mask, f"v1 default: {rel_id!r} must have mask=None")


# ---------------------------------------------------------------------------
# T3 — Cross-model CID idempotency (§4.4)
# ---------------------------------------------------------------------------

class TestCrossModelCid(unittest.TestCase):
    """Same logical content, different dict ordering → identical canonical bytes and cid."""

    def test_key_order_independent(self):
        a = {"i_cid": "x", "k": "calls", "j_cid": "y", "weight": 1.0, "confidence_score": 0.9}
        b = {"confidence_score": 0.9, "weight": 1.0, "j_cid": "y", "k": "calls", "i_cid": "x"}
        self.assertEqual(canonicalize(a), canonicalize(b))
        self.assertEqual(content_cid(a), content_cid(b))

    def test_s_ai_excluded_from_canonical(self):
        with_ai = {"i_cid": "a", "k": "uses", "j_cid": "b", "weight": 0.5, "s_ai": 0.8}
        without_ai = {"i_cid": "a", "k": "uses", "j_cid": "b", "weight": 0.5}
        self.assertEqual(canonicalize(with_ai), canonicalize(without_ai))
        self.assertEqual(content_cid(with_ai), content_cid(without_ai))

    def test_cid_is_blake2b_of_canonical(self):
        inst = _make_conformant_instance(7)
        canonical_bytes = canonicalize(inst)
        expected_cid = hashlib.blake2b(canonical_bytes, digest_size=32).hexdigest()
        self.assertEqual(content_cid(inst), expected_cid)


# ---------------------------------------------------------------------------
# T4 — MDL separation (§4.4)
# conformant ≥ 0.20; Δ(conformant − corrupted) ≥ 0.15
# ---------------------------------------------------------------------------

class TestMdlSeparation(unittest.TestCase):
    """Frozen corpus → dictionary → margin assertions.

    Fixtures frozen before running: corpus is deterministic (fixed seeds).
    """

    CORPUS_SIZE = 500
    DICT_SIZE = 16384
    ACCEPTANCE = 0.20
    MARGIN = 0.15

    @classmethod
    def setUpClass(cls):
        try:
            import cbor2  # noqa: F401
            import zstandard as zstd
        except ImportError as e:
            raise unittest.SkipTest(f"T4 requires cbor2 + zstandard: {e}")

        corpus = [canonicalize(_make_conformant_instance(i)) for i in range(cls.CORPUS_SIZE)]
        cls.dict_bytes = zstd.train_dictionary(cls.DICT_SIZE, corpus, level=3).as_bytes()

    def _score(self, inst: dict) -> float:
        return score_mdl(inst, self.dict_bytes)

    def test_conformant_above_acceptance(self):
        for seed in range(200, 220):
            inst = _make_conformant_instance(seed)
            s = self._score(inst)
            self.assertGreaterEqual(
                s, self.ACCEPTANCE,
                f"T4 conformant seed={seed}: score_mdl={s:.4f} < acceptance={self.ACCEPTANCE}",
            )

    def test_drop_relation_separation(self):
        for seed in range(200, 210):
            conformant = _make_conformant_instance(seed)
            corrupted = _make_corrupted_instance(seed, "drop_relation")
            s_c = self._score(conformant)
            s_x = self._score(corrupted)
            delta = s_c - s_x
            self.assertGreaterEqual(
                delta, self.MARGIN,
                f"T4 drop_relation seed={seed}: Δ={delta:.4f} < {self.MARGIN} "
                f"(conformant={s_c:.4f}, corrupted={s_x:.4f})",
            )

    def test_wrong_type_separation(self):
        for seed in range(200, 210):
            conformant = _make_conformant_instance(seed)
            corrupted = _make_corrupted_instance(seed, "wrong_type")
            s_c = self._score(conformant)
            s_x = self._score(corrupted)
            delta = s_c - s_x
            self.assertGreaterEqual(
                delta, self.MARGIN,
                f"T4 wrong_type seed={seed}: Δ={delta:.4f} < {self.MARGIN} "
                f"(conformant={s_c:.4f}, corrupted={s_x:.4f})",
            )

    def test_key_shuffle_separation(self):
        for seed in range(200, 210):
            conformant = _make_conformant_instance(seed)
            corrupted = _make_corrupted_instance(seed, "key_shuffle")
            s_c = self._score(conformant)
            s_x = self._score(corrupted)
            delta = s_c - s_x
            self.assertGreaterEqual(
                delta, self.MARGIN,
                f"T4 key_shuffle seed={seed}: Δ={delta:.4f} < {self.MARGIN} "
                f"(conformant={s_c:.4f}, corrupted={s_x:.4f})",
            )


# ---------------------------------------------------------------------------
# T5 — Replay / determinism
# ---------------------------------------------------------------------------

class TestReplayDeterminism(unittest.TestCase):
    """Same schema file → byte-identical operators. Same instance → byte-identical cid + scores."""

    DIM = 16

    def test_operators_deterministic_across_builds(self):
        ops_a = build_operators(self.DIM)
        ops_b = build_operators(self.DIM)
        self.assertEqual(list(ops_a.keys()), list(ops_b.keys()))
        for k in ops_a:
            self.assertEqual(ops_a[k], ops_b[k], f"operator {k!r} not deterministic")

    def test_canonical_form_deterministic(self):
        inst = _make_conformant_instance(42)
        self.assertEqual(canonicalize(inst), canonicalize(inst))

    def test_cid_deterministic(self):
        inst = _make_conformant_instance(99)
        self.assertEqual(content_cid(inst), content_cid(inst))

    def test_score_triple_deterministic(self):
        ops = build_operators(self.DIM)
        rel = ops["calls"]
        e1 = _make_embedding(1, self.DIM)
        e2 = _make_embedding(2, self.DIM)
        self.assertEqual(score_triple(e1, rel, e2), score_triple(e1, rel, e2))


# ---------------------------------------------------------------------------
# Schema / relation constants
# ---------------------------------------------------------------------------

class TestSchemaConstants(unittest.TestCase):
    def test_schema_ids_are_versioned_lgwks_strings(self):
        self.assertRegex(SCHEMA, r"^lgwks\..+\.v\d+$")
        self.assertRegex(RELATIONS_SCHEMA, r"^lgwks\..+\.v\d+$")

    def test_all_eight_relations_present(self):
        expected = {"calls", "contains", "method", "inherits",
                    "uses", "rationale_for", "imports_from", "case_of"}
        self.assertEqual(set(RELATIONS.keys()), expected)

    def test_all_relations_directed_v1(self):
        for rel_id, props in RELATIONS.items():
            self.assertEqual(props["direction"], "directed",
                             f"v1 decision: {rel_id!r} must be directed")


if __name__ == "__main__":
    unittest.main()
