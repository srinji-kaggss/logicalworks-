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


if __name__ == "__main__":
    unittest.main()
