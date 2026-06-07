from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_axiom


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo() -> Path:
    root = Path(tempfile.mkdtemp())
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(root, "add", "app.py")
    _git(root, "commit", "-m", "initial")
    return root


class TestAxiomHarness(unittest.TestCase):
    def test_capture_writes_verified_packet(self):
        repo = _repo()
        out = repo / "out"
        packet = lgwks_axiom.build_capture(repo, "run tests", "python -c 'print(123)'", out_dir=out)
        self.assertEqual(packet["schema"], lgwks_axiom.SCHEMA)
        self.assertTrue(packet["fabric"]["chain_ok"])
        self.assertTrue((out / "emissions.jsonl").exists())
        emissions = [json.loads(line) for line in (out / "emissions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(emissions), 6)
        self.assertTrue(all(e.get("ok") for e in emissions))

    def test_divergence_flags_claimed_tests_without_test_evidence(self):
        repo = _repo()
        out = repo / "out"
        packet = lgwks_axiom.build_capture(repo, "no test run", out_dir=out)
        result = lgwks_axiom.check_narration("tests passed", packet["emissions"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["level"], "pan_pan")

    def test_divergence_accepts_captured_passing_test(self):
        repo = _repo()
        packet = lgwks_axiom.build_capture(repo, "test run", "python -c 'print(123)'")
        result = lgwks_axiom.check_narration("tests passed", packet["emissions"])
        self.assertTrue(result["ok"])

    def test_replay_reconstructs_persisted_emissions(self):
        repo = _repo()
        out = repo / "out"
        lgwks_axiom.build_capture(repo, "replay", "python -c 'print(123)'", out_dir=out)
        result = lgwks_axiom.replay_emissions(out)
        self.assertTrue(result["ok"], result["failures"])
        self.assertTrue(result["chain_ok"])
        self.assertTrue(result["log_matches"])

    def test_replay_rejects_tampered_emission_bytes(self):
        repo = _repo()
        out = repo / "out"
        lgwks_axiom.build_capture(repo, "replay", out_dir=out)
        lines = (out / "emissions.jsonl").read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[1])
        first["bytes_hex"] = first["bytes_hex"][:-2] + ("00" if first["bytes_hex"][-2:] != "00" else "ff")
        lines[1] = json.dumps(first, sort_keys=True)
        (out / "emissions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = lgwks_axiom.replay_emissions(out)
        self.assertFalse(result["ok"])
        self.assertGreater(result["counts"]["failures"], 0)

    def test_replay_rejects_tampered_fabric_log(self):
        repo = _repo()
        out = repo / "out"
        lgwks_axiom.build_capture(repo, "replay", out_dir=out)
        log = json.loads((out / "fabric-log.json").read_text(encoding="utf-8"))
        log["log"][0]["seq"] = 99
        (out / "fabric-log.json").write_text(json.dumps(log), encoding="utf-8")
        result = lgwks_axiom.replay_emissions(out)
        self.assertFalse(result["ok"])
        self.assertFalse(result["log_matches"])

    def test_test_matrix_runs_multiple_labeled_tests_and_replays(self):
        repo = _repo()
        matrix = repo / "matrix.json"
        matrix.write_text(json.dumps({
            "schema": lgwks_axiom.MATRIX_SCHEMA,
            "tests": [
                {"label": "unit", "command": ["python", "-c", "print(123)"], "timeout": 10},
                {"label": "compile check", "command": ["python", "-m", "py_compile", "app.py"], "timeout": 10},
            ],
        }), encoding="utf-8")
        specs = lgwks_axiom.load_test_matrix(matrix)
        self.assertEqual([s.label for s in specs], ["unit", "compile-check"])
        out = repo / "matrix-out"
        packet = lgwks_axiom.build_capture(repo, "matrix", out_dir=out, test_specs=specs)
        self.assertTrue(lgwks_axiom.replay_emissions(out)["ok"])
        tests = [e["fact"] for e in packet["emissions"] if e.get("fact", {}).get("kind") == "test"]
        self.assertEqual([t["label"] for t in tests], ["unit", "compile-check"])
        self.assertTrue(lgwks_axiom.check_narration("tests passed", packet["emissions"])["ok"])

    def test_test_matrix_duplicate_labels_rejected(self):
        repo = _repo()
        matrix = repo / "matrix.json"
        matrix.write_text(json.dumps([
            {"label": "unit", "command": ["python", "-c", "print(1)"]},
            {"label": "unit", "command": ["python", "-c", "print(2)"]},
        ]), encoding="utf-8")
        with self.assertRaises(ValueError):
            lgwks_axiom.load_test_matrix(matrix)

    def test_test_matrix_one_failure_makes_tests_passed_diverge(self):
        repo = _repo()
        specs = [
            lgwks_axiom.TestSpec("ok", "python -c 'print(1)'", 10),
            lgwks_axiom.TestSpec("fail", ("python", "-c", "raise SystemExit(7)"), 10),
        ]
        packet = lgwks_axiom.build_capture(repo, "matrix", test_specs=specs)
        result = lgwks_axiom.check_narration("tests passed", packet["emissions"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["level"], "mayday")

    def test_test_matrix_shell_string_rejected(self):
        repo = _repo()
        matrix = repo / "matrix.json"
        matrix.write_text(json.dumps([
            {"label": "unit", "command": "python -c 'print(1)'"},
        ]), encoding="utf-8")
        with self.assertRaises(ValueError):
            lgwks_axiom.load_test_matrix(matrix)

    def test_parse_narration_known_claims(self):
        parsed = lgwks_axiom.parse_narration("tests passed and implemented changes")
        kinds = {c["kind"] for c in parsed["claims"]}
        self.assertIn("tests_passed", kinds)
        self.assertIn("work_implemented", kinds)
        self.assertEqual(parsed["holes"], [])

    def test_parse_narration_unknown_becomes_hole(self):
        parsed = lgwks_axiom.parse_narration("the vibes are excellent")
        self.assertEqual(parsed["claims"], [])
        self.assertEqual(len(parsed["holes"]), 1)

    def test_narration_artifact_persists_claim_capsules(self):
        repo = _repo()
        out = repo / "narration"
        artifact = lgwks_axiom.build_narration_artifact("tests passed", run=out)
        self.assertEqual(artifact["schema"], lgwks_axiom.NARRATION_SCHEMA)
        self.assertEqual(artifact["claims"][0]["kind"], "tests_passed")
        self.assertTrue((out / "narration.json").exists())
        self.assertTrue((out / "narration-emissions.jsonl").exists())
        self.assertTrue(artifact["fabric"]["chain_ok"])

    def test_check_accepts_typed_claim_file_payload(self):
        repo = _repo()
        packet = lgwks_axiom.build_capture(repo, "test run", "python -c 'print(123)'")
        claims = lgwks_axiom.parse_narration("tests passed")
        result = lgwks_axiom.check_narration("", packet["emissions"], claims)
        self.assertTrue(result["ok"])
        self.assertEqual(result["typed_claims"][0]["kind"], "tests_passed")

    def test_load_narration_rejects_unsupported_claim_kind(self):
        repo = _repo()
        claims = repo / "claims.json"
        claims.write_text(json.dumps({
            "schema": lgwks_axiom.NARRATION_SCHEMA,
            "claims": [{"kind": "admin_override", "source": "x", "requires": [], "confidence": 1.0}],
            "holes": [],
        }), encoding="utf-8")
        with self.assertRaises(ValueError):
            lgwks_axiom.load_narration(claims)

    def test_unknown_narration_hole_diverges(self):
        repo = _repo()
        packet = lgwks_axiom.build_capture(repo, "test run", "python -c 'print(123)'")
        result = lgwks_axiom.check_narration("the vibes are excellent", packet["emissions"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["claim"], "unsupported narration")

    def test_axiom_layer_has_no_lgwks_imports(self):
        report = lgwks_axiom.independence_report(Path(__file__).resolve().parents[1])
        self.assertTrue(report["independent"], report["violations"])

    def test_run_index_is_written_and_appended(self):
        repo = _repo()
        out = repo / "out"
        lgwks_axiom.build_capture(repo, "capture", out_dir=out)
        index_path = out / "index.json"
        self.assertTrue(index_path.exists())
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(index["artifacts"]), 3)
        kinds = {a["kind"] for a in index["artifacts"]}
        self.assertIn("capture", kinds)
        self.assertIn("emissions", kinds)
        self.assertIn("fabric_log", kinds)

        lgwks_axiom.build_narration_artifact("tests passed", run=out)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(index["artifacts"]), 5)
        kinds = {a["kind"] for a in index["artifacts"]}
        self.assertIn("narration", kinds)
        self.assertIn("narration_emissions", kinds)


if __name__ == "__main__":
    unittest.main()
