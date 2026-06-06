from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lgwks_entity_graph as entity_graph
import lgwks_sqlite


class TestSqliteHardening(unittest.TestCase):
    def test_shared_connection_applies_pragmas(self):
        with tempfile.TemporaryDirectory() as td:
            conn = lgwks_sqlite.connect(Path(td) / "x.db")
            try:
                self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                self.assertEqual(conn.execute("PRAGMA temp_store").fetchone()[0], 2)
                self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)
            finally:
                conn.close()

    def test_graphdb_uses_hardened_connection(self):
        with tempfile.TemporaryDirectory() as td:
            db = entity_graph.GraphDB(Path(td) / "graph.db")
            try:
                self.assertEqual(db._conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(db._conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
