from __future__ import annotations

import unittest

import lgwks_project_artifacts as artifacts


def _record(**overrides) -> dict:
    base = {
        "schema": artifacts.BOT_RECORD_SCHEMA,
        "run_id": "run:2026-06-06:abc123",
        "bot": "graph_anomaly",
        "target": {"kind": "file", "id": "lgwks_substrate.py"},
        "kind": "hub_risk",
        "summary": "high-betweenness transit hub with broad blast radius",
        "severity": "medium",
        "confidence": 0.88,
        "status": "open",
        "evidence": [{"type": "metric", "name": "betweenness", "value": 0.7, "unit": "score"}],
        "links": {
            "repo": "/Users/srinji/logicalworks-",
            "file": "lgwks_substrate.py",
            "symbol": None,
            "tests": ["tests/test_substrate.py"],
            "artifacts": ["runs/graph/current.json"],
        },
        "world_refs": [{"kind": "concept", "id": "hub-module"}],
        "tags": ["graph", "blast-radius"],
        "created_at": "2026-06-06T12:00:00Z",
    }
    base.update(overrides)
    return base


class TestBotReducer(unittest.TestCase):
    def test_duplicate_findings_collapse_deterministically(self):
        a = _record()
        b = _record(bot="optimizer", confidence=0.92, tags=["graph", "optimization"])
        reduced = artifacts.reduce_bot_records([a, b])
        findings = reduced["findings_normalized"]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(sorted(finding["contributing_bots"]), ["graph_anomaly", "optimizer"])
        self.assertEqual(finding["confidence"], 0.92)
        self.assertIn("optimization", finding["tags"])

    def test_clusters_and_review_packet_are_stable(self):
        reduced1 = artifacts.reduce_bot_records([_record()])
        reduced2 = artifacts.reduce_bot_records([_record()])
        self.assertEqual(reduced1["clusters"], reduced2["clusters"])
        packet = reduced1["review_packet"]
        self.assertTrue(packet["top_findings"])
        self.assertTrue(packet["recommended_next_reads"])
        self.assertTrue(packet["recommended_next_commands"])

    def test_anomaly_cards_have_drilldown_links(self):
        reduced = artifacts.reduce_bot_records([_record()])
        card = reduced["anomaly_cards"][0]
        self.assertEqual(card["drilldown_links"]["file"], "lgwks_substrate.py")


if __name__ == "__main__":
    unittest.main()
