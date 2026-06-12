"""Acceptance tests for I8-hardening L5 — audited tenant→world promotion (#89).

Covers the L5 contract (ARCH-two-db-multitenant.md gap L5; spec on #89):
  P1. WORLD_PROMOTE scope is required — a default (tenant:rw + world:r) token is
      rejected, the row is NOT moved, and NO audit is written.
  P2. A tenant promoting its OWN row: the row's tenant flips T -> 'world', a
      "promotion" audit lands on the cognition chain, and the chain verifies.
  P3. §1-INV after promotion: the promoted row is now visible to every tenant via
      query_for_tenant; an UNpromoted private row of another tenant stays hidden.
  P4. Own-row only, no existence side-channel: promoting an absent cid, another
      tenant's row, or an already-world row all raise the SAME PromotionError and
      write NO audit.
  P5. Audit-gates-commit (D5): if the audit append fails, the staged move is
      rolled back — the row stays private and no promotion is durable.
  P6. The audit payload records who/what/under-which-cap and never the raw secret.

Real on-disk store (create_store) so commit/rollback + cross-instance chain reads
are exercised, not faked.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_capability as capability
import lgwks_cognition as cognition
import lgwks_promote as promote
import lgwks_vector as vmod
from lgwks_vector import WORLD_TENANT, create_store, encode_record, query_for_tenant, upsert_record

_AUDIT_KEY = b"l5-audit-key"
_STREAM = "promotions-test"


def _make_record(idx: int, tenant: str, space_id: str = "test:d4") -> vmod.VectorRecord:
    floats = [float(idx % 4 + 1), 1.0, 0.0, 0.0]
    return encode_record(
        floats, modality="text", space_id=space_id, tenant=tenant,
        source_cid=f"src-{idx}-{tenant}",
    )


class TestPromotionAudit(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # Redirect the cognition store into the tmp dir so tests never touch the
        # real chain (same idiom as tests/test_stores.py).
        cognition._DIR = self.tmp / "cognition"
        self.conn = create_store(self.tmp / "vec.db")

    def tearDown(self):
        self.conn.close()

    def _audits(self) -> list[dict]:
        """Read back the promotion audit records; also verifies the chain."""
        return cognition.CognitionLog(_STREAM, key=_AUDIT_KEY).corpus("promotion")

    def _tenant_of(self, cid: str) -> str | None:
        rec = vmod.get_record(self.conn, cid)
        return rec.tenant if rec else None

    def _promote_token(self, tenant: str):
        scopes = {capability.TENANT_RW, capability.WORLD_R, capability.WORLD_PROMOTE}
        return capability.issue_token(tenant, scopes=frozenset(scopes))

    # -- P1 ----------------------------------------------------------------
    def test_promotion_requires_world_promote_scope(self):
        rec = _make_record(1, "tenant-A")
        upsert_record(self.conn, rec)
        self.conn.commit()
        token, key = capability.issue_token("tenant-A")  # DEFAULT_SCOPES: no promote

        with self.assertRaises(capability.CapabilityError):
            promote.promote(self.conn, rec.cid, token, key,
                            stream=_STREAM, cognition_key=_AUDIT_KEY)

        self.assertEqual(self._tenant_of(rec.cid), "tenant-A", "row must NOT have moved")
        self.assertEqual(self._audits(), [], "refused promotion writes no audit")

    # -- P2 ----------------------------------------------------------------
    def test_own_row_promotes_and_is_audited(self):
        rec = _make_record(2, "tenant-A")
        upsert_record(self.conn, rec)
        self.conn.commit()
        token, key = self._promote_token("tenant-A")

        result = promote.promote(self.conn, rec.cid, token, key,
                                 stream=_STREAM, cognition_key=_AUDIT_KEY)

        self.assertEqual(self._tenant_of(rec.cid), WORLD_TENANT, "row flips to world tier")
        self.assertEqual(result["promoted"], rec.cid)
        self.assertEqual(result["scope"], capability.WORLD_PROMOTE)

        audits = self._audits()
        self.assertEqual(len(audits), 1, "exactly one promotion audit on the chain")
        self.assertEqual(audits[0]["cid"], rec.cid)
        self.assertEqual(audits[0]["tenant"], "tenant-A")
        self.assertTrue(
            cognition.CognitionLog(_STREAM, key=_AUDIT_KEY).verify(),
            "cognition chain verifies after the audited promotion",
        )

    # -- P3 ----------------------------------------------------------------
    def test_promoted_row_visible_to_all_promotes_only_target(self):
        rec_a = _make_record(3, "tenant-A")
        rec_b = _make_record(4, "tenant-B")
        upsert_record(self.conn, rec_a)
        upsert_record(self.conn, rec_b)
        self.conn.commit()

        token, key = self._promote_token("tenant-A")
        promote.promote(self.conn, rec_a.cid, token, key,
                        stream=_STREAM, cognition_key=_AUDIT_KEY)

        # B (an unrelated tenant) now sees the promoted A-row (it is world)...
        b_cids = {r.cid for r in query_for_tenant(self.conn, "tenant-B")}
        self.assertIn(rec_a.cid, b_cids, "promoted row is world-visible to every tenant")
        # ...but B's own private row is still invisible to A — §1-INV holds.
        a_cids = {r.cid for r in query_for_tenant(self.conn, "tenant-A")}
        self.assertNotIn(rec_b.cid, a_cids, "an unpromoted private row stays isolated")

    # -- P4 ----------------------------------------------------------------
    def test_cannot_promote_absent_foreign_or_world_row_no_sidechannel(self):
        rec_b = _make_record(5, "tenant-B")
        rec_w = _make_record(6, WORLD_TENANT)
        upsert_record(self.conn, rec_b)
        upsert_record(self.conn, rec_w)
        self.conn.commit()

        token, key = self._promote_token("tenant-A")  # A holds promote, owns nothing here
        msgs = set()
        for target in ("cid-does-not-exist", rec_b.cid, rec_w.cid):
            with self.assertRaises(promote.PromotionError) as ctx:
                promote.promote(self.conn, target, token, key,
                                stream=_STREAM, cognition_key=_AUDIT_KEY)
            msgs.add(str(ctx.exception))

        self.assertEqual(len(msgs), 1, "absent / foreign / world all raise the SAME message — no existence leak")
        self.assertEqual(self._tenant_of(rec_b.cid), "tenant-B", "foreign row untouched")
        self.assertEqual(self._tenant_of(rec_w.cid), WORLD_TENANT, "world row untouched")
        self.assertEqual(self._audits(), [], "no refused attempt is audited")

    # -- P5 ----------------------------------------------------------------
    def test_audit_failure_rolls_back_the_move(self):
        rec = _make_record(7, "tenant-A")
        upsert_record(self.conn, rec)
        self.conn.commit()
        token, key = self._promote_token("tenant-A")

        # Force the audit append to fail AFTER the move is staged.
        orig_append = cognition.CognitionLog.append
        def boom(self, kind, data):
            raise RuntimeError("cognition write failed")
        cognition.CognitionLog.append = boom
        try:
            with self.assertRaises(promote.PromotionError):
                promote.promote(self.conn, rec.cid, token, key,
                                stream=_STREAM, cognition_key=_AUDIT_KEY)
        finally:
            cognition.CognitionLog.append = orig_append

        self.assertEqual(self._tenant_of(rec.cid), "tenant-A",
                         "audit failure must roll the move back — no promotion without audit")
        self.assertEqual(self._audits(), [], "no audit was committed")

    # -- P6 ----------------------------------------------------------------
    def test_audit_records_cap_identity_not_secret(self):
        rec = _make_record(8, "tenant-A")
        upsert_record(self.conn, rec)
        self.conn.commit()
        token, key = self._promote_token("tenant-A")

        promote.promote(self.conn, rec.cid, token, key,
                        stream=_STREAM, cognition_key=_AUDIT_KEY)

        audit = self._audits()[0]
        self.assertEqual(audit["nonce"], token.nonce, "cap is identified by its nonce")
        blob = repr(audit)
        self.assertNotIn(key.hex(), blob, "the raw signing key never enters the audit")
        self.assertNotIn(token.sig, blob, "the token signature is not logged")


if __name__ == "__main__":
    unittest.main()
