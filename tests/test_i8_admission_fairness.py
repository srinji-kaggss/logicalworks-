"""Tests for lgwks_admission L3 — per-tenant admission + fair leasing (issue #89).

Maps to the L3 slice of the #89 acceptance:
  L3-1 fail_open_closed   — invalid / missing-scope cap → CapabilityError, NO token
                            consumed and NO queue slot taken.
  L3-2 no_starvation      — one tenant flooding cannot block another tenant's admits.
  L3-3 fair_leasing       — concurrent leases ≤ c and ≤ ⌈c/active⌉ per tenant; release frees.
  L3-4 per_tenant_q_max   — a tenant fills only its own queue; others unaffected.
  L3-5 idempotent_shed    — duplicate cid within a tenant → one row (preserved).
  L3-6 replayable         — injected clock + shared key → deterministic decisions.

Authority: spec/second-harness/ARCH-two-db-multitenant.md (L3); issue #89.
"""

from __future__ import annotations

import os
import secrets
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_capability import CapabilityError, issue_token, WORLD_R
from lgwks_admission import (
    TenantAdmissionGate,
    Admitted,
    Rejected429,
)


class _StepClock:
    """Injectable clock that advances by `step` on each call (mirrors test_admission)."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self._t = start
        self._step = step

    def __call__(self) -> float:
        t = self._t
        self._t += self._step
        return t


def _gate(key: bytes, **kw) -> TenantAdmissionGate:
    # Slow clock (step 0.0) so buckets do not refill mid-test unless we want them to.
    kw.setdefault("clock", _StepClock(step=0.0))
    kw.setdefault("role_count", 4)
    kw.setdefault("mu", 1.0)
    return TenantAdmissionGate(key=key, **kw)


# ---------------------------------------------------------------------------
# L3-1 — fail-open closed (capability-FIRST ordering)
# ---------------------------------------------------------------------------

class TestFailOpenClosed(unittest.TestCase):
    def test_invalid_signature_raises_and_consumes_nothing(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, burst=8.0, q_max=8)
        # Token signed with a DIFFERENT key → invalid signature.
        bad_token, _other_key = issue_token("alice")
        with self.assertRaises(CapabilityError):
            gate.admit(bad_token, cid="cid-0", item="x")
        # No lane created, nothing in flight — fail-open is structurally closed.
        self.assertEqual(gate.in_flight, 0)
        self.assertEqual(gate.tenant_in_flight("alice"), 0)

    def test_missing_tenant_rw_scope_rejected(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, burst=8.0, q_max=8)
        # Read-only token (world:r only) — lacks tenant:rw.
        ro_token, _ = issue_token("alice", key=key, scopes={WORLD_R})
        with self.assertRaises(CapabilityError):
            gate.admit(ro_token, cid="cid-0", item="x")
        self.assertEqual(gate.in_flight, 0)

    def test_lease_is_also_capability_gated(self):
        key = secrets.token_bytes(32)
        gate = _gate(key)
        forged, _ = issue_token("alice")  # wrong key
        with self.assertRaises(CapabilityError):
            gate.lease(forged)


# ---------------------------------------------------------------------------
# L3-2 — no starvation (per-tenant buckets)
# ---------------------------------------------------------------------------

class TestNoStarvation(unittest.TestCase):
    def test_flood_by_one_tenant_does_not_block_another(self):
        key = secrets.token_bytes(32)
        # burst=4 per tenant, no refill (step 0.0) → each tenant gets exactly 4 admits.
        gate = _gate(key, burst=4.0, q_max=64)
        tok_a, _ = issue_token("A", key=key)
        tok_b, _ = issue_token("B", key=key)

        a_admitted = a_rejected = 0
        for i in range(40):                       # A floods 10× its burst
            r = gate.admit(tok_a, cid=f"A-{i}", item=i)
            if isinstance(r, Admitted):
                a_admitted += 1
            else:
                self.assertIsInstance(r, Rejected429)
                a_rejected += 1

        # B still has its full independent bucket despite A's flood.
        b_admitted = sum(
            isinstance(gate.admit(tok_b, cid=f"B-{i}", item=i), Admitted)
            for i in range(4)
        )
        self.assertEqual(a_admitted, 4, "A capped at its own burst")
        self.assertGreater(a_rejected, 0, "A's flood is rate-limited")
        self.assertEqual(b_admitted, 4, "B unaffected by A's flood — no starvation")


# ---------------------------------------------------------------------------
# L3-3 — fair leasing ≤ c
# ---------------------------------------------------------------------------

class TestFairLeasing(unittest.TestCase):
    def test_total_leases_bounded_by_c(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, role_count=4)            # c is small/bounded
        c = gate._c
        tokens = [issue_token(f"t{i}", key=key)[0] for i in range(c + 3)]
        granted = sum(gate.lease(t) for t in tokens)
        self.assertLessEqual(gate.in_flight, c)
        self.assertEqual(granted, gate.in_flight)
        self.assertLessEqual(granted, c)

    def test_per_tenant_fair_ceiling(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, role_count=8)            # larger c so ceiling > 1 with 1 tenant
        tok_a, _ = issue_token("A", key=key)
        # Only A active → ceiling = c. A may take up to c, then total==c blocks.
        grants = [gate.lease(tok_a) for _ in range(gate._c + 2)]
        self.assertEqual(sum(grants), gate._c)
        self.assertEqual(gate.tenant_in_flight("A"), gate._c)

    def test_release_frees_a_slot(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, role_count=4)
        tok, _ = issue_token("A", key=key)
        while gate.lease(tok):
            pass
        full = gate.in_flight
        self.assertEqual(full, gate._c)
        gate.release(tok)
        self.assertEqual(gate.in_flight, full - 1)
        self.assertTrue(gate.lease(tok), "a freed slot is re-grantable")

    def test_release_floors_at_zero(self):
        key = secrets.token_bytes(32)
        gate = _gate(key)
        tok, _ = issue_token("A", key=key)
        gate.release(tok)                          # never leased
        self.assertEqual(gate.tenant_in_flight("A"), 0)

    def test_two_tenants_split_capacity_fairly(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, role_count=8)
        tok_a, _ = issue_token("A", key=key)
        tok_b, _ = issue_token("B", key=key)
        # Touch both so active_tenants == 2 → ceiling = ⌈c/2⌉.
        gate.lease(tok_a); gate.release(tok_a)
        gate.lease(tok_b); gate.release(tok_b)
        ceiling = gate.fair_ceiling()
        a_grants = sum(gate.lease(tok_a) for _ in range(gate._c + 2))
        self.assertEqual(a_grants, ceiling, "A capped at its fair ceiling, cannot monopolise c")
        self.assertLessEqual(gate.in_flight, gate._c)


# ---------------------------------------------------------------------------
# L3-4 — per-tenant queue bound
# ---------------------------------------------------------------------------

class TestPerTenantQueue(unittest.TestCase):
    def test_one_tenant_fills_only_its_own_queue(self):
        key = secrets.token_bytes(32)
        # Huge burst so the bucket never rejects → isolate the queue bound.
        gate = _gate(key, burst=1000.0, q_max=4)
        tok_a, _ = issue_token("A", key=key)
        tok_b, _ = issue_token("B", key=key)
        results_a = [gate.admit(tok_a, cid=f"A-{i}", item=i) for i in range(8)]
        a_full = [r for r in results_a if isinstance(r, Rejected429)]
        self.assertTrue(a_full, "A overflows its own q_max")
        self.assertEqual(a_full[0].reason, "queue_full")
        # B's queue is independent and empty.
        r_b = gate.admit(tok_b, cid="B-0", item=0)
        self.assertIsInstance(r_b, Admitted)


# ---------------------------------------------------------------------------
# L3-5 — idempotent shed preserved per tenant
# ---------------------------------------------------------------------------

class TestIdempotentShed(unittest.TestCase):
    def test_duplicate_cid_one_row(self):
        key = secrets.token_bytes(32)
        gate = _gate(key, burst=8.0, q_max=8)
        tok, _ = issue_token("A", key=key)
        r1 = gate.admit(tok, cid="dup", item="x")
        r2 = gate.admit(tok, cid="dup", item="x")
        self.assertIsInstance(r1, Admitted)
        self.assertIsInstance(r2, Admitted)          # idempotent, not an error
        _bucket, queue = gate._lane("A")
        self.assertEqual(queue.size, 1, "duplicate cid → exactly one queued row")


# ---------------------------------------------------------------------------
# L3-6 — deterministic replay
# ---------------------------------------------------------------------------

class TestReplayable(unittest.TestCase):
    def _run(self) -> list[str]:
        key = b"\x01" * 32                            # fixed key → reproducible sigs not needed
        gate = TenantAdmissionGate(
            key=key, role_count=4, mu=1.0, burst=3.0, q_max=4,
            clock=_StepClock(step=0.0),
        )
        tok, _ = issue_token("A", key=key)
        out = []
        for i in range(10):
            r = gate.admit(tok, cid=f"cid-{i}", item=i)
            out.append(type(r).__name__)
        return out

    def test_two_runs_identical(self):
        self.assertEqual(self._run(), self._run())


if __name__ == "__main__":
    unittest.main()
