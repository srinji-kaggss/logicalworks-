"""Tests for lgwks_spawn — AI-AI handoff packet assembler."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import lgwks_spawn


class TestSpawnPacket(unittest.TestCase):
    def _make_run_dir(self, with_aup=True, with_do=True, with_context=True) -> Path:
        d = Path(tempfile.mkdtemp(prefix="lgwks-spawn-test-"))
        if with_aup:
            (d / "aup.verdict.json").write_text(json.dumps({"verdict": "allow", "confidence": 0.99}))
        if with_do:
            (d / "do.run.json").write_text(json.dumps({"phases": [{"name": "specify", "ok": True}]}))
        if with_context:
            ctx = d / "context"
            ctx.mkdir()
            for tier in ("raw", "full", "compact", "ultra"):
                (ctx / tier).mkdir()
            (ctx / "CONTEXT.md").write_text("# Context\nline1\nline2\n")
            (ctx / "state_matrix.json").write_text("{}")
            (d / "rounds.ledger.jsonl").write_text(json.dumps({"n": 1}) + "\n")
        return d

    def test_assemble_packet_schema(self):
        run_dir = self._make_run_dir()
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertEqual(packet["schema"], "lgwks.spawn.v1")
        self.assertIn("timestamp", packet)
        self.assertIn("provenance", packet)
        self.assertIn("git_sha", packet["provenance"])
        self.assertIn("hostname", packet["provenance"])
        self.assertEqual(packet["provenance"]["version"], "lgwks.spawn.v1")

    def test_assemble_packet_aup(self):
        run_dir = self._make_run_dir(with_aup=True)
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertEqual(packet["aup"]["verdict"], "allow")

    def test_assemble_packet_no_aup(self):
        run_dir = self._make_run_dir(with_aup=False)
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertEqual(packet["aup"]["verdict"], "unknown")

    def test_assemble_packet_do_run(self):
        run_dir = self._make_run_dir(with_do=True)
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertTrue(packet["do_run"]["phases"])

    def test_assemble_packet_context_meta(self):
        run_dir = self._make_run_dir(with_context=True)
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertTrue(packet["context"]["has_context_md"])
        self.assertTrue(packet["context"]["has_state_matrix"])
        self.assertTrue(packet["context"]["has_ledger"])
        self.assertGreater(packet["context"]["context_md_lines"], 0)

    def test_assemble_packet_capabilities(self):
        run_dir = self._make_run_dir()
        packet = lgwks_spawn.assemble_packet(run_dir)
        self.assertGreater(packet["capabilities"]["verb_count"], 0)
        self.assertIsInstance(packet["capabilities"]["verbs"], list)
        self.assertIsInstance(packet["capabilities"]["domains"], dict)

    def test_write_packet(self):
        run_dir = self._make_run_dir()
        out = lgwks_spawn.write_packet(run_dir)
        self.assertIsNotNone(out)
        self.assertTrue(out.exists())
        loaded = json.loads(out.read_text())
        self.assertEqual(loaded["schema"], "lgwks.spawn.v1")

    def test_write_packet_invalid_dir(self):
        out = lgwks_spawn.write_packet(Path("/nonexistent/spawn-test-12345"))
        self.assertIsNone(out)

    def test_cli_json(self):
        run_dir = self._make_run_dir()
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_spawn._spawn_command(type("Args", (), {"run_dir": str(run_dir), "json": True})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            packet = json.loads(output)
            self.assertEqual(packet["schema"], "lgwks.spawn.v1")
        finally:
            sys.stdout = old_stdout

    def test_cli_summary(self):
        run_dir = self._make_run_dir()
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_spawn._spawn_command(type("Args", (), {"run_dir": str(run_dir), "json": False})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            self.assertIn("spawn packet:", output)
            self.assertIn("lgwks.spawn.v1", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_bad_dir(self):
        rc = lgwks_spawn._spawn_command(type("Args", (), {"run_dir": "/nonexistent", "json": False})())
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
