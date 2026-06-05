from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import lgwks_entity_graph as eg


def _rrif_edge_id(rows: list[dict]) -> str:
    for row in rows:
        if row["neighbor"] == "PLAN_TYPE:rrif":
            return row["edge_id"]
    raise AssertionError("rrif neighbor not found")


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


if __name__ == "__main__":
    unittest.main()
