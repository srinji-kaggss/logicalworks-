"""
Tests for U6: lgwks_bot_slop_math (S1–S6).

Acceptance:
  1. Each sub-bot runs independently.
  2. Cycle and long-chain findings emitted from seeded graph fixtures.
  3. Spec drift detected against seeded schema/doc mismatches.
  4. Proof gap bot detects claims with no linked tests/evidence.
  5. Contradiction bot emits structured records, not prose.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import lgwks_bot_slop_math as slop
import lgwks_project_artifacts as artifacts


# ── graph stub ────────────────────────────────────────────────────────────────

def _make_graph(patterns: dict) -> object:
    """Minimal stub satisfying graph.detect_patterns() contract."""
    return SimpleNamespace(detect_patterns=lambda: patterns)


def _cycle_patterns(*groups: list[str]) -> dict:
    return {
        "circular_dependencies": {"count": len(groups), "groups": list(groups)},
        "god_modules": {"threshold_in": 9.0, "threshold_out": 9.0, "modules": []},
        "orphans": [],
        "unstable_modules": {"threshold": 0.8, "modules": []},
        "gatekeepers": {"threshold": 0.1, "modules": []},
        "tight_coupling": {"threshold": 0.5, "modules": []},
        "long_chains": [],
    }


def _hub_patterns(hubs: list[str]) -> dict:
    return {
        "circular_dependencies": {"count": 0, "groups": []},
        "god_modules": {"threshold_in": 3.0, "threshold_out": 3.0, "modules": hubs},
        "orphans": [],
        "unstable_modules": {"threshold": 0.8, "modules": []},
        "gatekeepers": {"threshold": 0.1, "modules": []},
        "tight_coupling": {"threshold": 0.5, "modules": []},
        "long_chains": [],
    }


def _long_chain_patterns(src: str, dst: str, length: int) -> dict:
    path = [f"m{i}" for i in range(length)]
    path[0] = src
    path[-1] = dst
    return {
        "circular_dependencies": {"count": 0, "groups": []},
        "god_modules": {"threshold_in": 9.0, "threshold_out": 9.0, "modules": []},
        "orphans": [],
        "unstable_modules": {"threshold": 0.8, "modules": []},
        "gatekeepers": {"threshold": 0.1, "modules": []},
        "tight_coupling": {"threshold": 0.5, "modules": []},
        "long_chains": [{"from": src, "to": dst, "length": length, "path": path}],
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _all_valid(findings: list[dict], test: unittest.TestCase) -> None:
    for rec in findings:
        ok, errs = artifacts.validate_bot_record(rec)
        test.assertTrue(ok, f"invalid record {rec.get('kind')}: {errs}")


# ── S1: graph anomaly ─────────────────────────────────────────────────────────

class TestS1GraphAnomaly(unittest.TestCase):
    """Acceptance 1 + 2: runs independently, cycle/chain findings emitted."""

    def test_cycle_risk_emitted(self):
        graph = _make_graph(_cycle_patterns(["a.py", "b.py", "c.py"]))
        findings = slop.run_s1_graph_anomaly(graph, repo="/repo")
        kinds = [f["kind"] for f in findings]
        self.assertIn("cycle_risk", kinds)

    def test_cycle_record_is_valid_schema(self):
        graph = _make_graph(_cycle_patterns(["x.py", "y.py"]))
        findings = slop.run_s1_graph_anomaly(graph, repo="/repo")
        _all_valid(findings, self)

    def test_long_chain_emitted(self):
        graph = _make_graph(_long_chain_patterns("alpha.py", "omega.py", 8))
        findings = slop.run_s1_graph_anomaly(graph, repo="/repo")
        kinds = [f["kind"] for f in findings]
        self.assertIn("long_chain", kinds)

    def test_hub_risk_emitted(self):
        graph = _make_graph(_hub_patterns(["hub.py", "mega.py"]))
        findings = slop.run_s1_graph_anomaly(graph, repo="/repo")
        kinds = [f["kind"] for f in findings]
        self.assertIn("hub_risk", kinds)

    def test_graph_failure_emits_analyzer_record(self):
        bad_graph = SimpleNamespace(detect_patterns=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        findings = slop.run_s1_graph_anomaly(bad_graph, repo="/repo")
        self.assertTrue(any(f["kind"] == "analyzer_failure" for f in findings))
        _all_valid(findings, self)

    def test_empty_patterns_produces_no_findings(self):
        graph = _make_graph(_cycle_patterns())  # zero cycles
        findings = slop.run_s1_graph_anomaly(graph, repo="/repo")
        real = [f for f in findings if f["kind"] != "analyzer_failure"]
        self.assertEqual(real, [])


# ── S2: naming bot ────────────────────────────────────────────────────────────

class TestS2NamingBot(unittest.TestCase):
    """Acceptance 1: runs independently; generic names flagged."""

    def test_generic_function_name_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def helper(): pass\n", encoding="utf-8")
            findings = slop.run_s2_naming_bot(tmp)
        kinds = [f["kind"] for f in findings]
        self.assertIn("naming_drift", kinds)

    def test_normal_function_not_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def build_jepa_package(): pass\n", encoding="utf-8")
            findings = slop.run_s2_naming_bot(tmp)
        drift = [f for f in findings if f["kind"] == "naming_drift"]
        self.assertFalse(drift)

    def test_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def util(): pass\ndef handler(): pass\n", encoding="utf-8")
            findings = slop.run_s2_naming_bot(tmp)
        _all_valid(findings, self)


# ── S3: spec drift ────────────────────────────────────────────────────────────

class TestS3SpecDrift(unittest.TestCase):
    """Acceptance 3: spec drift detected against seeded mismatches."""

    def _build_repo(self, tmp: Path, *, schema_title: str, code_schema: str) -> None:
        (tmp / "docs").mkdir(exist_ok=True)
        (tmp / "docs" / "schemas").mkdir(exist_ok=True)
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": schema_title,
        }
        (tmp / "docs" / "schemas" / "test.schema.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )
        (tmp / "mod.py").write_text(
            f'SOME_SCHEMA = "{code_schema}"\n', encoding="utf-8"
        )

    def test_missing_schema_constant_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # schema file says "lgwks.new.thing.v1" but code has "lgwks.old.thing.v1"
            self._build_repo(tmp, schema_title="lgwks.new.thing.v1", code_schema="lgwks.old.thing.v1")
            findings = slop.run_s3_spec_drift(tmp)
        kinds = [f["kind"] for f in findings]
        self.assertIn("spec_code_drift", kinds)

    def test_matching_schema_not_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            self._build_repo(tmp, schema_title="lgwks.match.v1", code_schema="lgwks.match.v1")
            findings = slop.run_s3_spec_drift(tmp)
        drift = [f for f in findings if f["kind"] == "spec_code_drift"]
        self.assertFalse(drift)

    def test_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            self._build_repo(tmp, schema_title="lgwks.x.v1", code_schema="lgwks.y.v1")
            findings = slop.run_s3_spec_drift(tmp)
        _all_valid(findings, self)


# ── S4: proof gap ─────────────────────────────────────────────────────────────

class TestS4ProofGap(unittest.TestCase):
    """Acceptance 4: claims without linked tests detected."""

    def test_todo_without_issue_ref_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("# TODO: fix this thing\nx = 1\n", encoding="utf-8")
            findings = slop.run_s4_proof_gap(tmp)
        kinds = [f["kind"] for f in findings]
        self.assertIn("proof_gap", kinds)

    def test_todo_with_issue_ref_not_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("# TODO(#42): tracked issue\nx = 1\n", encoding="utf-8")
            findings = slop.run_s4_proof_gap(tmp)
        gaps = [f for f in findings if f["kind"] == "proof_gap"]
        self.assertFalse(gaps)

    def test_test_gap_for_untested_function(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def my_special_function(): pass\n", encoding="utf-8")
            tests_dir = tmp / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_other.py").write_text("def test_something_else(): pass\n", encoding="utf-8")
            findings = slop.run_s4_proof_gap(tmp)
        gaps = [f for f in findings if f["kind"] == "test_gap" and "my_special_function" in f["summary"]]
        self.assertTrue(gaps)

    def test_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("# FIXME: broken\ndef foo(): pass\n", encoding="utf-8")
            findings = slop.run_s4_proof_gap(tmp)
        _all_valid(findings, self)


# ── S5: dead abstraction ──────────────────────────────────────────────────────

class TestS5DeadAbstraction(unittest.TestCase):
    """Acceptance 1: runs independently; unreferenced definitions flagged."""

    def test_unreferenced_function_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def orphaned_function_xyz(): pass\n", encoding="utf-8")
            findings = slop.run_s5_dead_abstraction(tmp)
        dead = [f for f in findings if f["kind"] == "dead_abstraction"]
        summaries = [f["summary"] for f in dead]
        self.assertTrue(any("orphaned_function_xyz" in s for s in summaries))

    def test_referenced_function_not_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.py").write_text("def shared_fn(): pass\n", encoding="utf-8")
            (tmp / "b.py").write_text("from a import shared_fn\nshared_fn()\n", encoding="utf-8")
            findings = slop.run_s5_dead_abstraction(tmp)
        dead = [f for f in findings if f["kind"] == "dead_abstraction" and "shared_fn" in f["summary"]]
        self.assertFalse(dead)

    def test_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("def ghost_fn_zzz(): pass\n", encoding="utf-8")
            findings = slop.run_s5_dead_abstraction(tmp)
        _all_valid(findings, self)


# ── S6: contradiction ─────────────────────────────────────────────────────────

class TestS6Contradiction(unittest.TestCase):
    """Acceptance 5: contradiction records are structured, not prose."""

    def test_conflicting_constant_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.py").write_text('VERSION = "1.0"\n', encoding="utf-8")
            (tmp / "b.py").write_text('VERSION = "2.0"\n', encoding="utf-8")
            findings = slop.run_s6_contradiction(tmp)
        kinds = [f["kind"] for f in findings]
        self.assertIn("contradiction", kinds)

    def test_consistent_constant_not_flagged(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.py").write_text('LIMIT = 100\n', encoding="utf-8")
            (tmp / "b.py").write_text('LIMIT = 100\n', encoding="utf-8")
            findings = slop.run_s6_contradiction(tmp)
        contradictions = [f for f in findings if f["kind"] == "contradiction"]
        self.assertFalse(contradictions)

    def test_contradiction_record_is_structured(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.py").write_text('MAX_SIZE = 512\n', encoding="utf-8")
            (tmp / "b.py").write_text('MAX_SIZE = 1024\n', encoding="utf-8")
            findings = slop.run_s6_contradiction(tmp)
        rec = next(f for f in findings if f["kind"] == "contradiction")
        # structured — must have evidence and a symbol link, not prose blobs
        self.assertTrue(rec["evidence"])
        self.assertIsNotNone(rec["links"].get("symbol"))
        ok, errs = artifacts.validate_bot_record(rec)
        self.assertTrue(ok, errs)

    def test_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "x.py").write_text('FLAG = True\n', encoding="utf-8")
            (tmp / "y.py").write_text('FLAG = False\n', encoding="utf-8")
            findings = slop.run_s6_contradiction(tmp)
        _all_valid(findings, self)


# ── run_all integration ───────────────────────────────────────────────────────

class TestRunAll(unittest.TestCase):
    def test_run_all_without_graph_skips_s1(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("x = 1\n", encoding="utf-8")
            findings = slop.run_all(tmp, graph=None)
        s1_finds = [f for f in findings if "graph_anomaly" in f["bot"]]
        self.assertFalse(s1_finds)

    def test_run_all_with_graph_includes_s1(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "m.py").write_text("x = 1\n", encoding="utf-8")
            graph = _make_graph(_cycle_patterns(["a.py", "b.py"]))
            findings = slop.run_all(tmp, graph=graph)
        s1_finds = [f for f in findings if "graph_anomaly" in f["bot"]]
        self.assertTrue(s1_finds)

    def test_all_run_all_records_valid(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.py").write_text('VER = "1"\ndef util(): pass\n', encoding="utf-8")
            (tmp / "b.py").write_text('VER = "2"\n', encoding="utf-8")
            graph = _make_graph(_hub_patterns(["a.py"]))
            findings = slop.run_all(tmp, graph=graph)
        _all_valid(findings, self)
