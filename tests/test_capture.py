from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_capture as capture


class TestCapture(unittest.TestCase):
    def _repo_fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "auth_runtime.py").write_text(
            "def login_scope(user):\n"
            "    return user\n",
            encoding="utf-8",
        )
        (root / "browser_session.py").write_text(
            "from auth_runtime import login_scope\n"
            "def session_user():\n"
            "    return login_scope('x')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        return root

    def test_inline_capture_materializes_and_saves_packet(self):
        with tempfile.TemporaryDirectory() as td:
            fake_manifest = {
                "run_id": "run-123",
                "counts": {"sources": 1, "documents": 1, "chunks": 1, "facts": 1, "frontier": 0, "graph_nodes": 1, "graph_edges": 0},
                "embedding": {"provider_requested": "deterministic", "model_requested": "", "providers_used": {"deterministic": 1},
                              "semantic_vectors": 0, "total_vectors": 1, "global_fact_vectors_written": 1},
                "artifacts": {"root": td},
                "global_artifacts": {"fact_vector_db": str(Path(td) / "facts.db")},
            }
            args = type("Args", (), {
                "target": "",
                "intent": "my messy research thought blob",
                "context_file": [],
                "stdin_text": "",
                "repo": "",
                "project": "ideas",
                "source_type": "auto",
                "max_pages": 25,
                "max_depth": 2,
                "max_files": 250,
                "max_chars": 120000,
                "chunk_words": 320,
                "chunk_overlap": 48,
                "fact_threshold": 0.6,
                "embed_provider": "deterministic",
                "embed_model": "",
                "login_if_needed": True,
                "login_url": "",
                "success_selector": None,
                "max_auto_bypass_attempts": 3,
                "max_auth_handoffs": 3,
                "browser_engine": "chromium",
                "refresh_graph": False,
            })()
            with mock.patch.object(capture, "CAPTURE_ROOT", Path(td) / "captures"):
                with mock.patch.object(capture.lgwks_substrate, "build_run", return_value=fake_manifest):
                    packet = capture.build_capture(args)
            self.assertEqual(packet["schema"], capture.CAPTURE_SCHEMA)
            self.assertTrue(packet["key"].startswith("capture:"))
            self.assertTrue(packet["input"]["effective_target"].endswith("capture.txt"))
            self.assertEqual(packet["bindings"]["portal_key"], "")
            self.assertTrue((Path(td) / "captures" / f"{packet['key'].replace(':', '_')}.json").exists())

    def test_repo_capture_builds_portal_binding(self):
        repo = self._repo_fixture()
        with tempfile.TemporaryDirectory() as td:
            fake_manifest = {
                "run_id": "run-456",
                "counts": {"sources": 1, "documents": 1, "chunks": 1, "facts": 1, "frontier": 0, "graph_nodes": 1, "graph_edges": 0},
                "embedding": {"provider_requested": "deterministic", "model_requested": "", "providers_used": {"deterministic": 1},
                              "semantic_vectors": 0, "total_vectors": 1, "global_fact_vectors_written": 1},
                "artifacts": {"root": td},
                "global_artifacts": {"fact_vector_db": str(Path(td) / "facts.db")},
            }
            args = type("Args", (), {
                "target": str(repo),
                "intent": "auth login scope for browser session",
                "context_file": [],
                "stdin_text": "",
                "repo": "",
                "project": "repo-thoughts",
                "source_type": "repo",
                "max_pages": 25,
                "max_depth": 2,
                "max_files": 250,
                "max_chars": 120000,
                "chunk_words": 320,
                "chunk_overlap": 48,
                "fact_threshold": 0.6,
                "embed_provider": "deterministic",
                "embed_model": "",
                "login_if_needed": True,
                "login_url": "",
                "success_selector": None,
                "max_auto_bypass_attempts": 3,
                "max_auth_handoffs": 3,
                "browser_engine": "chromium",
                "refresh_graph": True,
            })()
            with mock.patch.object(capture, "CAPTURE_ROOT", Path(td) / "captures"):
                with mock.patch.object(capture.lgwks_substrate, "build_run", return_value=fake_manifest):
                    packet = capture.build_capture(args)
            self.assertEqual(packet["bindings"]["repo"], str(repo.resolve()))
            self.assertTrue(packet["bindings"]["portal_key"].startswith("portal:"))
            portal_path = repo / ".lgwks" / "portals" / f"{packet['bindings']['portal_key'].replace(':', '_')}.json"
            self.assertTrue(portal_path.exists())
            portal_packet = json.loads(portal_path.read_text(encoding="utf-8"))
            ranked = [row["path"] for row in portal_packet["candidate_files"][:3]]
            self.assertIn("auth_runtime.py", ranked)


if __name__ == "__main__":
    unittest.main()
