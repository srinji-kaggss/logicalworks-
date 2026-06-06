"""Tests for lgwks_portal — deterministic project/portal packet builder."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import lgwks_portal as portal


class TestPortal(unittest.TestCase):
    def _repo_fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "auth_runtime.py").write_text(
            "def login_scope(user):\n"
            "    return user\n",
            encoding="utf-8",
        )
        (root / "billing.py").write_text(
            "from auth_runtime import login_scope\n"
            "def invoice_total():\n"
            "    return login_scope('x')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        return root

    def test_build_portal_ranks_relevant_file_first(self):
        repo = self._repo_fixture()
        packet = portal.build_portal(repo, "auth login scope for browser session", refresh=True)
        self.assertEqual(packet["schema"], portal.PORTAL_SCHEMA)
        self.assertTrue(packet["key"].startswith("portal:"))
        self.assertTrue(packet["project_key"].startswith("project:"))
        self.assertEqual(packet["candidate_files"][0]["path"], "auth_runtime.py")
        self.assertEqual(packet["relation_candidates"][0]["state"], "search")
        self.assertTrue(all(edge["state"] == "hard" for edge in packet["hard_edges"]))

    def test_validate_portal_packet_rejects_invalid_candidate_state(self):
        bad = {
            "schema": portal.PORTAL_SCHEMA,
            "key": "portal:abc",
            "project_key": "project:abc",
            "repo": "/tmp/x",
            "intent": "test",
            "tranches": ["repo_code", "project_intent"],
            "candidate_files": [],
            "relation_candidates": [{"source": "a", "target": "b", "kind": "relevance", "state": "imagined", "score": 1.0, "why": []}],
            "hard_edges": [],
        }
        with self.assertRaises(ValueError):
            portal._validate_portal_packet(bad)

    def test_show_and_code_roundtrip_saved_packet(self):
        repo = self._repo_fixture()
        packet = portal.build_portal(repo, "auth login scope", refresh=True)
        out = repo / ".lgwks" / "portals"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{packet['key'].replace(':', '_')}.json"
        path.write_text(json.dumps(packet), encoding="utf-8")

        loaded = portal._load_portal(repo, packet["key"])
        self.assertEqual(loaded["key"], packet["key"])
        self.assertGreaterEqual(len(loaded["candidate_files"]), 1)


if __name__ == "__main__":
    unittest.main()
