"""Tests for lgwks_capability — I8 capability-token tenant isolation (T1–T5).

All tests map to acceptance clauses from PLANS-NEXT-4.md §PACKET I8
(authority: INGESTION-LAYER §6 tenant isolation).

  T1: token_required   — query without valid token → CapabilityError (not served, not partial).
  T2: tenant_isolation — 10⁴ randomised A/B cross-tenant queries leak zero cross-tenant cids.
  T3: valid_token      — issue + validate round-trip succeeds.
  T4: forged_token     — mutated token signature → validation fails.
  T5: filter_boundary  — make_tenant_filter drops records from wrong tenant.
"""

from __future__ import annotations

import os
import random
import secrets
import sys
import unittest
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_capability
from lgwks_capability import (
    SCHEMA,
    CapabilityToken,
    CapabilityError,
    issue_token,
    validate,
    guard,
    make_tenant_filter,
)


# ---------------------------------------------------------------------------
# Synthetic record fixture
# ---------------------------------------------------------------------------

@dataclass
class _FakeRecord:
    cid: str
    tenant: str


def _make_store(tenant: str, n: int = 10) -> list[_FakeRecord]:
    return [_FakeRecord(cid=f"cid-{tenant}-{i:04d}", tenant=tenant) for i in range(n)]


# ---------------------------------------------------------------------------
# T1 — token required
# ---------------------------------------------------------------------------

class TestTokenRequired(unittest.TestCase):
    """T1: a query without a valid token is rejected (CapabilityError), never partial."""

    def test_guard_valid_token_succeeds(self):
        """T1: valid token with correct key → guard passes and returns query result."""
        token, key = issue_token("alice")
        result = guard(token, lambda t: f"data-for-{t}", key)
        self.assertEqual(result, "data-for-alice", "T1: valid token with key must succeed")

    def test_guard_wrong_key_raises(self):
        token, _good_key = issue_token("alice")
        bad_key = secrets.token_bytes(32)
        with self.assertRaises(CapabilityError, msg="T1: wrong key must raise CapabilityError"):
            guard(token, lambda t: f"data-{t}", bad_key)

    def test_guard_empty_tenant_raises(self):
        # Empty tenant is caught before signature validation — pass any key bytes.
        dummy_key = secrets.token_bytes(32)
        token = CapabilityToken(tenant="", nonce="aaa", sig="bbb")
        with self.assertRaises(CapabilityError, msg="T1: empty tenant must raise CapabilityError"):
            guard(token, lambda t: t, dummy_key)

    def test_issue_empty_tenant_raises(self):
        with self.assertRaises(ValueError, msg="T1: issuing token for empty tenant must raise"):
            issue_token("")


# ---------------------------------------------------------------------------
# T2 — tenant isolation (10⁴ randomised A/B queries leak zero cross-tenant cids)
# ---------------------------------------------------------------------------

class TestTenantIsolation(unittest.TestCase):
    """T2: 10⁴ randomised cross-tenant queries → zero leaked cids."""

    N_QUERIES = 10_000

    def test_no_cross_tenant_leak(self):
        store_a = _make_store("tenant-A", n=50)
        store_b = _make_store("tenant-B", n=50)
        combined = store_a + store_b

        cids_a = {r.cid for r in store_a}
        cids_b = {r.cid for r in store_b}

        token_a, key_a = issue_token("tenant-A")
        token_b, key_b = issue_token("tenant-B")
        filter_a = make_tenant_filter(token_a)
        filter_b = make_tenant_filter(token_b)

        rng = random.Random(42)
        for _ in range(self.N_QUERIES):
            which = rng.choice(["a", "b"])
            if which == "a":
                result = filter_a(combined)
                for rec in result:
                    self.assertIn(rec.cid, cids_a,
                                  msg="T2: tenant-A filter must never return tenant-B cid")
                    self.assertNotIn(rec.cid, cids_b,
                                     msg="T2: cross-tenant leak detected for tenant-A query")
            else:
                result = filter_b(combined)
                for rec in result:
                    self.assertIn(rec.cid, cids_b,
                                  msg="T2: tenant-B filter must never return tenant-A cid")
                    self.assertNotIn(rec.cid, cids_a,
                                     msg="T2: cross-tenant leak detected for tenant-B query")


# ---------------------------------------------------------------------------
# T3 — valid token round-trip
# ---------------------------------------------------------------------------

class TestValidToken(unittest.TestCase):
    """T3: issue + validate round-trip succeeds; re-issue with same key also validates."""

    def test_valid_token_validates(self):
        token, key = issue_token("project-x")
        self.assertTrue(validate(token, key), "T3: fresh token must validate with its own key")
        self.assertEqual(token.schema, SCHEMA, "T3: token schema must match SCHEMA")
        self.assertEqual(token.tenant, "project-x", "T3: token tenant must match issued tenant")
        self.assertTrue(token.nonce, "T3: nonce must be non-empty")

    def test_different_keys_cross_validate_fails(self):
        token, key_a = issue_token("t1")
        _, key_b = issue_token("t2")
        self.assertFalse(validate(token, key_b), "T3: token must not validate with a different key")


# ---------------------------------------------------------------------------
# T4 — forged token
# ---------------------------------------------------------------------------

class TestForgedToken(unittest.TestCase):
    """T4: mutated tenant, nonce, or sig → validation fails."""

    def test_mutated_tenant(self):
        token, key = issue_token("real-tenant")
        forged = CapabilityToken(tenant="evil-tenant", nonce=token.nonce, sig=token.sig)
        self.assertFalse(validate(forged, key), "T4: mutated tenant must fail validation")

    def test_mutated_nonce(self):
        token, key = issue_token("real-tenant")
        forged = CapabilityToken(tenant=token.tenant, nonce="ffffffff", sig=token.sig)
        self.assertFalse(validate(forged, key), "T4: mutated nonce must fail validation")

    def test_mutated_sig(self):
        token, key = issue_token("real-tenant")
        forged = CapabilityToken(tenant=token.tenant, nonce=token.nonce, sig="deadbeef" * 8)
        self.assertFalse(validate(forged, key), "T4: mutated sig must fail validation")


# ---------------------------------------------------------------------------
# T5 — filter boundary
# ---------------------------------------------------------------------------

class TestFilterBoundary(unittest.TestCase):
    """T5: make_tenant_filter drops all records from wrong tenant, keeps own."""

    def test_filter_correct_tenant(self):
        token, _ = issue_token("alice")
        f = make_tenant_filter(token)
        mixed = _make_store("alice", 5) + _make_store("bob", 5)
        result = f(mixed)
        self.assertEqual(len(result), 5, "T5: filter must return only alice's records")
        for rec in result:
            self.assertEqual(rec.tenant, "alice", "T5: all returned records must be alice's")

    def test_filter_empty_store(self):
        token, _ = issue_token("alice")
        f = make_tenant_filter(token)
        result = f([])
        self.assertEqual(result, [], "T5: filter on empty store returns empty list")

    def test_filter_no_matching_tenant(self):
        token, _ = issue_token("alice")
        f = make_tenant_filter(token)
        result = f(_make_store("bob", 10))
        self.assertEqual(result, [], "T5: no matching tenant → empty result (zero leak)")


if __name__ == "__main__":
    unittest.main()
