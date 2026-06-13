from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

import lgwks_audit_graph as audit_graph


class FakeEngine:
    def __init__(
        self,
        *,
        callees: dict[str, list[str]] | None = None,
        callers: dict[str, list[str]] | None = None,
        tainted: list[str] | None = None,
        nodes: dict[str, dict] | None = None,
    ):
        self._callees = callees or {}
        self._callers = callers or {}
        self._tainted = tainted or []
        self._nodes = nodes or {node: {"text": ""} for node in self._callees}

    def preanalysis(self) -> None:
        pass

    def to_json(self) -> str:
        return json.dumps({"nodes": self._nodes, "edges": []})

    def subgraph(self, name: str) -> list[str]:
        if name == "tainted":
            return self._tainted
        return []

    def callees_of(self, node_id: str) -> list[dict]:
        return [{"name": name} for name in self._callees.get(node_id, [])]

    def callers_of(self, node_id: str) -> list[dict]:
        return [{"name": name} for name in self._callers.get(node_id, [])]


class FakeQueryEngine:
    engine: FakeEngine

    @classmethod
    def from_directory(cls, *_args, **_kwargs):
        return cls.engine


def _rank(node: str, *, lane: str = "auto", centrality: float = 1.0):
    return SimpleNamespace(
        node_cid=node,
        centrality=centrality,
        rank_det=1,
        rank_ai=1,
        delta=0,
        lane=lane,
        schema_id="lgwks.rank.record.v1",
    )


class TestAuditGraphSinks(unittest.TestCase):
    def _run(self, engine: FakeEngine, ranks: list[SimpleNamespace] | None = None, *, escalated: bool = False):
        FakeQueryEngine.engine = engine
        fake_tm = SimpleNamespace(QueryEngine=FakeQueryEngine)
        with mock.patch.object(audit_graph, "tm", fake_tm):
            with mock.patch.object(audit_graph.lgwks_rank, "rank_graph", return_value=ranks or [_rank("n1")]):
                return audit_graph.run_audit(Path("."), escalated=escalated)

    def test_substring_callee_names_do_not_trigger_sinks(self):
        engine = FakeEngine(
            tainted=["n1"],
            callees={
                "n1": [
                    "forget",
                    "widget",
                    "target",
                    "compose",
                    "rerun",
                    "subsystem",
                ]
            },
        )

        result = self._run(engine)

        kinds = {finding["kind"] for finding in result.findings}
        self.assertNotIn("aversion_sodium_leak", kinds)
        self.assertNotIn("aversion_cmd_detonation", kinds)
        self.assertFalse(result.escalation_required)

    def test_exact_network_and_command_sinks_still_trigger(self):
        engine = FakeEngine(
            tainted=["net", "cmd"],
            callees={
                "net": ["requests.get"],
                "cmd": ["subprocess.run"],
            },
        )

        result = self._run(engine, ranks=[_rank("net"), _rank("cmd")])

        kinds = {finding["kind"] for finding in result.findings}
        self.assertIn("aversion_sodium_leak", kinds)
        self.assertIn("aversion_cmd_detonation", kinds)
        self.assertTrue(result.escalation_required)

    def test_exact_guard_and_escape_suppress_aversions(self):
        engine = FakeEngine(
            tainted=["net", "cmd"],
            callees={
                "net": ["requests.get"],
                "cmd": ["subprocess.run", "shlex.quote"],
            },
            callers={"net": ["lgwks_browser._remote_allowed"]},
        )

        result = self._run(engine, ranks=[_rank("net"), _rank("cmd")])

        self.assertFalse(result.findings)
        self.assertFalse(result.escalation_required)

    def test_tier3_requested_does_not_emit_fake_analysis_finding(self):
        engine = FakeEngine(
            tainted=["net"],
            callees={"net": ["httpx.get"]},
        )

        result = self._run(engine, ranks=[_rank("net")], escalated=True)

        kinds = {finding["kind"] for finding in result.findings}
        self.assertIn("aversion_sodium_leak", kinds)
        self.assertNotIn("escalated_reasoning", kinds)
        self.assertEqual(result.summary["tier3_status"], "adapter_not_configured")
        self.assertTrue(result.escalation_required)

    def test_human_lane_alone_does_not_force_escalation(self):
        engine = FakeEngine(callees={"n1": []}, nodes={"n1": {"text": ""}})

        result = self._run(engine, ranks=[_rank("n1", lane="human")])

        self.assertFalse(result.findings)
        self.assertFalse(result.escalation_required)
        self.assertEqual(result.summary["tier3_status"], "not_required")


if __name__ == "__main__":
    unittest.main()
