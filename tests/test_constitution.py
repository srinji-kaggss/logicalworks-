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
import json
import os
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
    sys.modules[modname] = mod          # @dataclass resolves cls.__module__ via sys.modules
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
        env = {**os.environ, "LGWKS_NO_MODELS": "1"}   # hermetic: never call the live Tongue in tests
        return subprocess.run([sys.executable, str(ROOT / "lgwks-akinator"), *args],
                              capture_output=True, text=True, input=stdin, env=env)

    def test_underspec_intent_blocked(self):
        out = self._cli("CRM", stdin="")  # objective present, purpose missing -> L1 blocks
        self.assertEqual(out.returncode, 2)
        self.assertIn("missing: purpose", out.stdout)

    def test_demo_conduct_yes(self):
        out = self._cli("--demo")
        self.assertIn("conduct (L9): YES", out.stdout)


class TestHardeningFixes(unittest.TestCase):
    """Regressions for the hacker FAIL: C1 keyed chain, C2 verdict provenance, C3 redirect SSRF, L1 ranges."""

    def setUp(self):
        self.plan, self.syn = r._demo_plan(all_pass=True)
        self.tmp = Path(tempfile.mkdtemp())

    def test_C1_keyed_chain_detects_rewrite(self):
        key = b"secret-test-key"
        log = r.RunLog("t", None, key=key)
        log.append("a", {"x": 1}); log.append("b", {"y": 2})
        self.assertTrue(log.verify())
        # Attacker rewrites record AND recomputes hash — but without the secret key it cannot forge.
        rec = log.records[0]
        rec["data"]["x"] = 999
        import lgwks_sign as _sign
        core = json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
        rec["hash"] = _sign.mac(core + "0" * 64, b"WRONG-KEY")   # rewriter lacks the real key
        self.assertFalse(log.verify())

    def test_C2_forged_verdict_rejected_when_keyed(self):
        key = b"secret-test-key"
        # Forged: passed=True but no valid signature for this run_id.
        forged = tuple(r.GateVerdict(g, True, "", sig="deadbeef") for g in r.GATES_REQUIRED)
        plan = dataclasses.replace(self.plan, verdicts=forged)
        with self.assertRaises(r.GateError):
            r.assert_gates_clicked(plan, key, "keyed-env")
        # Properly signed by the admission verifier (uses r.sign_verdict → lgwks_sign HMAC) → accepted.
        signed = tuple(r.GateVerdict(g, True, "", sig=r.sign_verdict(plan.run_id, g, True, key))
                       for g in r.GATES_REQUIRED)
        plan2 = dataclasses.replace(self.plan, verdicts=signed)
        self.assertTrue(r.assert_gates_clicked(plan2, key, "keyed-env"))

    def test_C3_private_and_metadata_hosts_blocked(self):
        # Resolve-and-judge: literal private / loopback / metadata IPs are blocked.
        self.assertTrue(r.host_is_blocked("127.0.0.1"))
        self.assertTrue(r.host_is_blocked("169.254.169.254"))   # cloud metadata
        self.assertTrue(r.host_is_blocked("10.0.0.5"))
        self.assertTrue(r.host_is_blocked(""))

    def test_C3_redirect_off_scope_and_bad_scheme_refused(self):
        frozen = ("https://example.org/a",)
        self.assertTrue(r._allowed_hop("https://example.org/a", frozen))   # in scope
        self.assertFalse(r._allowed_hop("https://example.org/b", frozen))  # off-scope hop
        self.assertFalse(r._allowed_hop("file:///etc/passwd", frozen))     # non-http(s)
        self.assertFalse(r._allowed_hop("http://169.254.169.254/", frozen))# metadata (also off-scope)

    def test_C3_real_fetch_of_out_of_scope_is_blocked(self):
        # A non-dry fetch of a URL not in the frozen set never hits the network.
        res = r.fetch("https://example.org/not-declared", dry=False, synthetic=None,
                      frozen=("https://example.org/declared",))
        self.assertEqual(res.status, "error")
        self.assertIn("blocked", res.error)

    def test_L1_range_violations_rejected(self):
        mod = _load_script("lgwks-akinator")
        base = {"objective": "x" * 5, "purpose": "y" * 5, "tier_floor": "secondary", "risk_class": "read_only"}
        self.assertEqual(mod.gate_intent({**base, "max_pages": 12}), [])          # ok
        self.assertIn("max_pages", mod.gate_intent({**base, "max_pages": 5000}))   # > max 500
        self.assertIn("tier_floor", mod.gate_intent({**base, "tier_floor": "bogus"}))  # bad enum
        self.assertIn("objective", mod.gate_intent({**base, "objective": "x"}))    # under min_len


class TestUrlRiskCurator(unittest.TestCase):
    """G3 (L9 malware half): cherry-pick/block slugs on malware + corrupted-intent; granularity adapt."""

    def setUp(self):
        import lgwks_urlrisk as g
        self.g = g
        self.tmp = Path(tempfile.mkdtemp())

    def test_feed_hit_blocks(self):
        feed = self.tmp / "feed.txt"
        feed.write_text("evil.example\n", encoding="utf-8")
        c = self.g.curate_scope(["https://evil.example/x"], feed_path=feed)
        self.assertEqual(c.scored[0].decision, "block")
        self.assertEqual(c.scored[0].malware, 100.0)

    def test_benign_allowed_phishing_blocked(self):
        c = self.g.curate_scope([
            "https://arxiv.org/abs/2502.13347",
            "https://xn--paypl-secure.tk/wallet-unlock-verify",
        ])
        self.assertEqual(c.scored[0].decision, "allow")
        self.assertEqual(c.scored[1].decision, "block")

    def test_corrupted_intent_blocks_over_time(self):
        # A slug whose accumulated evidence is orthogonal to the declared intent is blocked.
        slug = self.g.slugify_target("https://benign.example/page")
        history = {slug: {"slug": slug, "evidence_vec": [0.0, 1.0], "runs": 4}}
        risk = self.g.score_slug("https://benign.example/page", intent_vec=[1.0, 0.0],
                                 feed=set(), history=history)
        self.assertEqual(risk.decision, "block")          # drift = 1 - cos = 1.0
        self.assertGreaterEqual(risk.intent_corruption, self.g.INTENT_CORRUPTION_BLOCK)

    def test_granularity_reduce_to_wildcard(self):
        urls = ["docs.google.com/a", "mail.google.com/b", "drive.google.com/c"]
        hist = {u: {"drift": 0.05} for u in urls}
        prop = self.g.adapt_granularity(urls, hist)
        self.assertIn("*.google.com", prop["reduce"])

    def test_evidence_accumulates(self):
        hp = self.tmp / "hist.jsonl"
        self.g.record_evidence("a.com/x", [1.0, 0.0], hp)
        self.g.record_evidence("a.com/x", [0.0, 1.0], hp)
        import json
        rec = json.loads(hp.read_text().splitlines()[0])
        self.assertEqual(rec["runs"], 2)


class TestAutonomousLoop(unittest.TestCase):
    """#9 Unit A — the autonomous loop must fail closed when the Tongue is offline, and its per-round
    ledger must be hash-chained (tamper-evident under a key)."""

    def setUp(self):
        import lgwks_research
        self.lr = lgwks_research

    def test_fails_closed_when_tongue_offline(self):
        # NO_MODELS forces cloud+local Tongue offline → the loop must stop at round 1, never fabricate.
        os.environ["LGWKS_NO_MODELS"] = "1"
        try:
            cfg = self.lr.AutoConfig(objective="x", purpose="why x", start="x", max_rounds=3)
            res = self.lr.run_auto(cfg, emit=lambda *_: None)
        finally:
            os.environ.pop("LGWKS_NO_MODELS", None)
        self.assertEqual(res.stop_reason, "tongue_offline")
        self.assertEqual(res.rounds, 1)

    def test_ledger_detects_tampering(self):
        import lgwks_sign
        key, _ = lgwks_sign.signing_key()
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "rounds.ledger.jsonl"
            prev = "genesis"
            with ledger.open("w") as lf:
                for n in (1, 2):
                    rec = {"n": n, "digest": f"d{n}", "prev": prev}
                    rec["hash"] = lgwks_sign.mac(prev + self.lr._canon(rec), key)
                    prev = rec["hash"]
                    lf.write(self.lr._canon(rec) + "\n")
            self.assertTrue(self.lr._verify_ledger(ledger, key))
            lines = ledger.read_text().splitlines()
            lines[0] = lines[0].replace('"d1"', '"TAMPERED"')
            ledger.write_text("\n".join(lines) + "\n")
            self.assertFalse(self.lr._verify_ledger(ledger, key))


class TestContextPack(unittest.TestCase):
    """#9 harness — LOD spawn-context: empty dir → empty; populated → tiers + state matrix + symlinks."""

    def setUp(self):
        import lgwks_context
        self.lc = lgwks_context

    def test_empty_when_no_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.lc.assemble(Path(d)), "")
            self.assertIsNone(self.lc.write_pack(Path(d)))

    def test_pack_has_tiers_and_matrix(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            with (rd / "rounds.ledger.jsonl").open("w") as lf:
                for n in (1, 2):
                    (rd / f"round-{n:03d}").mkdir()
                    (rd / f"round-{n:03d}" / "think.md").write_text(f"think {n}")
                    (rd / f"round-{n:03d}" / "reason.json").write_text("{}")
                    lf.write(json.dumps({"n": n, "frontier_in": "x", "surviving": ["H0"],
                                         "falsifiers_hit": [], "learnings": ["l"], "digest": "dg",
                                         "converged": False, "spent": n * 100}) + "\n")
            out = self.lc.write_pack(rd)
            self.assertIsNotNone(out)
            txt = out.read_text()
            self.assertIn("STATE MATRIX", txt)
            self.assertIn("TIER 0", txt)
            self.assertIn("TIER 3", txt)
            # raw symlink to the newest round exists and resolves
            link = rd / "CONTEXT" / "raw" / f"{rd.name}-R002.reason.json"
            self.assertTrue(link.is_symlink() and link.resolve().exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
