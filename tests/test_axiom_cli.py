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

    def test_axiom_layer_has_no_lgwks_imports(self):
        report = lgwks_axiom.independence_report(Path(__file__).resolve().parents[1])
        self.assertTrue(report["independent"], report["violations"])


if __name__ == "__main__":
    unittest.main()
