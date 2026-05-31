#!/usr/bin/env python3
"""
Negative-path tests for the jarvis constitution (Issue #7, ADR-001).

The constitution's `test_obligation`: no law is trusted until its fail-closed negative-path test is
green. These assert the *violation* is caught — gates fail closed, scope cannot widen, the chain
detects tampering, the vault refuses bad authority, edges are not over-labelled. stdlib only.

Run:  python3 -m unittest tests/test_constitution.py -v
"""

from __future__ import annotations

import dataclasses
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lgwks_run as r  # noqa: E402


def _load_script(relpath: str):
    """Load a no-extension CLI script (possibly in a subdir) as a module."""
    from importlib.machinery import SourceFileLoader
    modname = Path(relpath).name.replace("-", "_")
    loader = SourceFileLoader(modname, str(ROOT / relpath))
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestSpineGates(unittest.TestCase):
    """L1/L6/L9 — the crawler must not run unless every gate clicked, and only on the frozen set."""

    def setUp(self):
        self.plan, self.syn = r._demo_plan(all_pass=True)
        self.tmp = Path(tempfile.mkdtemp())

    def _run(self, plan):
        return r.execute_plan(plan, dry=True, synthetic=self.syn, out_dir=self.tmp)

    def test_red_gate_fails_closed(self):
        plan, syn = r._demo_plan(all_pass=False)
        with self.assertRaises(r.GateError):
            r.execute_plan(plan, dry=True, synthetic=syn, out_dir=self.tmp)

    def test_missing_gate_fails_closed(self):
        plan = dataclasses.replace(self.plan, verdicts=self.plan.verdicts[:-1])  # drop L9_conduct
        with self.assertRaises(r.GateError):
            self._run(plan)

    def test_empty_scope_fails_closed(self):
        plan = dataclasses.replace(self.plan, frozen_scope=())
        with self.assertRaises(r.GateError):
            self._run(plan)

    def test_out_of_scope_url_rejected(self):
        self.assertFalse(r._in_scope("https://evil.test/x", self.plan.frozen_scope))
        self.assertTrue(r._in_scope(self.plan.frozen_scope[0], self.plan.frozen_scope))

    def test_max_pages_budget_honored(self):
        plan = dataclasses.replace(self.plan, max_pages=1)
        res = self._run(plan)
        self.assertLessEqual(res.fetched, 1)


class TestSpinePostChecks(unittest.TestCase):
    """L2/L3/L4/L5 — labels bounded by evidence, uncertainty from information, quarantine, chain."""

    def setUp(self):
        self.plan, self.syn = r._demo_plan(all_pass=True)
        self.tmp = Path(tempfile.mkdtemp())

    def test_L2_no_semantic_label_without_semantic_vector(self):
        # Deterministic embed is NOT semantic -> no edge may claim semantic_similarity.
        res = r.execute_plan(self.plan, dry=True, synthetic=self.syn, out_dir=self.tmp)
        import json
        graph = json.loads((Path(res.prevector_path)).read_text())
        kinds = {e["kind"] for e in graph["edges"]}
        self.assertNotIn("semantic_similarity", kinds)
        self.assertIn("lexical_cooccurrence", kinds)

    def test_L3_uncertainty_not_zero_on_thin_crawl(self):
        res = r.execute_plan(self.plan, dry=True, synthetic=self.syn, out_dir=self.tmp)
        self.assertGreater(res.uncertainty, 0.0)  # never "complete/certain" on a 2-page crawl

    def test_L4_quarantine_when_no_falsifier(self):
        res = r.execute_plan(self.plan, dry=True, synthetic=self.syn, out_dir=self.tmp)
        self.assertGreater(res.quarantined, 0)
        self.assertTrue((self.tmp / "quarantine.jsonl").exists())

    def test_L5_runlog_chain_intact_then_tamper_detected(self):
        log = r.RunLog("t", None)
        log.append("a", {"x": 1})
        log.append("b", {"y": 2})
        self.assertTrue(log.verify())
        log.records[0]["data"]["x"] = 999  # tamper
        self.assertFalse(log.verify())

    def test_no_embed_yields_empty_vector_cache(self):
        plan = dataclasses.replace(self.plan, embed=False)
        res = r.execute_plan(plan, dry=True, synthetic=self.syn, out_dir=self.tmp)
        self.assertEqual(res.embed_provider, "none")
        self.assertFalse((self.tmp / "embeddings.jsonl").exists())


class TestVaultAuthority(unittest.TestCase):
    """L5/L8 — vault is hash-chained, the bot cannot author human-authority events, no secret leaks."""

    def setUp(self):
        self.mod = _load_script("tools/lgwks-auth")
        self.tmp = Path(tempfile.mkdtemp())
        self.mod.VAULT_DIR = self.tmp
        self.mod.REGISTRY = self.tmp / "locks.jsonl"

    def test_bot_cannot_author_stale(self):
        with self.assertRaises(SystemExit):
            self.mod._append("stale", "x.com", by="sa-runner")

    def test_bot_may_append_used(self):
        rec = self.mod._append("used", "x.com", by="sa-runner", cred_ref="keychain://lgwks:x.com")
        self.assertEqual(rec["event"], "used")
        ok, _ = self.mod.verify_chain()
        self.assertTrue(ok)

    def test_chain_detects_tamper(self):
        self.mod._append("lock", "x.com", by="director", cred_ref="keychain://lgwks:x.com")
        self.mod._append("used", "x.com", by="sa-runner", cred_ref="keychain://lgwks:x.com")
        data = self.mod.REGISTRY.read_text().splitlines()
        import json
        rec = json.loads(data[0]); rec["site"] = "evil.com"; data[0] = json.dumps(rec)
        self.mod.REGISTRY.write_text("\n".join(data) + "\n")
        ok, msg = self.mod.verify_chain()
        self.assertFalse(ok)
        self.assertIn("broken", msg)


class TestAkinatorForm(unittest.TestCase):
    """L1/L9 — under-specified intent is unrepresentable; conduct returns a hard yes/no."""

    def _cli(self, *args, stdin=""):
        return subprocess.run([sys.executable, str(ROOT / "lgwks-akinator"), *args],
                              capture_output=True, text=True, input=stdin)

    def test_underspec_intent_blocked(self):
        out = self._cli("CRM", stdin="")  # objective present, purpose missing -> L1 blocks
        self.assertEqual(out.returncode, 2)
        self.assertIn("missing: purpose", out.stdout)

    def test_demo_conduct_yes(self):
        out = self._cli("--demo")
        self.assertIn("conduct (L9): YES", out.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
