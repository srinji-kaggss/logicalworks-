from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lgwks_agent_os as agent_os


class TestAgentOs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.prompts = self.tmp / "prompts"
        self.context = self.prompts / "context"
        self.prompts.mkdir(parents=True)
        self.context.mkdir(parents=True)
        (self.prompts / "GLOBAL.md").write_text("global\n", encoding="utf-8")
        (self.prompts / "_doctrine.md").write_text("doctrine\n", encoding="utf-8")
        (self.tmp / "claims").mkdir()
        (self.tmp / "artifacts").mkdir()
        self.fleet = self.tmp / "fleet-home"
        (self.fleet / "governance").mkdir(parents=True)
        (self.fleet / ".agents" / "prompts").mkdir(parents=True)
        (self.fleet / "AGENTS.md").write_text("fleet agents\n", encoding="utf-8")
        self.manifest = self.context / "manifest.json"
        self.cards = self.prompts / "agent_cards.json"
        self.manifest.write_text(json.dumps({
            "schema": "logicalworks.prompt-context/1",
            "entries": [
                {"name": "claims", "kind": "relative", "path": "../../claims", "required": True},
                {"name": "artifacts", "kind": "relative", "path": "../../artifacts", "required": True},
                {"name": "AGENTS.md", "kind": "fleet-home", "path": "AGENTS.md", "required": False},
                {"name": "governance", "kind": "fleet-home", "path": "governance", "required": False},
                {"name": "roles", "kind": "fleet-home", "path": ".agents/prompts", "required": False},
            ],
        }), encoding="utf-8")
        self.home = self.tmp / "home"
        agents_dir = self.home / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        for role in agent_os.ROLE_SUBAGENTS:
            (agents_dir / f"{role}.md").write_text(f"{role}\n", encoding="utf-8")

    def test_bootstrap_context_writes_links_and_cards(self):
        with patch.object(agent_os, "PROMPTS_ROOT", self.prompts), \
             patch.object(agent_os, "CONTEXT_DIR", self.context), \
             patch.object(agent_os, "MANIFEST_PATH", self.manifest), \
             patch.object(agent_os, "AGENT_CARD_PATH", self.cards), \
             patch.dict(os.environ, {"LGWKS_FLEET_HOME": str(self.fleet), "HOME": str(self.home)}, clear=False):
            results = agent_os.bootstrap_context()
            self.assertEqual({r["status"] for r in results}, {"linked"})
            self.assertTrue((self.context / "claims").is_symlink())
            self.assertTrue((self.context / "governance").is_symlink())
            out = agent_os.write_agent_cards(self.cards)
            self.assertEqual(out, self.cards)
            payload = json.loads(self.cards.read_text(encoding="utf-8"))
            self.assertEqual(payload["protocol"], "A2A/1.0")
            self.assertEqual(len(payload["roles"]), 5)

    def test_doctor_reports_green_when_bundle_complete(self):
        with patch.object(agent_os, "PROMPTS_ROOT", self.prompts), \
             patch.object(agent_os, "CONTEXT_DIR", self.context), \
             patch.object(agent_os, "MANIFEST_PATH", self.manifest), \
             patch.object(agent_os, "AGENT_CARD_PATH", self.cards), \
             patch.dict(os.environ, {"LGWKS_FLEET_HOME": str(self.fleet), "HOME": str(self.home)}, clear=False):
            agent_os.write_agent_cards(self.cards)
            agent_os.bootstrap_context()
            status = agent_os.doctor()
            self.assertTrue(status["ok"])
            self.assertTrue(all(status["startup_files"].values()))
            self.assertTrue(all(status["role_subagents"].values()))
