from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_storage


class MemoryFactListPort:
    def __init__(self):
        self.initialized = False
        self.rows: dict[str, dict] = {}

    def init_global_facts(self) -> None:
        self.initialized = True

    def register_fact(self, fact_hash: str, text: str, modality: str, score: float = 0.0) -> None:
        row = self.rows.get(fact_hash)
        if row is None:
            self.rows[fact_hash] = {
                "fact_hash": fact_hash,
                "fact_text": text,
                "modality": modality,
                "seen_count": 1,
                "importance_score": score,
            }
            return
        row["seen_count"] += 1

    def lookup_fact(self, fact_hash: str) -> dict | None:
        row = self.rows.get(fact_hash)
        return dict(row) if row else None

    def close(self) -> None:
        pass


class TestCausalTape(unittest.TestCase):
    def test_same_second_appends_chain_by_sequence(self):
        with tempfile.TemporaryDirectory() as td:
            tape = lgwks_storage.CausalTape(Path(td) / "causal_tape.db", "tenant-a")
            try:
                ids = [
                    tape.append("cid-a", "cap"),
                    tape.append("cid-b", "cap"),
                    tape.append("cid-c", "cap"),
                ]
            finally:
                tape.close()

            conn = sqlite3.connect(Path(td) / "causal_tape.db")
            rows = conn.execute(
                """
                SELECT sequence, entry_hash, prev_hash, fact_cid
                FROM tape
                WHERE tenant_id = ?
                ORDER BY sequence ASC
                """,
                ("tenant-a",),
            ).fetchall()
            conn.close()

        self.assertEqual([row[0] for row in rows], [1, 2, 3])
        self.assertEqual([row[1] for row in rows], ids)
        self.assertEqual(rows[0][2], "genesis")
        self.assertEqual(rows[1][2], rows[0][1])
        self.assertEqual(rows[2][2], rows[1][1])

    def test_legacy_tape_without_sequence_is_backfilled(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "causal_tape.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE tape (
                    entry_hash TEXT PRIMARY KEY,
                    prev_hash TEXT,
                    tenant_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    fact_cid TEXT NOT NULL,
                    ciphertext BLOB,
                    meta_json TEXT,
                    timestamp REAL DEFAULT (strftime('%s', 'now'))
                );
                INSERT INTO tape
                (entry_hash, prev_hash, tenant_id, capability_id, fact_cid, meta_json, timestamp)
                VALUES
                ('a1', 'genesis', 'tenant-a', 'cap', 'cid-a', '{}', 10),
                ('a2', 'a1', 'tenant-a', 'cap', 'cid-b', '{}', 10),
                ('b1', 'genesis', 'tenant-b', 'cap', 'cid-c', '{}', 10);
                """
            )
            conn.commit()
            conn.close()

            tape = lgwks_storage.CausalTape(path, "tenant-a")
            try:
                new_id = tape.append("cid-d", "cap")
            finally:
                tape.close()

            conn = sqlite3.connect(path)
            a_rows = conn.execute(
                "SELECT sequence, entry_hash, prev_hash FROM tape WHERE tenant_id='tenant-a' ORDER BY sequence"
            ).fetchall()
            b_rows = conn.execute(
                "SELECT sequence, entry_hash, prev_hash FROM tape WHERE tenant_id='tenant-b' ORDER BY sequence"
            ).fetchall()
            conn.close()

        self.assertEqual([row[0] for row in a_rows], [1, 2, 3])
        self.assertEqual([row[1] for row in a_rows], ["a1", "a2", new_id])
        self.assertEqual(a_rows[2][2], "a2")
        self.assertEqual([row[0] for row in b_rows], [1])


class TestStorageGateConnections(unittest.TestCase):
    def test_ingest_reuses_gate_connections(self):
        with tempfile.TemporaryDirectory() as td:
            real_connect = lgwks_storage.lgwks_sqlite.connect
            with mock.patch.object(lgwks_storage.lgwks_sqlite, "connect", wraps=real_connect) as connect:
                gate = lgwks_storage.StorageGate(Path(td), tenant_id="tenant-a")
                try:
                    init_calls = connect.call_count
                    gate.ingest_fact("cid-1", "one", "text", "cap")
                    gate.ingest_fact("cid-2", "two", "text", "cap")
                    gate.ingest_fact("cid-1", "one", "text", "cap")
                    self.assertEqual(connect.call_count, init_calls)
                finally:
                    gate.close()


class TestGlobalFactListPort(unittest.TestCase):
    def test_global_fact_list_depends_on_operations_not_sql(self):
        port = MemoryFactListPort()
        facts = lgwks_storage.GlobalFactList(port)

        facts.register_fact("cid-1", "one", "text", 0.25)
        facts.register_fact("cid-1", "one", "text", 0.25)

        self.assertTrue(port.initialized)
        self.assertEqual(facts.lookup("cid-1")["seen_count"], 2)


if __name__ == "__main__":
    unittest.main()
