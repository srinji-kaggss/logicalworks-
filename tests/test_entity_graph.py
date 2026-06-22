from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from lgwks_crdt import JsonFileSink, reconverge
import lgwks_entity_graph as eg


def _rrif_edge_id(rows: list[dict]) -> str:
    for row in rows:
        if row["neighbor"] == "PLAN_TYPE:rrif":
            return row["edge_id"]
    raise AssertionError("rrif neighbor not found")


def _edge_id(src: str, dst: str, rel: str) -> str:
    return hashlib.sha256(f"{src}|{dst}|{rel}".encode()).hexdigest()[:16]


class TestEntityGraphQueries(unittest.TestCase):
    def _seed_graph(self, tmp_path: Path):
        db = eg.GraphDB(tmp_path / "graph.db")
        db.upsert_node("PLAN_TYPE:rrsp", "PLAN_TYPE", "RRSP")
        db.upsert_node("PLAN_TYPE:rrif", "PLAN_TYPE", "RRIF")
        db.upsert_node("FORM:t2033", "FORM", "T2033")
        db.upsert_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer", {"version": "Current"})
        db.upsert_edge("PLAN_TYPE:rrsp", "FORM:t2033", "requires_form", {"version": "Current"})
        db.commit()
        return db

    def test_query_nodes_match_and_type(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed_graph(Path(td))
            rows = db.query_nodes(node_type="PLAN_TYPE", match="rri")
            self.assertEqual([row["node_id"] for row in rows], ["PLAN_TYPE:rrif"])
            db.close()

    def test_neighbors_and_path(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed_graph(Path(td))
            neighbors = db.neighbors("PLAN_TYPE:rrsp", direction="out")
            self.assertEqual({row["neighbor"] for row in neighbors}, {"PLAN_TYPE:rrif", "FORM:t2033"})
            path = db.shortest_path("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif")
            self.assertEqual(path, [{
                "src": "PLAN_TYPE:rrsp",
                "dst": "PLAN_TYPE:rrif",
                "rel": "allows_transfer",
                "edge_id": _rrif_edge_id(neighbors),
            }])
            db.close()

    def test_entity_graph_command_neighbors_json(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed_graph(Path(td))
            db.close()

            class Args:
                db = str(Path(td) / "graph.db")
                chunks = None
                export = None
                mermaid = None
                stats = False
                nodes = False
                edges = False
                node_type = None
                rel = None
                match = None
                neighbors = "RRSP"
                direction = "out"
                path = None
                max_depth = 6
                limit = 20
                json = True
                sync = False
                sync_repo = "."

            from io import StringIO
            import contextlib

            buf = StringIO()
            with contextlib.redirect_stdout(buf):
                eg._entity_graph_command(Args())
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["schema"], "lgwks.entity-graph.neighbors.v0")
            self.assertEqual(payload["node"]["node_id"], "PLAN_TYPE:rrsp")
            self.assertEqual({row["neighbor"] for row in payload["neighbors"]}, {"PLAN_TYPE:rrif", "FORM:t2033"})

    def test_edge_membership_remove_then_readd_is_visible(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed_graph(Path(td))
            db.remove_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer")
            self.assertEqual(
                {row["neighbor"] for row in db.neighbors("PLAN_TYPE:rrsp", direction="out")},
                {"FORM:t2033"},
            )
            db.upsert_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer", {"version": "Current"})
            self.assertEqual(
                {row["neighbor"] for row in db.neighbors("PLAN_TYPE:rrsp", direction="out")},
                {"PLAN_TYPE:rrif", "FORM:t2033"},
            )
            db.close()

    def test_membership_sidecar_fails_closed_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed_graph(Path(td))
            db.remove_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer")
            db.remove_edge("PLAN_TYPE:rrsp", "FORM:t2033", "requires_form")
            self.assertEqual(db.query_edges(), [])
            db.close()

    def test_edge_membership_add_wins_across_divergent_replicas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target_edge = _edge_id("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer")
            db_a = self._seed_graph(root / "a")
            db_b = self._seed_graph(root / "b")
            db_a.remove_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer")
            db_b.upsert_edge("PLAN_TYPE:rrsp", "PLAN_TYPE:rrif", "allows_transfer", {"version": "Current"})
            db_a.commit()
            db_b.commit()
            db_a.close()
            db_b.close()

            sidecar_a = JsonFileSink(root / "a" / "graph.db.crdt.json").load()
            sidecar_b = JsonFileSink(root / "b" / "graph.db.crdt.json").load()

            order1 = root / "order1.json"
            reconverge(JsonFileSink(order1), sidecar_a)
            merged_1 = reconverge(JsonFileSink(order1), sidecar_b)

            order2 = root / "order2.json"
            reconverge(JsonFileSink(order2), sidecar_b)
            merged_2 = reconverge(JsonFileSink(order2), sidecar_a)

            self.assertEqual(merged_1["edges"].value(), merged_2["edges"].value())
            self.assertIn(
                target_edge,
                merged_1["edges"].value(),
                "OR-Set add-wins: concurrent re-add must survive the remove across replicas",
            )


class TestGraphTierScoping(unittest.TestCase):
    """#275: read-side world ⊕ tenant enforcement on the entity graph.

    Writes already stamp `tier` (#165 step 2). These tests lock the read side: a
    caller scoped to tenant A sees A's rows ⊕ world ⊕ pre-enforcement NULL rows, but
    never another tenant's (B's) rows. scope_tier=None stays unrestricted (admin).
    """

    def _seed(self, tmp_path: Path):
        db = eg.GraphDB(tmp_path / "graph.db")
        db.upsert_node("N:a", "doc", "alpha", tier="tenant-A")
        db.upsert_node("N:b", "doc", "bravo", tier="tenant-B")
        db.upsert_node("N:w", "doc", "world-node", tier="world")
        db.upsert_node("N:legacy", "doc", "legacy", tier=None)  # pre-enforcement
        db.upsert_edge("N:a", "N:w", "rel", tier="tenant-A")
        db.upsert_edge("N:b", "N:w", "rel", tier="tenant-B")
        db.commit()
        return db

    def test_query_nodes_scoped_excludes_other_tenant(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed(Path(td))
            ids = {n["node_id"] for n in db.query_nodes(scope_tier="tenant-A")}
            self.assertIn("N:a", ids)          # own tier
            self.assertIn("N:w", ids)          # world readable by all
            self.assertIn("N:legacy", ids)     # NULL legacy treated as shared
            self.assertNotIn("N:b", ids)       # other tenant: REFUSED
            db.close()

    def test_query_nodes_scope_none_is_unrestricted(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed(Path(td))
            ids = {n["node_id"] for n in db.query_nodes(scope_tier=None)}
            self.assertEqual(ids, {"N:a", "N:b", "N:w", "N:legacy"})
            db.close()

    def test_neighbors_scoped_excludes_other_tenant_edges(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed(Path(td))
            # From the world node, tenant A must not see tenant B's edge into it.
            srcs_a = {e["neighbor"] for e in db.neighbors("N:w", scope_tier="tenant-A")}
            self.assertIn("N:a", srcs_a)
            self.assertNotIn("N:b", srcs_a)
            srcs_all = {e["neighbor"] for e in db.neighbors("N:w", scope_tier=None)}
            self.assertEqual(srcs_all, {"N:a", "N:b"})
            db.close()

    def test_resolve_nodes_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed(Path(td))
            # "bravo" is tenant B's node — invisible to tenant A.
            self.assertEqual(db.resolve_nodes("bravo", scope_tier="tenant-A"), [])
            self.assertTrue(db.resolve_nodes("bravo", scope_tier="tenant-B"))
            self.assertTrue(db.resolve_nodes("bravo", scope_tier=None))
            db.close()

    def test_stats_scoped_counts_visible_only(self):
        with tempfile.TemporaryDirectory() as td:
            db = self._seed(Path(td))
            # tenant-A sees N:a, N:w, N:legacy = 3 nodes; B's node excluded.
            self.assertEqual(db.stats(scope_tier="tenant-A")["nodes"], 3)
            self.assertEqual(db.stats(scope_tier=None)["nodes"], 4)
            db.close()


class TestPerRowProvenance(unittest.TestCase):
    """#275 part 2: each chunk's graph rows carry its OWN artifact_cid (its tape fact
    cid), not a single last-writer cid for the whole batch. Mirrors the substrate
    producer, which now sets artifact_cid=chunk_id on every graph_input_row."""

    def test_ingest_chunks_stamps_per_chunk_artifact_cid(self):
        with tempfile.TemporaryDirectory() as td:
            db = eg.GraphDB(Path(td) / "graph.db")
            chunks = [
                {"chunk_id": "chunk-aaa", "artifact_cid": "chunk-aaa",
                 "document_id": "doc1", "text": "alpha content", "hash": "h1", "schema": "TEXT"},
                {"chunk_id": "chunk-bbb", "artifact_cid": "chunk-bbb",
                 "document_id": "doc2", "text": "bravo content", "hash": "h2", "schema": "TEXT"},
            ]
            # No batch-level artifact_cid: per-row keys must win.
            eg.ingest_chunks(db, chunks, tier="tenant-A")
            acids = dict(db._conn.execute("SELECT chunk_id, artifact_cid FROM chunks").fetchall())
            self.assertEqual(acids["chunk-aaa"], "chunk-aaa")
            self.assertEqual(acids["chunk-bbb"], "chunk-bbb")
            # Distinct per row — not collapsed to one batch cid.
            self.assertNotEqual(acids["chunk-aaa"], acids["chunk-bbb"])
            db.close()


class TestGateGraphScoping(unittest.TestCase):
    """#275: the StorageGate-owned GraphFabric scopes reads to the gate's tenant."""

    def test_gate_graph_fabric_enforces_tenant(self):
        import lgwks_storage as storage
        with tempfile.TemporaryDirectory() as td:
            # One graph.db holding two tenants' rows + a world row.
            db = eg.GraphDB(Path(td) / "graph.db")
            db.upsert_node("N:a", "doc", "alpha", tier="tenant-A")
            db.upsert_node("N:b", "doc", "bravo", tier="tenant-B")
            db.upsert_node("N:w", "doc", "shared", tier="world")
            db.commit()
            db.close()

            gate_a = storage.GraphFabric(Path(td) / "graph.db", scope_tier="tenant-A")
            ids = {n["node_id"] for n in gate_a._db.query_nodes(scope_tier=gate_a.scope_tier)}
            self.assertEqual(ids, {"N:a", "N:w"})
            # resolve_node (the gate read wrapper) refuses the other tenant's node.
            node, err = gate_a.resolve_node("bravo")
            self.assertIsNone(node)
            self.assertIsNotNone(err)
            gate_a.close()


if __name__ == "__main__":
    unittest.main()
