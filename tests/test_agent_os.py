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
        # fleet orchestrator sandbox
        self.git_repo = self.tmp / "repo"
        self.git_repo.mkdir(parents=True)
        self.fleet_dir = self.tmp / "fleet"
        self.agents_dir = self.tmp / "parsed_agents"
        self.agents_dir.mkdir(parents=True)
        self.audit_log = self.tmp / "fleet-audit.jsonl"

    def _git(self, repo, *args):
        import subprocess
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        return p.returncode, p.stdout.strip()

    def _init_git_repo(self, repo):
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "test@logical.works")
        self._git(repo, "config", "user.name", "Test")
        (repo / "root.txt").write_text("root\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", "init")

    def _write_agent(self, name, branch="main"):
        (self.agents_dir / f"{name}.md").write_text(
            f"# {name}\n## Home + isolation\nWork in `~/works/{name}` (branch `{name}/{branch}`).\n",
            encoding="utf-8",
        )

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

    # ------------------------------------------------------------------
    # Fleet orchestrator tests
    # ------------------------------------------------------------------
    def _mk_orch(self, with_agents: tuple[str, ...] = ("claude", "coder")):
        self._init_git_repo(self.git_repo)
        for a in with_agents:
            self._write_agent(a)
        return agent_os.FleetOrchestrator(
            repo_root=self.git_repo,
            agents_dir=self.agents_dir,
            fleet_dir=self.fleet_dir,
            audit_log=self.audit_log,
        )

    def test_orchestrator_scans_agent_manifests(self):
        orch = self._mk_orch(("claude", "coder", "hacker"))
        agents = orch.scan_agents()
        self.assertIsInstance(agents, dict)
        self.assertEqual(set(agents.keys()), {"claude", "coder", "hacker"})

    def test_orchestrator_spawn_creates_worktree_with_inputs(self):
        orch = self._mk_orch(("coder",))
        record = orch.spawn("coder", "# implement foo", {"issue": 57})
        self.assertEqual(record.agent_id, "coder")
        self.assertTrue(record.worktree_path.exists())
        self.assertTrue((record.worktree_path / "prompt.md").exists())
        self.assertTrue((record.worktree_path / ".fleet" / "context.json").exists())
        self.assertTrue((record.worktree_path / ".fleet" / "spawn.json").exists())
        ctx = json.loads((record.worktree_path / ".fleet" / "context.json").read_text(encoding="utf-8"))
        self.assertEqual(ctx["issue"], 57)
        # Audit written with fsync
        self.assertTrue(self.audit_log.exists())
        lines = [json.loads(line) for line in self.audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["event"], "spawn")
        self.assertEqual(lines[0]["agent_id"], "coder")
        self.assertEqual(lines[0]["status"], "queued")

    def test_orchestrator_collect_reads_output(self):
        orch = self._mk_orch(("coder",))
        record = orch.spawn("coder", "# fix bug", {})
        out = {"result": "done"}
        (record.worktree_path / ".fleet" / "output.json").write_text(json.dumps(out), encoding="utf-8")
        result = orch.collect(record)
        self.assertEqual(result["status"], "collected")
        self.assertEqual(result["output"]["result"], "done")

    def test_orchestrator_collect_reports_pending_when_no_output(self):
        orch = self._mk_orch(("coder",))
        record = orch.spawn("coder", "# fix bug", {})
        result = orch.collect(record)
        self.assertEqual(result["status"], "pending")

    def test_orchestrator_spawn_two_agents_no_collision(self):
        orch = self._mk_orch(("coder", "hacker"))
        r1 = orch.spawn("coder", "# task a", {"id": 1})
        r2 = orch.spawn("hacker", "# task b", {"id": 2})
        self.assertNotEqual(r1.worktree_path, r2.worktree_path)
        self.assertNotEqual(r1.branch, r2.branch)
        # Ensure filesystem isolation
        self.assertTrue(r1.worktree_path.exists())
        self.assertTrue(r2.worktree_path.exists())
        # Verify no prompt bleed
        self.assertEqual((r1.worktree_path / "prompt.md").read_text(encoding="utf-8"), "# task a")
        self.assertEqual((r2.worktree_path / "prompt.md").read_text(encoding="utf-8"), "# task b")
        # Audit has two spawns
        lines = [json.loads(line) for line in self.audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)

    def test_orchestrator_close_removes_worktree(self):
        orch = self._mk_orch(("coder",))
        record = orch.spawn("coder", "# task", {})
        self.assertTrue(record.worktree_path.exists())
        orch.close(record)
        self.assertFalse(record.worktree_path.exists())
        lines = [json.loads(line) for line in self.audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(line["event"] == "close" for line in lines))

    def test_orchestrator_spawn_unknown_agent_raises(self):
        orch = self._mk_orch(("coder",))
        with self.assertRaises(ValueError) as exc:
            orch.spawn("architect", "# task", {})
        self.assertIn("unknown agent_id", str(exc.exception))

    def test_orchestrator_spawn_git_fail_audit_and_raise(self):
        orch = self._mk_orch(("coder",))
        # break repo so worktree add fails
        import shutil
        shutil.rmtree(self.git_repo / ".git")
        with self.assertRaises(RuntimeError) as exc:
            orch.spawn("coder", "# task", {})
        self.assertIn("worktree creation failed", str(exc.exception))
        lines = [json.loads(line) for line in self.audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["status"], "failed")
