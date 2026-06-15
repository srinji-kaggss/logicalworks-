"""Task #3 — substrate_run dual-write bridge.

Proves RelationalProjection.project_run reaches parity with the legacy
lgwks_substrate_db._build_index_db, is idempotent, exposes FTS, and that
GraphFabric.ingest_chunks populates the entity graph.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_storage


def _rowsets():
    source_rows = [{"source_id": "src-1", "source": "http://x", "title": "X", "discovered_by": "seed", "depth": 0}]
    doc_rows = [{"document_id": "doc-1", "source_id": "src-1", "title": "X", "source": "http://x", "word_count": 3}]
    chunk_rows = [{
        "chunk_id": "chunk-1", "document_id": "doc-1", "source": "http://x", "url": "http://x",
        "text": "alpha beta gamma", "stem_text": "alpha beta", "hash": "h1",
        "fact_score": 0.5, "chunk_kind": "prose", "position": 0,
    }]
    fact_rows = [{
        "fact_id": "fact-1", "chunk_id": "chunk-1", "document_id": "doc-1",
        "fact_text": "alpha beta", "fact_score": 0.5, "chunk_kind": "prose",
    }]
    vector_rows = [{
        "vector_id": "vec-1", "chunk_id": "chunk-1", "document_id": "doc-1",
        "provider": "deterministic", "is_semantic": False, "dims": 8,
        "vector_text": "alpha", "vector": [0.1] * 8, "fact_score": 0.5, "chunk_kind": "prose",
    }]
    frontier = [{"url": "http://x", "depth": 0, "status": "ok", "reason": "", "discovered_by": "seed", "links_found": 2}]
    return dict(source_rows=source_rows, doc_rows=doc_rows, chunk_rows=chunk_rows,
                fact_rows=fact_rows, vector_rows=vector_rows, frontier=frontier)


def _counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    out = {}
    for t in ("sources", "documents", "chunks", "facts", "vectors", "frontier", "chunk_fts", "fact_fts"):
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    conn.close()
    return out


class TestProjectRunParity(unittest.TestCase):
    def test_project_run_writes_all_tables(self):
        """The gate-owned relational projection (which replaced the deleted legacy
        _build_index_db) writes every table + FTS for a run's rowsets."""
        rs = _rowsets()  # 1 row per table
        with tempfile.TemporaryDirectory() as td:
            rp = lgwks_storage.RelationalProjection(Path(td) / "relational.db")
            try:
                rp.project_run(**rs)
            finally:
                rp.close()
            gc = _counts(Path(td) / "relational.db")
            for table in ("sources", "documents", "chunks", "facts", "vectors", "frontier", "chunk_fts", "fact_fts"):
                self.assertEqual(gc[table], 1, f"expected 1 row in {table}, got {gc[table]}")

    def test_fts_is_queryable(self):
        rs = _rowsets()
        with tempfile.TemporaryDirectory() as td:
            rp = lgwks_storage.RelationalProjection(Path(td) / "relational.db")
            try:
                rp.project_run(**rs)
                hits = rp._conn.execute("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'alpha'").fetchall()
                self.assertEqual([h[0] for h in hits], ["chunk-1"])
            finally:
                rp.close()

    def test_project_run_is_idempotent(self):
        rs = _rowsets()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "relational.db"
            rp = lgwks_storage.RelationalProjection(path)
            try:
                rp.project_run(**rs)
                rp.project_run(**rs)  # second pass must not duplicate
            finally:
                rp.close()
            c = _counts(path)
            self.assertEqual(c["chunks"], 1)
            self.assertEqual(c["chunk_fts"], 1)
            self.assertEqual(c["facts"], 1)
            self.assertEqual(c["fact_fts"], 1)
            self.assertEqual(c["vectors"], 1)
            self.assertEqual(c["frontier"], 1)


class TestGraphFabricIngest(unittest.TestCase):
    def test_ingest_chunks_populates_graph(self):
        graph_rows = [{
            "chunk_id": "chunk-1", "document_id": "doc-1", "url": "http://x",
            "text": "alpha beta gamma lgwks_storage.py", "hash": "h1", "schema": "PROSE",
        }]
        with tempfile.TemporaryDirectory() as td:
            gf = lgwks_storage.GraphFabric(Path(td) / "graph.db")
            try:
                gf.ingest_chunks(graph_rows)
                stats = gf._db.stats()
                self.assertEqual(stats["chunks"], 1)
                # idempotent re-ingest keeps chunk count stable
                gf.ingest_chunks(graph_rows)
                self.assertEqual(gf._db.stats()["chunks"], 1)
            finally:
                gf.close()


class TestGraphFabricExportResolve(unittest.TestCase):
    """#169 — exports + node resolution are sourced from the gate's cumulative
    GraphFabric (the per-run graph.db was removed; substrate_run + query --neighbors
    target the gate)."""

    def test_export_json_and_mermaid_from_cumulative_graph(self):
        rows = [{
            "chunk_id": "chunk-1", "document_id": "doc-1", "url": "http://x",
            "text": "Acme Corp filed form T2033 with the CRA.", "hash": "h1", "schema": "PROSE",
        }]
        with tempfile.TemporaryDirectory() as td:
            gf = lgwks_storage.GraphFabric(Path(td) / "graph.db")
            try:
                gf.ingest_chunks(rows)
                jpath = Path(td) / "graph.json"
                mpath = Path(td) / "graph.mmd"
                gf.export_json(jpath)
                gf.export_mermaid(mpath)
                self.assertTrue(jpath.exists() and mpath.exists())
                data = json.loads(jpath.read_text())
                self.assertEqual(set(data.keys()), {"nodes", "edges", "stats"})
                # export stats agree with the live gate stats (single source)
                self.assertEqual(data["stats"], gf.stats())
            finally:
                gf.close()

    def test_resolve_node_missing_returns_error(self):
        with tempfile.TemporaryDirectory() as td:
            gf = lgwks_storage.GraphFabric(Path(td) / "graph.db")
            try:
                node, err = gf.resolve_node("does-not-exist")
                self.assertIsNone(node)
                self.assertIn("no node matches", err or "")
            finally:
                gf.close()


if __name__ == "__main__":
    unittest.main()
