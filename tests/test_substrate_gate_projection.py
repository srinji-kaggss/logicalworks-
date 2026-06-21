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

import lgwks_artifact_tokenized as artifact_mod
import lgwks_entity_graph
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


def _graph_artifact(gate, *, tenant: str, title: str):
    """A canonical text artifact carrying a small graph on the extras sidecar."""
    art = artifact_mod.build_artifact(
        tenant_id=tenant,
        source="ingest",
        modality="text",
        tokenization_id=gate.tokenizers.default_word_regex_id(),
        token_stream=[1, 2, 3],
        payload_cid="b2b256:" + "c" * 64,
        payload_meta={"title": title},
        capability_id="cap:ingest",
        timestamp=1234567890.0,
    )
    graph = {
        "chunks": [{"chunk_id": "chunk-1", "doc_id": "doc-1", "text": "alpha beta", "schema": "PROSE"}],
        "nodes": [
            {"node_id": "ORG:acme", "type": "ORG", "label": "Acme"},
            {"node_id": "GEO:ottawa", "type": "GEO", "label": "Ottawa"},
        ],
        "edges": [{"src": "ORG:acme", "dst": "GEO:ottawa", "rel": "located_in"}],
    }
    return art, graph


class TestGraphFabricCidTierAlignment(unittest.TestCase):
    """#165 step 2 — the gate graph projection is live: graph structure carried on
    extras["graph"] is recorded with each row stamped with the artifact's cid (tape
    provenance) and tier (world ⊕ tenant ownership)."""

    def _graph_rows(self, db_path: Path):
        conn = sqlite3.connect(str(db_path))
        try:
            nodes = conn.execute("SELECT node_id, artifact_cid, tier FROM nodes ORDER BY node_id").fetchall()
            edges = conn.execute("SELECT rel, artifact_cid, tier FROM edges").fetchall()
            chunks = conn.execute("SELECT chunk_id, artifact_cid, tier FROM chunks").fetchall()
        finally:
            conn.close()
        return nodes, edges, chunks

    def test_apply_projects_graph_stamped_with_cid_and_tier(self):
        with tempfile.TemporaryDirectory() as td:
            gate = lgwks_storage.StorageGate(Path(td), tenant_id="tenant-a")
            try:
                art, graph = _graph_artifact(gate, tenant="tenant-a", title="g1")
                receipt = gate.ingest_artifact(art, extras={"graph": graph})
                # The graph projection applied and wrote chunk + 2 nodes + 1 edge.
                graph_results = [r for r in receipt.projections if r.name == "graph"]
                self.assertEqual(len(graph_results), 1)
                self.assertTrue(graph_results[0].applied)
                self.assertEqual(graph_results[0].written, 4)

                nodes, edges, chunks = self._graph_rows(gate.graph_fabric.db_path)
                # Every row carries this artifact's cid + the tenant tier.
                self.assertEqual(len(nodes), 2)
                self.assertEqual(len(edges), 1)
                self.assertEqual(len(chunks), 1)
                for _nid, acid, tier in nodes:
                    self.assertEqual(acid, art.artifact_cid)
                    self.assertEqual(tier, "tenant-a")
                self.assertEqual(edges[0][1], art.artifact_cid)
                self.assertEqual(edges[0][2], "tenant-a")
                self.assertEqual(chunks[0][1], art.artifact_cid)
                self.assertEqual(chunks[0][2], "tenant-a")
            finally:
                gate.close()

    def test_apply_inert_when_no_graph_extras(self):
        """A plain artifact (no graph sidecar) leaves the graph projection inert —
        this is why every existing ingest path is unchanged."""
        with tempfile.TemporaryDirectory() as td:
            gate = lgwks_storage.StorageGate(Path(td), tenant_id="tenant-a")
            try:
                art, _ = _graph_artifact(gate, tenant="tenant-a", title="g2")
                receipt = gate.ingest_artifact(art)  # no extras
                graph_results = [r for r in receipt.projections if r.name == "graph"]
                self.assertEqual(len(graph_results), 1)
                self.assertFalse(graph_results[0].applied)
                nodes, edges, chunks = self._graph_rows(gate.graph_fabric.db_path)
                self.assertEqual((len(nodes), len(edges), len(chunks)), (0, 0, 0))
            finally:
                gate.close()

    def test_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            gate = lgwks_storage.StorageGate(Path(td), tenant_id="tenant-a")
            try:
                art, graph = _graph_artifact(gate, tenant="tenant-a", title="g3")
                gate.ingest_artifact(art, extras={"graph": graph})
                gate.ingest_artifact(art, extras={"graph": graph})  # replay
                nodes, edges, chunks = self._graph_rows(gate.graph_fabric.db_path)
                self.assertEqual((len(nodes), len(edges), len(chunks)), (2, 1, 1))
            finally:
                gate.close()


class TestGraphCidTierMigration(unittest.TestCase):
    """#165 step 2 — graph.db files created before step 2 gain the cid/tier columns
    in place (existing rows keep NULL), so opening a legacy graph never errors."""

    def test_legacy_db_gains_columns_with_null_rows(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy_graph.db"
            # Build a pre-step-2 schema: nodes/edges/chunks WITHOUT cid/tier columns.
            conn = sqlite3.connect(str(path))
            conn.executescript(
                "CREATE TABLE nodes (node_id TEXT PRIMARY KEY, type TEXT NOT NULL, "
                "label TEXT NOT NULL, attrs TEXT NOT NULL DEFAULT '{}');"
                "CREATE TABLE edges (edge_id TEXT PRIMARY KEY, src TEXT NOT NULL, "
                "dst TEXT NOT NULL, rel TEXT NOT NULL, attrs TEXT NOT NULL DEFAULT '{}');"
                "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, "
                "url TEXT, text TEXT NOT NULL, hash TEXT NOT NULL, "
                "schema TEXT NOT NULL DEFAULT 'UNKNOWN', labels TEXT NOT NULL DEFAULT '[]');"
            )
            conn.execute("INSERT INTO nodes (node_id, type, label) VALUES ('ORG:old', 'ORG', 'Old')")
            conn.commit()
            conn.close()

            db = lgwks_entity_graph.GraphDB(path)  # migration runs in __post_init__
            try:
                cols = {r[1] for r in db._conn.execute("PRAGMA table_info(nodes)")}
                self.assertIn("artifact_cid", cols)
                self.assertIn("tier", cols)
                row = db._conn.execute(
                    "SELECT artifact_cid, tier FROM nodes WHERE node_id='ORG:old'"
                ).fetchone()
                self.assertEqual(row, (None, None))  # pre-existing rows untouched
                # New write through the migrated DB stamps cid/tier.
                db.upsert_node("ORG:new", "ORG", "New", artifact_cid="b2b256:x", tier="tenant-z")
                db.commit()
                new = db._conn.execute(
                    "SELECT artifact_cid, tier FROM nodes WHERE node_id='ORG:new'"
                ).fetchone()
                self.assertEqual(new, ("b2b256:x", "tenant-z"))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
