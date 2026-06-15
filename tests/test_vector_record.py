"""Acceptance tests for lgwks.vector.record.v1 (I1).

Acceptance criteria from INGESTION-PLAN §I1:
  A1. round-trip a vector → bit-identical out
  A2. ‖ê‖ = 1 ± 1e-6
  A3. identical input bytes → identical cid (dedup)
  A4. cross-space compare raises (never silently compares)
  A5. manifest declares space_id; cross-space compare raises

All tests are pure (no network, no DB on disk) except the store tests which use :memory:.
"""

from __future__ import annotations

import math
import sqlite3
import sys
import unittest
from pathlib import Path

# ensure repo root is importable when run from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_vector as vmod
from lgwks_vector import (
    VectorRecord,
    SpaceMismatchError,
    VectorError,
    cosine,
    decode_record,
    encode_record,
    get_record,
    require_same_space,
    upsert_record,
    SCHEMA,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _vec(n: int = 8, *, scale: float = 1.0) -> list[float]:
    """Reproducible non-trivial vector of length n."""
    return [scale * (i + 1) * 0.1 for i in range(n)]


def _make_record(**kwargs) -> VectorRecord:
    defaults = dict(
        floats=_vec(),
        modality="text",
        space_id="test-space:d8",
        tenant="test-tenant",
        source_cid="b2b256:" + "a" * 64,
    )
    defaults.update(kwargs)
    return encode_record(defaults.pop("floats"), **defaults)


# ---------------------------------------------------------------------------
# A2 — normalization: ‖ê‖ = 1 ± 1e-6
# ---------------------------------------------------------------------------

class TestNormalization(unittest.TestCase):
    def test_norm_one(self):
        r = _make_record()
        floats = r.floats()
        norm = math.sqrt(sum(x * x for x in floats))
        self.assertAlmostEqual(norm, 1.0, delta=1e-6, msg="stored embedding is not unit norm")

    def test_norm_stored_is_pre_normalization(self):
        raw = _vec(scale=3.0)
        pre_norm_expected = math.sqrt(sum(x * x for x in raw))
        r = _make_record(floats=raw)
        self.assertAlmostEqual(r.norm, pre_norm_expected, delta=1e-5)

    def test_zero_vector_raises(self):
        with self.assertRaises(VectorError):
            encode_record([0.0] * 8, modality="text", space_id="s", tenant="t",
                          source_cid="b2b256:" + "a" * 64)


# ---------------------------------------------------------------------------
# A1 — round-trip: encode → decode → bit-identical floats
# ---------------------------------------------------------------------------

class TestRoundTrip(unittest.TestCase):
    def test_bit_identical_floats(self):
        raw = _vec(n=16)
        r = encode_record(raw, modality="text", space_id="sp:d16",
                          tenant="t", source_cid="b2b256:" + "b" * 64)
        # simulate DB round-trip by packing into the row tuple
        row = (r.cid, r.modality, r.embedding, r.norm, r.dim,
               r.space_id, r.tenant, r.source_cid)
        r2 = decode_record(row)
        self.assertEqual(r2.cid, r.cid)
        self.assertEqual(r2.embedding, r.embedding)   # byte-identical
        self.assertEqual(r2.floats(), r.floats())

    def test_dim_matches_input(self):
        for n in (64, 128, 512, 4096):
            floats = [0.1] * n
            r = encode_record(floats, modality="image", space_id=f"sp:d{n}",
                              tenant="t", source_cid="b2b256:" + "c" * 64)
            self.assertEqual(r.dim, n)

    def test_cid_verify_tamper_raises(self):
        from axiom.cid import CidError
        r = _make_record()
        tampered_embedding = bytes([b ^ 0xFF for b in r.embedding[:4]]) + r.embedding[4:]
        row = (r.cid, r.modality, tampered_embedding, r.norm, r.dim,
               r.space_id, r.tenant, r.source_cid)
        with self.assertRaises(CidError):
            decode_record(row)


# ---------------------------------------------------------------------------
# A3 — dedup: identical inputs → identical cid
# ---------------------------------------------------------------------------

class TestDedup(unittest.TestCase):
    def test_same_inputs_same_cid(self):
        kwargs = dict(modality="text", space_id="sp", tenant="t",
                      source_cid="b2b256:" + "d" * 64)
        r1 = encode_record(_vec(), **kwargs)
        r2 = encode_record(_vec(), **kwargs)
        self.assertEqual(r1.cid, r2.cid)
        self.assertEqual(r1.embedding, r2.embedding)

    def test_different_source_different_cid(self):
        base = dict(modality="text", space_id="sp", tenant="t")
        r1 = encode_record(_vec(), source_cid="b2b256:" + "0" * 64, **base)
        r2 = encode_record(_vec(), source_cid="b2b256:" + "1" * 64, **base)
        self.assertNotEqual(r1.cid, r2.cid)

    def test_different_space_different_cid(self):
        base = dict(modality="text", tenant="t", source_cid="b2b256:" + "e" * 64)
        r1 = encode_record(_vec(), space_id="space-A", **base)
        r2 = encode_record(_vec(), space_id="space-B", **base)
        self.assertNotEqual(r1.cid, r2.cid)


# ---------------------------------------------------------------------------
# A4 / A5 — cross-space guard
# ---------------------------------------------------------------------------

class TestCrossSpaceGuard(unittest.TestCase):
    def test_same_space_ok(self):
        r1 = _make_record(space_id="sp")
        r2 = _make_record(space_id="sp", source_cid="b2b256:" + "f" * 64)
        sim = cosine(r1, r2)
        self.assertGreaterEqual(sim, -1.0)
        self.assertLessEqual(sim, 1.0)  # cosine() clamps f32 overflow

    def test_different_space_raises(self):
        r1 = _make_record(space_id="space-A")
        r2 = _make_record(space_id="space-B", source_cid="b2b256:" + "f" * 64)
        with self.assertRaises(SpaceMismatchError):
            cosine(r1, r2)

    def test_require_same_space_identical_ok(self):
        r1 = _make_record(space_id="sp")
        r2 = _make_record(space_id="sp", source_cid="b2b256:" + "f" * 64)
        require_same_space(r1, r2)  # must not raise

    def test_cosine_of_identical_normalized_is_one(self):
        raw = _vec(n=32)
        kwargs = dict(modality="text", space_id="sp:d32", tenant="t",
                      source_cid="b2b256:" + "a" * 64)
        r = encode_record(raw, **kwargs)
        # cosine with itself = 1.0
        self.assertAlmostEqual(cosine(r, r), 1.0, delta=1e-5)


# ---------------------------------------------------------------------------
# Store: upsert idempotency
# ---------------------------------------------------------------------------

class TestStore(unittest.TestCase):
    def _mem_store(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(vmod.VECTOR_RECORDS_DDL)
        conn.commit()
        return conn

    def test_upsert_inserts_new(self):
        conn = self._mem_store()
        r = _make_record()
        self.assertTrue(upsert_record(conn, r, admin=vmod.ADMIN))

    def test_upsert_idempotent(self):
        conn = self._mem_store()
        r = _make_record()
        upsert_record(conn, r, admin=vmod.ADMIN)
        second = upsert_record(conn, r, admin=vmod.ADMIN)
        self.assertFalse(second, "second upsert of same cid must be a no-op")
        count = conn.execute("SELECT COUNT(*) FROM vector_records").fetchone()[0]
        self.assertEqual(count, 1)

    def test_roundtrip_via_store(self):
        conn = self._mem_store()
        r = _make_record()
        conn.commit()
        upsert_record(conn, r, admin=vmod.ADMIN)
        conn.commit()
        r2 = get_record(conn, r.cid, admin=vmod.ADMIN)
        self.assertIsNotNone(r2)
        self.assertEqual(r2.cid, r.cid)
        self.assertEqual(r2.embedding, r.embedding)
        self.assertEqual(r2.space_id, r.space_id)

    def test_schema_field_stored(self):
        conn = self._mem_store()
        r = _make_record()
        upsert_record(conn, r, admin=vmod.ADMIN)
        conn.commit()
        schema_val = conn.execute(
            "SELECT schema FROM vector_records WHERE cid = ?", (r.cid,)
        ).fetchone()[0]
        self.assertEqual(schema_val, SCHEMA)


# ---------------------------------------------------------------------------
# Validation guards
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):
    def test_empty_space_id_raises(self):
        with self.assertRaises(VectorError):
            encode_record(_vec(), modality="text", space_id="",
                          tenant="t", source_cid="b2b256:" + "a" * 64)

    def test_unknown_modality_raises(self):
        with self.assertRaises(VectorError):
            encode_record(_vec(), modality="pdf", space_id="sp",
                          tenant="t", source_cid="b2b256:" + "a" * 64)

    def test_empty_floats_raises(self):
        with self.assertRaises(VectorError):
            encode_record([], modality="text", space_id="sp",
                          tenant="t", source_cid="b2b256:" + "a" * 64)


class TestVectorRecordV2Metadata(unittest.TestCase):
    def test_v2_fields_roundtrip(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(vmod.VECTOR_RECORDS_DDL)
        r = encode_record(
            _vec(),
            modality="text",
            space_id="sp:v2",
            tenant="t",
            source_cid="b2b256:" + "a" * 64,
            tokenization_id="word_regex:v1",
            artifact_cid="b2b256:" + "b" * 64,
        )
        upsert_record(conn, r, admin=vmod.ADMIN)
        r2 = get_record(conn, r.cid, admin=vmod.ADMIN)
        self.assertIsNotNone(r2)
        self.assertEqual(r2.tokenization_id, "word_regex:v1")
        self.assertEqual(r2.artifact_cid, "b2b256:" + "b" * 64)

    def test_v2_fields_not_in_cid(self):
        """Same bytes with different tokenization_id/artifact_cid must dedup."""
        base = dict(modality="text", space_id="sp:v2", tenant="t",
                    source_cid="b2b256:" + "a" * 64)
        r1 = encode_record(_vec(), tokenization_id="a:v1", artifact_cid="b2b256:00", **base)
        r2 = encode_record(_vec(), tokenization_id="b:v1", artifact_cid="b2b256:11", **base)
        self.assertEqual(r1.cid, r2.cid)


if __name__ == "__main__":
    unittest.main()
