"""Acceptance tests for I8 — basic tenant isolation + WAL concurrency.

Covers the 'basically working' scope from PLANS-NEXT-5.md:
  T1. query_for_tenant returns own + world rows, never another tenant's standard rows.
  T2. Two concurrent writers via WAL-backed store don't corrupt or lose data.
  T3. world rows (tenant='world') visible to every tenant.
  T4. tenant='' (default/unset) only sees world rows when querying as ''.
"""

from __future__ import annotations

import math
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_vector as vmod
from lgwks_vector import (
    WORLD_TENANT,
    create_store,
    encode_record,
    query_for_tenant,
    store_count,
    upsert_record,
)


def _make_record(idx: int, tenant: str, space_id: str = "test:d4") -> vmod.VectorRecord:
    floats = [float(idx % 4 + 1), 0.0, 0.0, 0.0]
    return encode_record(
        floats,
        modality="text",
        space_id=space_id,
        tenant=tenant,
        source_cid=f"src-{idx}-{tenant}",
    )


def _mem_store() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(vmod.VECTOR_RECORDS_DDL)
    conn.commit()
    return conn


class TestTenantIsolation(unittest.TestCase):

    def test_tenant_sees_own_and_world_not_other(self):
        """T1: query_for_tenant(A) returns A-rows and world-rows, never B-rows."""
        conn = _mem_store()
        rec_a = _make_record(1, "tenant-A")
        rec_b = _make_record(2, "tenant-B")
        rec_w = _make_record(3, WORLD_TENANT)
        for r in (rec_a, rec_b, rec_w):
            upsert_record(conn, r)

        result = query_for_tenant(conn, "tenant-A")
        cids = {r.cid for r in result}

        self.assertIn(rec_a.cid, cids, "own row must be present")
        self.assertIn(rec_w.cid, cids, "world row must be present")
        self.assertNotIn(rec_b.cid, cids, "other tenant's row must NOT be present")

    def test_world_rows_visible_to_all_tenants(self):
        """T3: world rows are returned for every tenant query."""
        conn = _mem_store()
        rec_w = _make_record(10, WORLD_TENANT)
        upsert_record(conn, rec_w)

        for tenant in ("alpha", "beta", "gamma"):
            result = query_for_tenant(conn, tenant)
            cids = {r.cid for r in result}
            self.assertIn(rec_w.cid, cids, f"world row missing for tenant={tenant!r}")

    def test_space_id_filter_respected(self):
        """query_for_tenant with space_id only returns rows in that space."""
        conn = _mem_store()
        rec_s1 = _make_record(20, "tenant-A", space_id="space1:d4")
        rec_s2 = _make_record(21, "tenant-A", space_id="space2:d4")
        rec_world_s1 = _make_record(22, WORLD_TENANT, space_id="space1:d4")
        for r in (rec_s1, rec_s2, rec_world_s1):
            upsert_record(conn, r)

        result = query_for_tenant(conn, "tenant-A", space_id="space1:d4")
        cids = {r.cid for r in result}
        self.assertIn(rec_s1.cid, cids)
        self.assertIn(rec_world_s1.cid, cids)
        self.assertNotIn(rec_s2.cid, cids, "wrong-space row must be excluded")

    def test_empty_tenant_sees_only_world(self):
        """T4: unset tenant ('') only sees world rows, not named-tenant rows."""
        conn = _mem_store()
        rec_named = _make_record(30, "tenant-X")
        rec_world = _make_record(31, WORLD_TENANT)
        for r in (rec_named, rec_world):
            upsert_record(conn, r)

        result = query_for_tenant(conn, "")
        cids = {r.cid for r in result}
        self.assertNotIn(rec_named.cid, cids)
        self.assertIn(rec_world.cid, cids)


class TestWALConcurrency(unittest.TestCase):

    def test_concurrent_writers_no_corruption(self):
        """T2: two threads writing to a WAL-backed on-disk store produce no lost rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn0 = create_store(db_path)
            conn0.close()

            errors: list[Exception] = []
            rows_per_thread = 20

            def writer(thread_idx: int) -> None:
                try:
                    import lgwks_sqlite
                    conn = lgwks_sqlite.connect(db_path)
                except ImportError:
                    conn = sqlite3.connect(str(db_path))
                    conn.execute("PRAGMA journal_mode=WAL")
                try:
                    for i in range(rows_per_thread):
                        rec = _make_record(thread_idx * 100 + i, f"t{thread_idx}")
                        upsert_record(conn, rec)
                    conn.commit()
                except Exception as exc:
                    errors.append(exc)
                finally:
                    conn.close()

            threads = [threading.Thread(target=writer, args=(t,)) for t in range(2)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()

            self.assertEqual([], errors, f"writer errors: {errors}")

            verify_conn = create_store(db_path)
            total = store_count(verify_conn)
            verify_conn.close()
            self.assertEqual(
                total,
                2 * rows_per_thread,
                f"expected {2 * rows_per_thread} rows, got {total} (data loss under concurrency)",
            )


if __name__ == "__main__":
    unittest.main()
