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
            "symbol": "build_substrate",
            "tests": ["tests/test_substrate.py"],
            "artifacts": ["runs/graph/current.json"],
        },
        "world_refs": [{"kind": "concept", "id": "hub-module"}],
        "tags": ["graph", "blast-radius"],
        "created_at": "2026-06-06T12:00:00Z",
    }
    base.update(overrides)
    return base


class TestArtifactStrength(unittest.TestCase):
    def _built(self):
        reduced = artifacts.reduce_bot_records([_record()])
        built = artifacts.build_jepa_package(
            reduced,
            repo="/Users/srinji/logicalworks-",
            plan_id="plan:lgwks-self-review",
            world_db_bindings=["wdb:concept:hub-module"],
            prior_package_refs=[],
        )
        return reduced, built

    def test_strength_passes_for_actionable_package(self):
        reduced, built = self._built()
        verdict = artifacts.evaluate_artifact_strength(
            reduced["review_packet"],
            built["package"],
            built["machine_packet"],
            built["links_index"],
            synth_status="skipped",
        )
        self.assertTrue(verdict["pass"])
        self.assertTrue(verdict["actionable_without_synth"])

    def test_missing_drilldown_fails(self):
        reduced, built = self._built()
        fid = reduced["review_packet"]["top_findings"][0]["finding_id"]
        built["links_index"]["findings"][fid] = {"file": "", "symbol": "", "tests": [], "artifacts": []}
        verdict = artifacts.evaluate_artifact_strength(
            reduced["review_packet"],
            built["package"],
            built["machine_packet"],
            built["links_index"],
            synth_status="skipped",
        )
        self.assertFalse(verdict["pass"])
        self.assertFalse(verdict["checks"]["drilldown"])

    def test_no_next_steps_fails(self):
        reduced, built = self._built()
        built["machine_packet"]["recommended_reads"] = []
        built["machine_packet"]["recommended_commands"] = []
        verdict = artifacts.evaluate_artifact_strength(
            reduced["review_packet"],
            built["package"],
            built["machine_packet"],
            built["links_index"],
            synth_status="skipped",
        )
        self.assertFalse(verdict["pass"])
        self.assertFalse(verdict["checks"]["next_steps"])


if __name__ == "__main__":
    unittest.main()
