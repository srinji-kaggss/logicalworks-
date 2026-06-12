"""Tests for lgwks_admission_store — I8-hardening L4 durable cross-process queue (#89).

Maps to the L4 slice of #89 acceptance:
  L4-1 crash_durable     — rows survive close/reopen of the DB.
  L4-2 backpressure      — at q_max → Rejected429(queue_full); nothing dropped.
  L4-3 idempotent        — duplicate (tenant, cid) → exactly one row.
  L4-4 capability_gated  — bad/missing cap → CapabilityError, no row touched (§1-INV).
  L4-5 fair_leasing      — total leased ≤ c, per-tenant ceiling ⌈c/active⌉; complete frees a slot.
  L4-6 reap_crash        — a lease past its deadline is reclaimed → queued, retry_count++.
  L4-7 cross_process     — two connections to one DB share the lease COUNT (≤ c across "processes").

Authority: spec/second-harness/ARCH-two-db-multitenant.md (L4); issue #89.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_capability import CapabilityError, issue_token, WORLD_R
from lgwks_admission import Admitted, Rejected429, TenantAdmissionGate
from lgwks_admission_store import DurableAdmissionQueue


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "admission.db"
        self.key = secrets.token_bytes(32)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _q(self, **kw) -> DurableAdmissionQueue:
        kw.setdefault("role_count", 4)
        kw.setdefault("q_max", 8)
        return DurableAdmissionQueue(self.path, key=self.key, **kw)

    def _tok(self, tenant: str):
        return issue_token(tenant, key=self.key)[0]


# ---------------------------------------------------------------------------
# L4-1 — crash durability
# ---------------------------------------------------------------------------

class TestCrashDurable(_Base):
    def test_rows_survive_reopen(self):
        q = self._q()
        tok = self._tok("alice")
        self.assertIsInstance(q.enqueue(tok, cid="c1", item={"ref": 1}, now=1.0), Admitted)
        self.assertIsInstance(q.enqueue(tok, cid="c2", item={"ref": 2}, now=2.0), Admitted)
        q.close()
        # Reopen a fresh handle on the same file — durable WAL state.
        q2 = self._q()
        self.assertEqual(q2.depth("alice"), 2)
        leased = q2.lease(tok, owner="w1", now=3.0)
        self.assertEqual(leased[0], "c1")             # FIFO by enqueued_at
        self.assertEqual(leased[1], {"ref": 1})       # item round-trips through JSON
        q2.close()


# ---------------------------------------------------------------------------
# L4-2 / L4-3 — backpressure (not drop) + idempotent shed
# ---------------------------------------------------------------------------

class TestBackpressureIdempotent(_Base):
    def test_queue_full_is_backpressure_not_drop(self):
        q = self._q(q_max=3)
        tok = self._tok("alice")
        for i in range(3):
            self.assertIsInstance(q.enqueue(tok, cid=f"c{i}", now=float(i)), Admitted)
        r = q.enqueue(tok, cid="overflow", now=9.0)
        self.assertIsInstance(r, Rejected429)
        self.assertEqual(r.reason, "queue_full")
        self.assertEqual(q.depth("alice"), 3, "no drop — existing rows intact")
        # the rejected cid was NOT persisted
        self.assertEqual(q.leased_count("alice"), 0)
        q.close()

    def test_duplicate_cid_one_row(self):
        q = self._q()
        tok = self._tok("alice")
        self.assertIsInstance(q.enqueue(tok, cid="dup", now=1.0), Admitted)
        self.assertIsInstance(q.enqueue(tok, cid="dup", now=2.0), Admitted)  # idempotent
        self.assertEqual(q.depth("alice"), 1)
        q.close()


# ---------------------------------------------------------------------------
# L4-4 — capability-gated (§1-INV)
# ---------------------------------------------------------------------------

class TestCapabilityGated(_Base):
    def test_invalid_cap_raises_and_writes_nothing(self):
        q = self._q()
        forged, _other = issue_token("alice")          # signed with a DIFFERENT key
        with self.assertRaises(CapabilityError):
            q.enqueue(forged, cid="c1", now=1.0)
        self.assertEqual(q.depth("alice"), 0)
        q.close()

    def test_read_only_scope_cannot_enqueue(self):
        q = self._q()
        ro = issue_token("alice", key=self.key, scopes={WORLD_R})[0]
        with self.assertRaises(CapabilityError):
            q.enqueue(ro, cid="c1", now=1.0)
        q.close()

    def test_tenant_cannot_lease_another_tenants_rows(self):
        q = self._q()
        a, b = self._tok("A"), self._tok("B")
        q.enqueue(a, cid="a1", now=1.0)
        # B leases against its own (empty) lane — never sees A's row.
        self.assertIsNone(q.lease(b, owner="wb", now=2.0))
        self.assertEqual(q.leased_count("A"), 0)
        q.close()


# ---------------------------------------------------------------------------
# L4-5 — fair leasing ≤ c + complete frees a slot
# ---------------------------------------------------------------------------

class TestFairLeasing(_Base):
    def test_total_leased_bounded_by_c(self):
        q = self._q(role_count=2)                       # small c
        c = q._c
        toks = [self._tok(f"t{i}") for i in range(c + 3)]
        for i, t in enumerate(toks):
            q.enqueue(t, cid=f"c{i}", now=float(i))
        leased = 0
        for i, t in enumerate(toks):
            if q.lease(t, owner=f"w{i}", now=100.0 + i) is not None:
                leased += 1
        self.assertLessEqual(q.leased_count(), c)
        self.assertEqual(leased, q.leased_count())
        q.close()

    def test_complete_frees_a_slot(self):
        q = self._q(role_count=1)                        # c == 1 → exactly one lease at a time
        self.assertEqual(q._c, 1)
        a, b = self._tok("A"), self._tok("B")
        q.enqueue(a, cid="a1", now=1.0)
        q.enqueue(b, cid="b1", now=2.0)
        first = q.lease(a, owner="wa", now=3.0)
        self.assertIsNotNone(first)
        self.assertIsNone(q.lease(b, owner="wb", now=4.0), "at capacity c=1")
        self.assertTrue(q.complete(a, cid="a1"))
        self.assertIsNotNone(q.lease(b, owner="wb", now=5.0), "freed slot re-grantable")
        q.close()


# ---------------------------------------------------------------------------
# L4-6 — reap stale leases (crash durability)
# ---------------------------------------------------------------------------

class TestReap(_Base):
    def test_stale_lease_reclaimed(self):
        q = self._q(role_count=1)
        tok = self._tok("alice")
        q.enqueue(tok, cid="c1", now=1.0)
        q.lease(tok, owner="dead-worker", now=10.0, ttl=5.0)   # deadline = 15.0
        self.assertEqual(q.leased_count("alice"), 1)
        self.assertEqual(q.reap(now=12.0), 0, "not yet past deadline")
        self.assertEqual(q.reap(now=20.0), 1, "past deadline → reclaimed")
        self.assertEqual(q.leased_count("alice"), 0)
        self.assertEqual(q.depth("alice"), 1, "back to queued, not lost")
        # retry_count bumped
        row = q._conn.execute(
            "SELECT state, retry_count FROM admission_queue WHERE tenant='alice' AND cid='c1'"
        ).fetchone()
        self.assertEqual(row[0], "queued")
        self.assertEqual(row[1], 1)
        q.close()


# ---------------------------------------------------------------------------
# L4-7 — cross-process lease accounting
# ---------------------------------------------------------------------------

class TestCrossProcess(_Base):
    def test_two_connections_share_lease_count(self):
        # Two handles on the SAME db file = two processes.
        q1 = self._q(role_count=1)                       # c == 1 globally
        q2 = self._q(role_count=1)
        a, b = self._tok("A"), self._tok("B")
        q1.enqueue(a, cid="a1", now=1.0)
        q2.enqueue(b, cid="b1", now=2.0)
        leased_1 = q1.lease(a, owner="p1", now=3.0)
        self.assertIsNotNone(leased_1)
        # q2 (other "process") sees the lease and is blocked by the shared c=1 cap.
        self.assertIsNone(q2.lease(b, owner="p2", now=4.0), "global c respected across processes")
        self.assertEqual(q2.leased_count(), 1)
        q1.close(); q2.close()


# ---------------------------------------------------------------------------
# L4-8 — TenantAdmissionGate(store_path=...) opt-in wiring
# ---------------------------------------------------------------------------

class TestGateDelegation(_Base):
    def test_gate_admit_persists_durably(self):
        # store_path set → the gate's per-process bucket still rate-limits, but the
        # queue is the durable store; gate.store is the daemon's lease handle.
        gate = TenantAdmissionGate(
            key=self.key, role_count=4, burst=100.0, q_max=8, store_path=self.path,
        )
        self.assertIsNotNone(gate.store)
        tok = self._tok("alice")
        r = gate.admit(tok, cid="g1", item={"ref": 7})
        self.assertIsInstance(r, Admitted)
        # Visible to an independent durable handle on the same file → it was persisted.
        other = self._q()
        self.assertEqual(other.depth("alice"), 1)
        leased = gate.store.lease(tok, owner="w1", now=50.0)
        self.assertEqual(leased, ("g1", {"ref": 7}))
        gate.store.close()
        other.close()

    def test_gate_without_store_stays_in_memory(self):
        gate = TenantAdmissionGate(key=self.key, role_count=4, burst=8.0, q_max=8)
        self.assertIsNone(gate.store)
        self.assertIsInstance(gate.admit(self._tok("alice"), cid="m1"), Admitted)


if __name__ == "__main__":
    unittest.main()
