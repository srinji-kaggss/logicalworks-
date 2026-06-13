"""Tests for lgwks.daemon.query.v1 (#124 — unified daemon query surface).

Maps to the issue's acceptance bullets:
  1. retrieve from ≥2 existing projections in one call (transcript + graph);
  2. every hit carries provenance to a real event or artifact;
  3. freshness + trust filtering drop the right rows;
  4. deterministic ordering — same store state + request → identical hit order.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lgwks_daemon_event as de
import lgwks_query as q
from lgwks_daemon_store import DaemonEventStore

TENANT = "repo:demo"


class TestQueryFederation(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="q124_"))
        # ── projection 1: transcript (real daemon event store, #118 v2 events) ──
        self.daemon_db = self.root / "daemon-events.db"
        self.daemon_db.parent.mkdir(parents=True, exist_ok=True)
        store = DaemonEventStore(self.daemon_db)
        try:
            for i, (kind, source, trust, ts) in enumerate([
                ("human_message", "text", "human_confirmed", "2026-06-13T10:00:00+00:00"),
                ("tool_call", "model", "model_proposed", "2026-06-13T11:00:00+00:00"),
                ("human_message", "text", "human_confirmed", "2026-06-01T00:00:00+00:00"),  # stale
            ]):
                store.append(de.build_event(
                    tenant_id=TENANT, agent_id="claude", session_id="sess-1",
                    actor="human", client="claude", lane="ingress",
                    kind=kind, scope="agent_local",
                    payload={"prompt_head": f"refactor the daemon query surface {i}"},
                    source=source, trust=trust, ts=ts,
                ))
        finally:
            store.close()
        # ── projection 2: graph (real entity graph) ──
        import lgwks_entity_graph
        self.graph_db = self.root / "entity_graph.db"
        g = lgwks_entity_graph.GraphDB(self.graph_db)
        g.upsert_node("node:query", "module", "daemon query surface")
        g.upsert_node("node:other", "module", "unrelated widget")
        g.commit()
        g.close()

        self.adapters = {
            "transcript": q.transcript_adapter(self.daemon_db),
            "graph": q.graph_adapter(self.graph_db),
        }

    def _req(self, **over):
        return q.build_request(tenant=TENANT, q="daemon query", **over)

    def test_retrieves_from_two_projections(self):
        result = q.query(self._req(), self.adapters)
        self.assertEqual(result["schema"], "lgwks.daemon.query.result.v1")
        projections = {h["projection"] for h in result["hits"]}
        self.assertIn("transcript", projections)
        self.assertIn("graph", projections)

    def test_every_hit_has_provenance(self):
        for h in q.query(self._req(), self.adapters)["hits"]:
            prov = h["provenance"]
            # provenance resolves to a real event OR an artifact cid — never neither.
            self.assertTrue(prov.get("event_id") or prov.get("artifact_cid"), h)
            self.assertTrue(h["cid"].startswith("b2b256:"))

    def test_freshness_drops_stale_rows(self):
        cutoff = "2026-06-10T00:00:00+00:00"
        fresh = q.query(self._req(freshness=cutoff), self.adapters)["hits"]
        # the 2026-06-01 event is older than the cutoff and must be gone.
        stale_ts = [h for h in fresh if h.get("ts") and h["ts"] < cutoff]
        self.assertEqual(stale_ts, [])

    def test_trust_filter_keeps_only_requested_class(self):
        hits = q.query(self._req(trust="human_confirmed"), self.adapters)["hits"]
        # graph hits are trust=deterministic and the tool_call is model_proposed — all dropped.
        self.assertTrue(hits)
        self.assertTrue(all(h["trust"] == "human_confirmed" for h in hits))

    def test_source_filter(self):
        hits = q.query(self._req(source="model"), self.adapters)["hits"]
        self.assertTrue(all(h["provenance"]["source"] == "model" for h in hits))

    def test_deterministic_order(self):
        r1 = q.query(self._req(), self.adapters)["hits"]
        r2 = q.query(self._req(), self.adapters)["hits"]
        self.assertEqual([(h["cid"], h["score"]) for h in r1],
                         [(h["cid"], h["score"]) for h in r2])
        # order obeys (score desc, cid asc)
        keys = [(-h["score"], h["cid"]) for h in r1]
        self.assertEqual(keys, sorted(keys))


class TestRequestValidation(unittest.TestCase):
    def test_tenant_required(self):
        with self.assertRaises(ValueError):
            q.validate_request({"schema": "lgwks.daemon.query.v1", "q": None,
                                "filters": {}, "limit": 10, "order": "score_desc"})

    def test_bad_source_rejected(self):
        with self.assertRaises(ValueError):
            q.build_request(tenant=TENANT, source="telepathy")

    def test_bad_trust_rejected(self):
        with self.assertRaises(ValueError):
            q.build_request(tenant=TENANT, trust="vibes")

    def test_unstable_order_rejected(self):
        with self.assertRaises(ValueError):
            q.build_request(tenant=TENANT, order="random")


class TestScoreNormalisation(unittest.TestCase):
    def test_fraction_of_query_tokens(self):
        self.assertEqual(q.score_text("alpha beta", "alpha gamma"), 0.5)
        self.assertEqual(q.score_text("alpha", "alpha alpha"), 1.0)
        self.assertEqual(q.score_text(None, "anything"), 1.0)  # filter-only → 1.0


if __name__ == "__main__":
    unittest.main()
