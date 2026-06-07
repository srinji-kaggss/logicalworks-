from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import lgwks_axiom
import lgwks_run


def _repo() -> Path:
    root = Path(tempfile.mkdtemp())
    # Mock a git repo for axiom facts
    (root / ".git").mkdir()
    (root / "app.py").write_text("print('hi')", encoding="utf-8")
    return root


class TestRunSpine(unittest.TestCase):
    def test_adopt_axiom_run_creates_universal_index(self):
        repo = _repo()
        out = repo / "axiom-out"
        lgwks_axiom.build_capture(repo, "capture", ("python", "-c", "1"), out_dir=out, adopt=False)
        
        # Now adopt manually
        res = lgwks_run.adopt_axiom_run(out, repo=repo)
        self.assertEqual(res["schema"], lgwks_run.UNIVERSAL_SCHEMA)
        self.assertEqual(res["source"], "axiom")
        
        # Verify artifacts
        kinds = {a["kind"] for a in res["artifacts"]}
        self.assertIn("axiom_run_index", kinds)
        self.assertIn("axiom_capture", kinds)
        self.assertIn("axiom_emissions", kinds)
        
        # Verify index file exists
        run_id = res["run_id"]
        uni_index_path = repo / ".lgwks" / "runs" / run_id / "index.json"
        self.assertTrue(uni_index_path.exists())

    def test_adoption_is_idempotent(self):
        repo = _repo()
        out = repo / "axiom-out"
        lgwks_axiom.build_capture(repo, "capture", ("python", "-c", "1"), out_dir=out, adopt=False)
        
        res1 = lgwks_run.adopt_axiom_run(out, repo=repo)
        res2 = lgwks_run.adopt_axiom_run(out, repo=repo)
        
        self.assertEqual(len(res1["artifacts"]), len(res2["artifacts"]))
        self.assertEqual(res1["run_id"], res2["run_id"])

    def test_axiom_commands_adopt_by_default(self):
        repo = _repo()
        out = repo / "axiom-out"
        packet = lgwks_axiom.build_capture(repo, "capture", ("python", "-c", "1"), out_dir=out)
        
        axiom_id = packet["run_id"]
        run_id = f"run-{axiom_id.replace('axiom-', '')}"
        uni_index_path = repo / ".lgwks" / "runs" / run_id / "index.json"
        
        self.assertTrue(uni_index_path.exists())
        index = json.loads(uni_index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["run_id"], run_id)

    def test_unsafe_paths_rejected(self):
        root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            lgwks_run.write_universal_index(
                root, "run-1", "test",
                [{"kind": "bad", "path": "/etc/passwd", "cid": "x"}]
            )

    def test_adoption_fails_on_missing_artifact(self):
        repo = _repo()
        out = repo / "axiom-out"
        lgwks_axiom.build_capture(repo, "capture", ("python", "-c", "1"), out_dir=out, adopt=False)
        
        # Delete one artifact
        (out / "emissions.jsonl").unlink()
        
        with self.assertRaises(ValueError) as cm:
            lgwks_run.adopt_axiom_run(out, repo=repo)
        self.assertIn("artifact missing", str(cm.exception))

    def test_adoption_fails_on_unknown_kind_without_schema(self):
        repo = _repo()
        out = repo / "axiom-out"
        lgwks_axiom.build_capture(repo, "capture", ("python", "-c", "1"), out_dir=out, adopt=False)
        
        # Tamper Axiom index to add an unknown kind without schema
        path = out / "index.json"
        index = json.loads(path.read_text(encoding="utf-8"))
        index["artifacts"].append({"kind": "mysterious", "path": "packet.json"}) # missing schema
        path.write_text(json.dumps(index), encoding="utf-8")
        
        with self.assertRaises(ValueError) as cm:
            lgwks_run.adopt_axiom_run(out, repo=repo)
        self.assertIn("unknown artifact kind 'mysterious' missing schema", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
