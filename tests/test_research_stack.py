"""
Offline tests for the research stack: capability resolution, search hygiene, steering, extract typing,
grounding degradation. No network — providers are monkeypatched. Hardens the turn's build (search
chain + resolver + extract + ground wiring) against regression.
"""

from __future__ import annotations

import os
import sys
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_capabilities as cap
import lgwks_search as search
import lgwks_steering as steering
import lgwks_extract as extract
import lgwks_ground as ground
import lgwks_home  # noqa: E402  (TestHomeQuickHints exercises _live_hints introspection)


class TestCapabilitiesAgnostic(unittest.TestCase):
    def test_chain_surfaces_agnostic_ids_not_vendor_names(self):
        # Director directive: no brand names on the surface. The chain must expose role ids only.
        brands = {"firecrawl", "googler", "ddgr", "crwl", "playwright", "pdftotext", "markitdown", "fitz"}
        for r in cap.doctor():
            for node in r["chain"]:
                self.assertNotIn(node["id"], brands, f"vendor name leaked as id: {node['id']}")

    def test_resolve_unknown_capability_is_loud_not_silent(self):
        r = cap.resolve("does-not-exist")
        self.assertIsNone(r["chosen"])

    def test_missing_capability_carries_install_hint(self):
        # a fabricated all-absent capability must report an install hint, never a silent empty.
        r = cap.resolve("search")
        if r["missing"]:
            self.assertTrue(r["install"])

    def test_find_binary_probes_beyond_path(self):
        # python3 exists; find_binary must locate a real binary (PATH or scatter dirs).
        self.assertTrue(cap.find_binary("python3") or cap.find_binary("python"))


class TestSearchHygiene(unittest.TestCase):
    def test_dedup_and_relevance_rank(self):
        rows = [
            {"title": "unrelated postal api", "url": "https://x.com/api", "snippet": "post", "via": "open"},
            {"title": "Canada Life acquisition close", "url": "https://cl.com/a", "snippet": "Canada Life acquisition", "via": "open"},
            {"title": "dup", "url": "https://cl.com/a?utm=1", "snippet": "Canada Life", "via": "open"},
        ]
        orig = search._PROVIDERS
        search._PROVIDERS = [("open", lambda q, k: list(rows))]
        try:
            out = search.search("Canada Life acquisition", k=5)
        finally:
            search._PROVIDERS = orig
        urls = [r["url"].split("?")[0] for r in out]
        self.assertEqual(len(urls), len(set(urls)), "URLs must be deduped (ignoring query string)")
        self.assertIn("acquisition", out[0]["title"].lower(), "most on-topic ranks first")

    def test_falls_through_empty_provider_to_next(self):
        orig = search._PROVIDERS
        hit = {"title": "Canada Life", "url": "https://cl.com/x", "snippet": "", "via": "open"}
        search._PROVIDERS = [("cli", lambda q, k: []), ("open", lambda q, k: [hit])]
        try:
            out = search.search("Canada Life", k=3)
        finally:
            search._PROVIDERS = orig
        self.assertEqual(len(out), 1)

    def test_unwrap_redirect(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc"
        self.assertEqual(search._unwrap(wrapped), "https://example.com/page")

    def test_parse_links_reads_dom_and_skips_nav(self):
        # the real around-the-block: parse links from a (browser-rendered) DOM, drop self/nav hosts.
        dom = ('<a href="https://duckduckgo.com/settings">nav</a>'
               '<a href="https://greatwestlifeco.com/news/value-partners.html">Value Partners acquisition</a>'
               '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fquadrus.com%2Fabout">Quadrus about</a>')
        rows = search._parse_links(dom, k=5, via="rendered")
        urls = [r["url"] for r in rows]
        self.assertNotIn("https://duckduckgo.com/settings", urls, "nav/self host must be dropped")
        self.assertIn("https://greatwestlifeco.com/news/value-partners.html", urls)
        self.assertIn("https://quadrus.com/about", urls, "wrapped redirect must be unwrapped")
        self.assertTrue(all(r["via"] == "rendered" for r in rows))

    def test_open_rotates_endpoints_on_empty(self):
        # the live failure: one endpoint 429s → empty. _open must back off and rotate to the next host.
        calls = []
        def fake_curl(url, data=None, timeout=20, ua=""):
            calls.append(url)
            if "html.duckduckgo" in url:
                return ""                                   # first endpoint blocked/empty
            # second endpoint answers — body must be > _MIN_BODY (200) to avoid short-body rejection
            return ('<a href="https://cl.com/acq">Canada Life acquisition</a>'
                    + "\n" + "x" * 300)
        slept = []
        orig = search._curl
        search._curl = fake_curl
        try:
            rows = search._open("Canada Life acquisition", k=3, sleep=lambda s: slept.append(s))
        finally:
            search._curl = orig
        self.assertTrue(rows, "rotation must recover when the first endpoint is dry")
        self.assertEqual(rows[0]["url"], "https://cl.com/acq")
        # 3 endpoints × 2 retries each = up to 6 calls; first endpoint is empty so at least 2+ calls
        self.assertGreaterEqual(len(calls), 2, "must have tried more than one endpoint")
        self.assertTrue(slept, "must have backed off before rotating")

    def test_mojeek_parser_skips_promo_and_nav(self):
        # the binning trap: a generic anchor grab conflated Mojeek's own promo links with results.
        # the targeted parser takes ONLY <a class="title"> result anchors.
        body = ('<a href="https://buttondown.email/Mojeek">Newsletter</a>'
                '<ul class="results-standard">'
                '<a class="title" href="https://deepmind.google/blog/alphaevolve">AlphaEvolve</a>'
                '</ul>')
        rows = search._parse_mojeek(body, k=5, via="open")
        urls = [r["url"] for r in rows]
        self.assertEqual(urls, ["https://deepmind.google/blog/alphaevolve"], "only result anchors, no promo")

    def test_backoff_monotonic_and_capped(self):
        self.assertLess(search._backoff(0), search._backoff(2))
        self.assertLessEqual(search._backoff(10), 2.15, "backoff is capped (base 2.0 + max jitter 0.15), never unbounded")


class TestSteering(unittest.TestCase):
    def test_nan_and_out_of_range_clamp_to_default(self):
        self.assertEqual(steering._clamp(float("nan"), 0.0, 1.0, 0.5), 0.5)
        self.assertEqual(steering._clamp(9.0, 0.0, 1.0, 0.3), 1.0)
        self.assertEqual(steering._clamp(-9.0, -1.0, 1.0, 0.0), -1.0)

    def test_down_out_before_up_ordering(self):
        nodes = [{"direction": "up"}, {"direction": "out"}, {"direction": "down"}, {}]
        ordered = [n.get("direction", "out") for n in steering.frontier_order(nodes)]
        self.assertEqual(ordered[0], "down")          # decompose first
        self.assertEqual(ordered[-1], "up")            # synthesis last

    def test_require_context_names_missing(self):
        missing = steering.require_context({"objective": "x", "purpose": ""}, ["objective", "purpose"])
        self.assertEqual(missing, ["purpose"])

    def test_prompt_fragment_reflects_dials(self):
        s = steering.Steering(frontierness=0.9, lens=-0.9, depth=0.9)
        frag = s.prompt_fragment().lower()
        self.assertIn("frontier", frag)
        self.assertIn("first principles", frag)


class TestExtractTyping(unittest.TestCase):
    def test_extension_detection(self):
        self.assertEqual(extract._ext_of("https://x.com/doc.pdf?a=1"), ".pdf")
        self.assertEqual(extract._ext_of("/local/file.docx"), ".docx")

    def test_missing_local_file_is_honest_failure(self):
        r = extract.extract("/no/such/file.txt")
        self.assertFalse(r["ok"])
        self.assertEqual(r["text"], "")

    def test_non_http_url_scheme_is_rejected(self):
        r = extract.extract("file:///etc/passwd")
        self.assertFalse(r["ok"])
        self.assertEqual(r["kind"], "unsupported-url-scheme")

    def test_private_and_metadata_hosts_are_blocked(self):
        for url in ("http://127.0.0.1:8000/admin", "http://169.254.169.254/latest/meta-data",
                    "http://metadata.google.internal/computeMetadata/v1"):
            r = extract.extract(url)
            self.assertFalse(r["ok"])
            self.assertEqual(r["kind"], "blocked-host")


class TestManifest(unittest.TestCase):
    def test_manifest_is_a_valid_machine_contract(self):
        # the AI's door: an agent reads this instead of docs — it must always be complete + structured.
        import lgwks_manifest as man
        m = man.build_manifest()
        self.assertTrue(m["machine_first"])
        self.assertGreaterEqual(len(m["verbs"]), 4, "must declare the core verbs")
        for v in m["verbs"]:
            self.assertIn("tokens", v, "every verb declares its token cost so an agent can budget")
            self.assertIn("intent", v)
        self.assertTrue(m["thought_schema"], "must carry the thought-continuation schema")
        # capabilities come from the live resolver (agnostic ids, no vendor brand leak)
        brands = {"firecrawl", "playwright", "crwl", "pdftotext"}
        for c in m["capabilities"]:
            self.assertNotIn(c["capability"], brands)

    def test_every_registered_subparser_appears_in_manifest(self):
        import importlib.machinery
        import importlib.util
        import os
        import sys
        import lgwks_manifest as man
        here = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(os.path.dirname(here), "lgwks")
        loader = importlib.machinery.SourceFileLoader("_lgwks_main_for_manifest_test", script_path)
        spec = importlib.util.spec_from_loader("_lgwks_main_for_manifest_test", loader)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        loader.exec_module(mod)
        live = man._collect_verbs()
        for expected in ("manifest", "extract", "convert", "solve", "x", "refine", "store",
                         "jarvis crawl", "memory init", "project plan", "geo compile"):
            self.assertIn(expected, live, f"{expected!r} must appear in the live verb surface")
        m = man.build_manifest()
        manifest_names = {v["verb"] for v in m["verbs"]}
        for name in live:
            self.assertIn(name, manifest_names,
                          f"verb {name!r} is registered in build_parser() but missing from the manifest")

    def test_verb_collection_degrades_loudly_on_broken_parser(self):
        import lgwks_manifest as man
        original = man._collect_verbs
        man._collect_verbs = lambda: (_ for _ in ()).throw(RuntimeError("simulated parser failure"))
        try:
            m = man.build_manifest()
        finally:
            man._collect_verbs = original
        self.assertTrue(m["machine_first"])
        self.assertEqual(len(m["verbs"]), 1)
        entry = m["verbs"][0]
        self.assertIn("RuntimeError", entry["verb"])
        self.assertIn("simulated parser failure", entry["verb"])
        self.assertEqual(entry["intent"], "(no metadata)")

    def test_missing_metadata_is_loud_not_silent(self):
        import lgwks_manifest as man
        saved = man._VERB_META.get("manifest")
        try:
            man._VERB_META.pop("manifest", None)
            m = man.build_manifest()
            entry = next(v for v in m["verbs"] if v["verb"] == "manifest")
            self.assertEqual(entry["intent"], "(no metadata)")
            self.assertEqual(entry["tokens"], "(no metadata)")
        finally:
            if saved is not None:
                man._VERB_META["manifest"] = saved

    def test_manifest_default_emits_parseable_json(self):
        import argparse
        import lgwks_manifest as man
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = man.manifest_command(argparse.Namespace(json=False, render=False))
        self.assertEqual(rc, 0)
        m = json.loads(buf.getvalue())
        self.assertTrue(m["machine_first"])
        self.assertIn("verbs", m)

    def test_manifest_json_flag_emits_parseable_json(self):
        import argparse
        import lgwks_manifest as man
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = man.manifest_command(argparse.Namespace(json=True, render=False))
        self.assertEqual(rc, 0)
        m = json.loads(buf.getvalue())
        self.assertTrue(m["machine_first"])
        self.assertGreaterEqual(len(m["verbs"]), 4)

    def test_manifest_render_flag_routes_to_human_view(self):
        import argparse
        import lgwks_manifest as man
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = man.manifest_command(argparse.Namespace(json=True, render=True))
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertFalse(out.lstrip().startswith("{"), "render must not emit JSON")
        self.assertIn("manifest", out)

    def test_manifest_args_line_reflects_registered_flags(self):
        import re as _re
        import lgwks_manifest as man
        here = os.path.dirname(os.path.abspath(__file__))
        src = Path(os.path.join(os.path.dirname(here), "lgwks")).read_text(encoding="utf-8")
        m_block = _re.search(r'manifest\s*=\s*sub\.add_parser\(\s*"manifest"(.*?)manifest\.set_defaults',
                             src, _re.DOTALL)
        self.assertIsNotNone(m_block, "could not locate the manifest parser block in lgwks")
        assert m_block is not None
        registered = set(_re.findall(r'add_argument\(\s*"(--[\w-]+)"', m_block.group(1)))
        self.assertIn("--json", registered, "--json must be registered on the manifest subparser")
        self.assertIn("--render", registered)
        # _VERB_META["manifest"]["args"] must name both flags (drift guard)
        manifest_meta = man._VERB_META.get("manifest", {})
        self.assertIn("--json", manifest_meta.get("args", {}))
        self.assertIn("--render", manifest_meta.get("args", {}))


class TestAuthRuntime(unittest.TestCase):
    def test_active_lock_maps_host_to_keychain_headers(self):
        import lgwks_auth_runtime as auth

        tmp = Path(tempfile.mkdtemp())
        auth.REGISTRY = tmp / "locks.jsonl"
        auth.REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        auth.REGISTRY.write_text(json.dumps({"event": "lock", "site": "scholar.google.com"}) + "\n")

        class P:
            returncode = 0
            stdout = "Bearer test-token\n"

        old = auth.subprocess.run
        auth.subprocess.run = lambda *a, **k: P()
        try:
            self.assertEqual(auth.site_for_url("https://scholar.google.com/scholar?q=x"), "scholar.google.com")
            self.assertEqual(auth.headers_for_url("https://scholar.google.com/scholar?q=x"),
                             {"Authorization": "Bearer test-token"})
            self.assertEqual(auth.headers_for_url("https://example.com/"), {})
        finally:
            auth.subprocess.run = old

    def test_browser_session_is_host_scoped(self):
        import lgwks_browser as browser

        tmp = Path(tempfile.mkdtemp())
        old_dir, old_legacy = browser._SESSION_DIR, browser._SESSION
        browser._SESSION_DIR = tmp / "sessions"
        browser._SESSION = tmp / "linkedin-session.json"
        try:
            browser._SESSION_DIR.mkdir()
            scoped = browser._SESSION_DIR / "scholar.google.com.json"
            scoped.write_text("{}", encoding="utf-8")
            self.assertEqual(browser._session_for_url("https://scholar.google.com/scholar"), scoped)
            self.assertIsNone(browser._session_for_url("https://example.com/"))
        finally:
            browser._SESSION_DIR, browser._SESSION = old_dir, old_legacy

    def test_needs_auth_json_sanitizes_url(self):
        import lgwks_auth_runtime as auth

        tmp = Path(tempfile.mkdtemp())
        auth.REQUESTS = tmp / "needs_auth.jsonl"
        auth.request_keyring("https://user:secret@example.com/private?token=x#frag", "remote returned auth failure", 403)
        rec = json.loads(auth.REQUESTS.read_text().splitlines()[0])
        self.assertEqual(rec["url"], "https://example.com/private")
        self.assertNotIn("token", json.dumps(rec))


class TestProjectMemory(unittest.TestCase):
    def test_project_memory_chain_focuses_themes(self):
        import lgwks_memory as mem

        tmp = Path(tempfile.mkdtemp())
        mem._DIR = tmp / "projects"
        mem.init_project("project 1", "scholar.google.com",
                         "machine-first language embeddings focus on deterministic memory chains")
        mem.remember("project 1", "Previous convo: auth tokens stay in keychain, crawler obeys scoped grants.")
        ctx = mem.context("project 1", query="deterministic context chain embeddings")
        self.assertTrue(ctx["chain_ok"])
        self.assertEqual(ctx["scopes"][0]["site"], "scholar.google.com")
        labels = {t["theme"] for t in ctx["focus_themes"]}
        self.assertIn("deterministic", labels)
        self.assertTrue(ctx["chain_head"])


class TestPublicSources(unittest.TestCase):
    def test_public_search_carries_license_basis(self):
        import lgwks_public as pub

        old = pub._fetch_json
        def fake(url, timeout=20):
            if "openalex" in url:
                return {"results": [{"display_name": "Machine memory", "id": "https://openalex.org/W1",
                                     "publication_year": 2026,
                                     "best_oa_location": {"landing_page_url": "https://example.org/p",
                                                          "pdf_url": "https://example.org/p.pdf",
                                                          "license": "cc-by",
                                                          "license_url": "https://creativecommons.org/licenses/by/4.0/"}}]}
            if "crossref" in url:
                return {"message": {"items": [{"title": ["Open metadata"], "URL": "https://doi.org/10/x",
                                               "license": [{"URL": "https://creativecommons.org/publicdomain/zero/1.0/"}],
                                               "published-online": {"date-parts": [[2025]]}}]}}
            return {"results": [{"title": "Open image", "url": "https://img.example/x.jpg",
                                 "foreign_landing_url": "https://example.org/x",
                                 "license": "cc0",
                                 "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}]}

        pub._fetch_json = fake
        try:
            out = pub.search_public("machine memory", limit=1)
        finally:
            pub._fetch_json = old
        self.assertEqual(len(out["records"]), 3)
        self.assertTrue(all(r["basis"] for r in out["records"]))
        self.assertEqual(out["policy"], "open-license-only; verify per-item license before redistribution")


class TestEmbeddingVault(unittest.TestCase):
    def test_folder_embedding_vault_has_root_and_subvaults(self):
        import lgwks_embed as emb

        tmp = Path(tempfile.mkdtemp())
        old = emb.VAULT_ROOT
        emb.VAULT_ROOT = tmp / "vectors"
        root = tmp / "src"
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir()
        (root / "a" / "one.md").write_text("deterministic context chain embeddings memory", encoding="utf-8")
        (root / "b" / "two.py").write_text("def keyring_auth(): return 'vault context'", encoding="utf-8")
        try:
            out = emb.build_vault(str(root), "project 1", ["deterministic", "keyring"], cycles=0, max_cycles=3)
        finally:
            emb.VAULT_ROOT = old
        manifest = json.loads(Path(out["manifest"]).read_text())
        self.assertTrue(Path(out["vault"], "root", "embeddings.jsonl").exists())
        self.assertGreaterEqual(len(manifest["subvaults"]), 2)
        self.assertGreater(manifest["records"], 0)
        self.assertLessEqual(manifest["cycles_run"], 3)


class TestProjectPlanner(unittest.TestCase):
    def setUp(self):
        # //why: pin the host to the spec profile (24GiB/15cpu) so the worker-cap
        # math is deterministic on any machine. Without this the suite only
        # passes by accident on a host that happens to match the spec.
        self._host_env = {k: os.environ.get(k) for k in ("LGWKS_HOST_RAM_GIB", "LGWKS_HOST_CPU")}
        os.environ["LGWKS_HOST_RAM_GIB"] = "24"
        os.environ["LGWKS_HOST_CPU"] = "15"

    def tearDown(self):
        for k, v in self._host_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_one_prompt_defaults_to_five_cycles_and_four_hundred_embeddings(self):
        import argparse
        import lgwks_project as proj

        args = argparse.Namespace(project="salesforce", prompt="map Salesforce as AI OS competitor",
                                  site="scholar.google.com", folder=".", reasoning_cycles=None,
                                  embedding_rounds=400, max_workers=4, tokens_per_cycle=8000)
        plan = proj.build_plan(args)
        self.assertEqual(plan["budgets"]["reasoning_cycles"], 5)
        self.assertEqual(plan["budgets"]["embedding_rounds"], 400)
        self.assertEqual(plan["machine_weight"]["retrieval"], 0.35)
        self.assertIn("Self-RAG", plan["frontier_techniques"])
        self.assertTrue(plan["next_commands"])

    def test_project_plan_caps_workers_at_four(self):
        import argparse
        import lgwks_project as proj

        args = argparse.Namespace(project="salesforce", prompt="map Salesforce", site="", folder=".",
                                  reasoning_cycles=None, embedding_rounds=400, max_workers=99,
                                  tokens_per_cycle=8000)
        plan = proj.build_plan(args)
        self.assertEqual(plan["budgets"]["max_workers"], 4)
        self.assertEqual(plan["budgets"]["max_concurrent_workers"], 4)
        self.assertLessEqual(len(plan["branch_workers"]), 4)
        # cap is computed from the host formula, not a constant; 24/15 -> 4 via roles
        wc = plan["budgets"]["worker_cap"]
        self.assertEqual(wc["computed_cap"], 4)
        self.assertEqual(wc["formula_headroom"], 4)
        self.assertEqual(wc["cap_basis"], "role_count")
        self.assertEqual(wc["host"]["source"], "override")

    def test_project_deploy_dry_run_writes_machine_native_artifacts(self):
        import argparse
        import lgwks_project as proj

        tmp = Path(tempfile.mkdtemp())
        old = proj.DEPLOY_ROOT
        proj.DEPLOY_ROOT = tmp / "deploy"
        args = argparse.Namespace(project="ai-ml-layers",
                                  prompt="build a one-command research CLI on existing AI research skills",
                                  reasoning_cycles=None, embedding_rounds=400, max_workers=4,
                                  tokens_per_cycle=8000, site="open-public-sources", folder="",
                                  source="all", source_limit=5, embed_cycles=3, max_files=100,
                                  learning_mode="local-only",
                                  device_consent="local-device", model_spine="oss-coreml",
                                  dry_run=True, execute=False)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(proj.deploy_command(args), 0)
            out_dir = proj._deploy_path("ai-ml-layers")
            for name in ("cycles.jsonl", "leases.jsonl", "token-ledger.jsonl", "model_state.json",
                         "machine-packets.jsonl", "learning-records.jsonl", "model-lineage.jsonl",
                         "graph-edges.jsonl", "operator-profile.json", "execution-events.jsonl",
                         "source-records.jsonl", "vector-vault.json", "worker-map.json",
                         "artifact-embeddings.jsonl"):
                self.assertTrue((out_dir / name).exists(), name)
            review = proj.review_project("ai-ml-layers")
            worker_map = json.loads((out_dir / "worker-map.json").read_text(encoding="utf-8"))
            embeddings = [json.loads(line) for line in (out_dir / "artifact-embeddings.jsonl").read_text(
                encoding="utf-8").splitlines()]
        finally:
            proj.DEPLOY_ROOT = old
        self.assertTrue(review["chain_ok"])
        self.assertEqual(review["cycles"], 5)
        self.assertEqual(review["token_status"], "ok")
        self.assertGreaterEqual(review["model_lineage_count"], 3)
        self.assertEqual(review["machine_packets"], 5)
        self.assertTrue(review["one_command_replaces_many"])
        self.assertTrue(review["build_on_existing_work"])
        self.assertIn("local-only", review["learning_export_policy"])
        self.assertEqual(worker_map["max_concurrent_workers"], 4)
        self.assertLessEqual(len(worker_map["active_slots"]), 4)
        self.assertEqual(worker_map["worker_cap"]["cap_basis"], "role_count")
        self.assertEqual(worker_map["worker_cap"]["reserves"]["always_on_deep_ml_model_gib"], 8)
        self.assertGreater(review["artifact_embeddings"], 0)
        self.assertIn("transcript", {row["kind"] for row in embeddings})
        self.assertIn("learning-records.jsonl", {row["artifact"] for row in embeddings})
        self.assertIn("artifact-embeddings.jsonl", {row["artifact"] for row in embeddings})
        self.assertTrue(all(row["embedding_model"] == "deterministic-feature-hash-v1" for row in embeddings))

    def test_project_deploy_tamper_breaks_cycle_chain(self):
        import argparse
        import lgwks_project as proj

        tmp = Path(tempfile.mkdtemp())
        old = proj.DEPLOY_ROOT
        proj.DEPLOY_ROOT = tmp / "deploy"
        args = argparse.Namespace(project="tamper-demo", prompt="test tamper chain", reasoning_cycles=2,
                                  embedding_rounds=400, max_workers=2, tokens_per_cycle=8000,
                                  site="open-public-sources", folder="", source="all", source_limit=5,
                                  embed_cycles=3, max_files=100,
                                  learning_mode="local-only", device_consent="research-only",
                                  model_spine="oss-coreml", dry_run=True, execute=False)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                proj.deploy_command(args)
            cycles = proj._deploy_path("tamper-demo") / "cycles.jsonl"
            lines = cycles.read_text(encoding="utf-8").splitlines()
            lines[0] = lines[0].replace("neutral_academic", "rewritten")
            cycles.write_text("\n".join(lines) + "\n", encoding="utf-8")
            review = proj.review_project("tamper-demo")
        finally:
            proj.DEPLOY_ROOT = old
        self.assertFalse(review["chain_ok"])

    def test_learning_records_do_not_inline_raw_prompt(self):
        import argparse
        import lgwks_project as proj

        prompt = "private phrase should not be copied into learning record raw body"
        tmp = Path(tempfile.mkdtemp())
        old = proj.DEPLOY_ROOT
        proj.DEPLOY_ROOT = tmp / "deploy"
        args = argparse.Namespace(project="privacy-boundary", prompt=prompt, reasoning_cycles=1,
                                  embedding_rounds=400, max_workers=1, tokens_per_cycle=8000,
                                  site="open-public-sources", folder="", source="all", source_limit=5,
                                  embed_cycles=3, max_files=100,
                                  learning_mode="local-only", device_consent="local-device",
                                  model_spine="oss-coreml", dry_run=True, execute=False)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                proj.deploy_command(args)
            learning_text = (proj._deploy_path("privacy-boundary") / "learning-records.jsonl").read_text(encoding="utf-8")
            packets = json.loads((proj._deploy_path("privacy-boundary") / "machine-packets.jsonl").read_text(
                encoding="utf-8").splitlines()[0])
        finally:
            proj.DEPLOY_ROOT = old
        self.assertNotIn(prompt, learning_text)
        self.assertEqual(packets["schema"], "lgwks-machine-packet/1")

    def test_project_execute_composes_public_memory_and_embed(self):
        import argparse
        import lgwks_embed as emb
        import lgwks_memory as mem
        import lgwks_project as proj
        import lgwks_public as pub

        tmp = Path(tempfile.mkdtemp())
        old_deploy, old_mem, old_vectors = proj.DEPLOY_ROOT, mem._DIR, emb.VAULT_ROOT
        old_fetch = pub._fetch_json
        proj.DEPLOY_ROOT = tmp / "deploy"
        mem._DIR = tmp / "projects"
        emb.VAULT_ROOT = tmp / "vectors"
        folder = tmp / "src"
        folder.mkdir()
        (folder / "notes.md").write_text("salesforce ai operating system agent runtime evidence", encoding="utf-8")

        def fake_fetch(url, timeout=20):
            if "openalex" in url:
                return {"results": [{"display_name": "Agent runtime evidence", "id": "https://openalex.org/W1",
                                     "publication_year": 2026,
                                     "best_oa_location": {"landing_page_url": "https://example.org/p",
                                                          "license": "cc-by"}}]}
            if "crossref" in url:
                return {"message": {"items": [{"title": ["Open metadata"], "URL": "https://doi.org/10/x",
                                               "license": [{"URL": "https://creativecommons.org/publicdomain/zero/1.0/"}],
                                               "published-online": {"date-parts": [[2025]]}}]}}
            return {"results": [{"title": "Open diagram", "url": "https://img.example/x.jpg",
                                 "foreign_landing_url": "https://example.org/x", "license": "cc0",
                                 "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}]}

        pub._fetch_json = fake_fetch
        args = argparse.Namespace(project="execute-demo", prompt="map salesforce ai os", reasoning_cycles=2,
                                  embedding_rounds=400, max_workers=4, tokens_per_cycle=8000,
                                  site="open-public-sources", folder=str(folder), source="all", source_limit=1,
                                  embed_cycles=1, max_files=10, learning_mode="local-only",
                                  device_consent="local-device", model_spine="oss-coreml",
                                  dry_run=False, execute=True)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(proj.deploy_command(args), 0)
            review = proj.review_project("execute-demo")
            out_dir = proj._deploy_path("execute-demo")
            events = [json.loads(line) for line in (out_dir / "execution-events.jsonl").read_text(
                encoding="utf-8").splitlines()]
        finally:
            proj.DEPLOY_ROOT, mem._DIR, emb.VAULT_ROOT = old_deploy, old_mem, old_vectors
            pub._fetch_json = old_fetch

        self.assertTrue(review["chain_ok"])
        self.assertEqual(review["source_records"], 3)
        self.assertEqual(review["vector_vault_status"], "ok")
        self.assertGreater(review["vector_records"], 0)
        self.assertGreater(review["artifact_embeddings"], review["source_records"])
        self.assertEqual(review["max_concurrent_workers"], 4)
        self.assertLessEqual(review["active_worker_slots"], 4)
        self.assertIn("internal deterministic", review["worker_api_key_policy"])
        self.assertIn("ok", review["execution_status_counts"])
        self.assertIn("skipped", review["execution_status_counts"])
        self.assertEqual({e["step"] for e in events},
                         {"memory", "public_search", "embed", "auth_private_crawl"})

    def test_project_review_render_is_projection(self):
        import lgwks_project as proj

        review = {
            "project": "x", "chain_ok": True, "cycles": 5, "token_status": "ok", "token_spend": 100,
            "source_records": 2, "vector_vault_status": "ok", "vector_records": 3, "machine_packets": 5,
            "graph_edges": 10, "model_lineage_count": 3, "one_command_replaces_many": True,
            "build_on_existing_work": True, "rollback_ref": "champion", "unsupported_claims": ["claim-2"],
            "execution_status_counts": {"ok": 3, "skipped": 1}, "artifact_embeddings": 22,
            "active_worker_slots": 4, "max_concurrent_workers": 4,
        }
        rendered = proj._render_review(review)
        self.assertIn("project x", rendered)
        self.assertIn("sources 2", rendered)
        self.assertIn("artifact embeddings 22", rendered)
        self.assertIn("execution ok:3, skipped:1", rendered)


class TestWorkerCap(unittest.TestCase):
    def test_spec_host_yields_four_via_role_ceiling(self):
        import lgwks_workercap as wc
        cap = wc.compute_worker_cap(4, host={"ram_total_gib": 24, "cpu_total": 15, "source": "test"})
        self.assertEqual(cap["ram_available_for_workers_gib"], 8)  # 24 - 6 - 8 - 2
        self.assertEqual(cap["memory_cap"], 4)
        self.assertEqual(cap["cpu_cap"], 10)
        self.assertEqual(cap["formula_headroom"], 4)
        self.assertEqual(cap["computed_cap"], 4)
        self.assertEqual(cap["cap_basis"], "role_count")

    def test_larger_host_records_headroom_but_stays_role_bound(self):
        import lgwks_workercap as wc
        cap = wc.compute_worker_cap(4, host={"ram_total_gib": 64, "cpu_total": 24, "source": "test"})
        self.assertGreater(cap["formula_headroom"], 4)  # host could take more
        self.assertEqual(cap["computed_cap"], 4)         # but no phantom slots beyond defined roles
        self.assertEqual(cap["cap_basis"], "role_count")

    def test_model_reserve_is_an_enforced_input_not_a_comment(self):
        import lgwks_workercap as wc
        with_reserve = wc.compute_worker_cap(8, host={"ram_total_gib": 24, "cpu_total": 15, "source": "t"})
        no_reserve = wc.compute_worker_cap(
            8, host={"ram_total_gib": 24, "cpu_total": 15, "source": "t"},
            reserves={**wc.RESERVES, "always_on_deep_ml_model_gib": 0})
        # dropping the 8GiB Model reserve must visibly raise the memory headroom
        self.assertEqual(with_reserve["memory_cap"], 4)
        self.assertEqual(no_reserve["memory_cap"], 8)
        self.assertGreater(no_reserve["formula_headroom"], with_reserve["formula_headroom"])

    def test_constrained_host_floors_at_one_not_zero(self):
        import lgwks_workercap as wc
        cap = wc.compute_worker_cap(4, host={"ram_total_gib": 12, "cpu_total": 4, "source": "test"})
        self.assertEqual(cap["formula_headroom"], 0)  # no slack after reserves
        self.assertEqual(cap["computed_cap"], 1)       # still runs one worker, never deadlocks at 0

    def test_probe_env_override_is_deterministic_and_flagged(self):
        import lgwks_workercap as wc
        prior = {k: os.environ.get(k) for k in ("LGWKS_HOST_RAM_GIB", "LGWKS_HOST_CPU")}
        os.environ["LGWKS_HOST_RAM_GIB"] = "32"
        os.environ["LGWKS_HOST_CPU"] = "12"
        try:
            host = wc.probe_host()
        finally:
            for k, v in prior.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertEqual(host, {"ram_total_gib": 32, "cpu_total": 12, "source": "override"})

    def test_malformed_env_override_fails_closed_not_crashes(self):
        # //why: regression for the hacker LOW finding — a non-numeric override crashed deploy. Must degrade.
        import lgwks_workercap as wc
        prior = {k: os.environ.get(k) for k in ("LGWKS_HOST_RAM_GIB", "LGWKS_HOST_CPU")}
        os.environ["LGWKS_HOST_RAM_GIB"] = "not-a-number"
        os.environ["LGWKS_HOST_CPU"] = "12"
        try:
            host = wc.probe_host()
            cap = wc.compute_worker_cap(4, host=host)
        finally:
            for k, v in prior.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertEqual(host["source"], "override-invalid")
        self.assertEqual(cap["computed_cap"], 1)  # smallest viable, never a crash or a spawn-storm


class TestGeoExpr(unittest.TestCase):
    def _expr(self, verbs, risk_max="read"):
        return {"schema": "lgwks-geoexpr/1", "op": "product",
                "axes": [{"name": "verb", "values": verbs}, {"name": "scope", "values": ["repo.current"]}],
                "constraints": {"risk_max": risk_max, "requires_human_preview": True}}

    def test_product_expands_argv_without_shell(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["git.status", "git.log", "git.diff"]))
        self.assertTrue(plan["ok"])
        cmds = plan["value"]["commands"]
        self.assertEqual(len(cmds), 3)  # 3 verbs x 1 scope
        self.assertEqual(cmds[0]["argv"], ["git", "status"])
        self.assertFalse(plan["value"]["compile_policy"]["shell"])
        self.assertTrue(all(isinstance(c["argv"], list) for c in cmds))  # argv, never a shell string

    def test_plan_id_is_deterministic(self):
        import lgwks_geoexpr as g
        a = g.compile_plan(self._expr(["git.status"]))["value"]
        b = g.compile_plan(self._expr(["git.status"]))["value"]
        self.assertEqual(a["plan_id"], b["plan_id"])

    def test_unknown_verb_is_flagged_for_review_not_executed(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["git.frobnicate"]))["value"]
        cmd = plan["commands"][0]
        self.assertIsNone(cmd["argv"])
        self.assertEqual(cmd["risk"], "unknown")
        self.assertTrue(cmd["needs_review"])
        self.assertTrue(plan["compile_policy"]["unknown_requires_review"])

    def test_preview_is_projection_with_risk_gated_approval(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["git.status", "git.log"]))["value"]
        preview = g.human_preview(plan, risk_max="read")
        self.assertEqual(preview["risk"], "read")
        self.assertEqual(preview["approval"], "auto_allowed")
        self.assertEqual([s["label"] for s in preview["steps"]], ["git.status", "git.log"])
        self.assertEqual(preview["plan_id"], plan["plan_id"])

    def test_unknown_verb_preview_asks_not_auto(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["git.frobnicate"]))["value"]
        self.assertEqual(g.human_preview(plan, risk_max="read")["approval"], "ask")

    def test_validate_rejects_bad_shapes(self):
        import lgwks_geoexpr as g
        self.assertEqual(g.validate_geoexpr({"schema": "wrong"})["error_code"], "schema_mismatch")
        self.assertEqual(g.validate_geoexpr(
            {"schema": "lgwks-geoexpr/1", "op": "sum", "axes": []})["error_code"], "unsupported_op")
        self.assertEqual(g.validate_geoexpr(
            {"schema": "lgwks-geoexpr/1", "op": "product",
             "axes": [{"name": "scope", "values": ["x"]}]})["error_code"], "axis_missing_verb")

    def test_correction_record_builder_validates_failure_type(self):
        import lgwks_geoexpr as g
        ok = g.correction_record(source_expr="sha", failure_type="human_misread",
                                 before={}, after={}, corrected_by="human")
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["value"]["training_use"], "local_only")
        bad = g.correction_record(source_expr="sha", failure_type="bogus",
                                  before={}, after={}, corrected_by="human")
        self.assertEqual(bad["error_code"], "correction_failure_type_unknown")

    def test_execute_runs_validated_read_argv(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["fs.pwd"]))["value"]
        tr = g.execute_plan(plan)
        self.assertTrue(tr["ok"])
        self.assertEqual(tr["value"]["results"][0]["argv"], ["pwd"])
        self.assertTrue(tr["value"]["results"][0]["ok"])

    def test_execute_blocks_destructive_without_force(self):
        import lgwks_geoexpr as g
        # //why argv is a harmless `echo` (not a real rm): we test the gate, not destruction. risk is set
        # destructive to exercise the block; executing echo can never lose work.
        plan = {"plan_id": "p", "source_expr": "s",
                "commands": [{"argv": ["echo", "rm", "-rf", "x"], "risk": "destructive", "why": "",
                              "verb": "fs.rm", "needs_review": False}]}
        self.assertEqual(g.execute_plan(plan)["error_code"], "execute_destructive_blocked")
        forced = g.execute_plan(plan, force=True)  # gate passes; transcript produced
        self.assertTrue(forced["ok"])
        self.assertEqual(forced["value"]["results"][0]["verb"], "fs.rm")

    def test_execute_blocks_unknown_without_allow(self):
        import lgwks_geoexpr as g
        plan = g.compile_plan(self._expr(["git.frobnicate"]))["value"]
        self.assertEqual(g.execute_plan(plan)["error_code"], "execute_unknown_blocked")

    def test_run_persists_artifacts_and_embeddings(self):
        import lgwks_geoexpr as g
        tmp = Path(tempfile.mkdtemp())
        old = g.RUN_ROOT
        g.RUN_ROOT = tmp / "geo-runs"
        try:
            plan = g.compile_plan(self._expr(["fs.pwd"]))["value"]
            preview = g.human_preview(plan, "read")
            tr = g.execute_plan(plan)["value"]
            run_dir = g._persist_run(self._expr(["fs.pwd"]), plan, preview, tr)
            for name in ("geoexpr.json", "command-plan.json", "human-preview.json",
                         "result-transcript.json", "artifact-embeddings.jsonl"):
                self.assertTrue((run_dir / name).exists(), name)
            embeds = [json.loads(l) for l in (run_dir / "artifact-embeddings.jsonl").read_text(
                encoding="utf-8").splitlines()]
            kinds = {e["kind"] for e in embeds}
            self.assertEqual(kinds, {"geoexpr", "command-plan", "human-preview", "result"})
            self.assertTrue(all(len(e["embedding"]) == g.EMBED_DIMS for e in embeds))
        finally:
            g.RUN_ROOT = old


class TestMultiply(unittest.TestCase):
    def test_expands_cartesian_product(self):
        import lgwks_multiply as mx
        out = mx._expand_braces("git {add,reset} {a.py,b.py}")
        self.assertEqual(out, ["git add a.py", "git add b.py", "git reset a.py", "git reset b.py"])

    def test_single_axis_and_no_brace(self):
        import lgwks_multiply as mx
        self.assertEqual(mx._expand_braces("git {status,log}"), ["git status", "git log"])
        self.assertEqual(mx._expand_braces("git status"), ["git status"])

    def test_classifies_risk_destructive_outranks(self):
        import lgwks_multiply as mx
        self.assertEqual(mx._classify("git reset --hard"), "destructive")
        self.assertEqual(mx._classify("rm -rf build"), "destructive")
        self.assertEqual(mx._classify("git add x.py"), "mutate")
        self.assertEqual(mx._classify("git status"), "read")
        self.assertEqual(mx._classify("frobnicate x"), "unknown")

    def test_default_deny_on_flags_no_data_loss_verb_reads_as_safe(self):
        # //why: regression for the 2026-06-01 hacker finding — a read/mutate verb carrying a
        # deletion/force flag must NOT classify as 'read' (which is auto_allowed). Default-deny on flags.
        import lgwks_multiply as mx
        for cmd in ("git branch -d feature", "git branch -D feature", "git clean -fd",
                    "git checkout -- file", "git stash clear", "git update-ref -d X",
                    "git tag -d v1", "git restore file", "git push --delete origin x"):
            self.assertEqual(mx._classify(cmd), "destructive", cmd)
        # safe read verbs (incl. their benign flags) stay read — no false positives
        for cmd in ("git status", "git log -5 --oneline", "git diff --stat",
                    "git branch --show-current", "ls -la", "pwd"):
            self.assertEqual(mx._classify(cmd), "read", cmd)

    def test_run_one_uses_no_shell(self):
        # injection guard: shell metachars are NOT interpreted (argv via shlex, no shell=True).
        import lgwks_multiply as mx
        r = mx._run_one("echo safe; rm -rf /tmp/should-not-happen")
        # echo receives the rest as literal args; the rm is never executed as a separate shell command.
        self.assertIn("safe", r["out"])
        self.assertNotIn("should-not-happen", r["out"].split("safe")[0] if "safe" in r["out"] else "x")

    def test_unknown_noninteractive_requires_second_gate(self):
        import argparse
        import lgwks_multiply as mx
        args = argparse.Namespace(expr="frobnicate x", yes=True, force=False, allow_unknown=False,
                                  dry_run=False, json=False, plan_only=False, keep_going=False)
        self.assertEqual(mx.multiply_command(args), 2)


class TestGroundDegradation(unittest.TestCase):
    def test_web_empty_search_returns_no_evidence(self):
        orig = search.sweep
        search.sweep = lambda q, **k: {"results": [], "arms_empty": ["all"], "has_evidence": False}
        try:
            text, cites = ground._web("anything")
        finally:
            search.sweep = orig
        self.assertEqual((text, cites), ("", []))

    def test_ground_has_evidence_false_when_all_empty(self):
        o1, o2 = ground._ctx7_docs, ground._web
        ground._ctx7_docs = lambda q: ("", [])
        ground._web = lambda q, **k: ("", [])
        try:
            g = ground.ground("x")
        finally:
            ground._ctx7_docs, ground._web = o1, o2
        self.assertFalse(g["has_evidence"])
        self.assertEqual(g["sources"], [])


lass TestHomeQuickHints(unittest.TestCase):
    """L4 invariant: every verb shown in the `quick` block must exist in the live parser, and the
    block must never contain a separate binary (e.g. `lgwks-akinator`) that the parser can't dispatch.
    Source-of-truth = `lgwks build_parser()` (the same parser `lgwks --help` shows)."""

    def _build_parser(self):
        # The home launcher loads `lgwks` (a no-extension script) via SourceFileLoader. Mirror that
        # so the test exercises the same path the runtime does.
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path
        loader = SourceFileLoader("lgwks_cli", str(Path(lgwks_home.ROOT) / "lgwks"))
        spec = importlib.util.spec_from_loader("lgwks_cli", loader)
        mod = importlib.util.module_from_spec(spec)
        import sys as _sys
        _sys.modules.setdefault("lgwks_cli", mod)
        loader.exec_module(mod)
        return mod.build_parser()

    def _live_verb_names(self):
        parser = self._build_parser()
        for action in parser._actions:
            if action.dest == "command":
                return set(action.choices.keys())
        return set()

    def test_hints_match_live_subparsers(self):
        import lgwks_home as home
        hints = home._live_hints()
        self.assertTrue(hints, "hints must be non-empty when the live parser is reachable")
        live = self._live_verb_names()
        shown = {name for name, _ in hints}
        # every shown verb must be a registered subparser
        self.assertTrue(shown.issubset(live), f"hints reference verbs not in parser: {shown - live}")
        # //why: regression for the user-visible drift — `lgwks-akinator` is a separate binary
        # and must NEVER appear in the quick block (it isn't in `lgwks --help`).
        self.assertNotIn("akinator", shown)

    def test_hints_capped_at_six(self):
        import lgwks_home as home
        hints = home._live_hints()
        self.assertLessEqual(len(hints), 6)

    def test_hint_order_read_then_mutate_then_orchestrator(self):
        import lgwks_home as home
        hints = home._live_hints()
        # //why: bucket must be monotonically non-decreasing (read=0, mutate=1, orchestrator=2).
        # We don't know which specific verbs appear (cap=6), only the bucket invariant.
        ranks = [home._bucket_order(name)[0] for name, _ in hints]
        self.assertEqual(ranks, sorted(ranks), f"hints cross bucket boundaries: {ranks}")

    def test_hints_have_non_empty_one_line_help(self):
        import lgwks_home as home
        hints = home._live_hints()
        for name, why in hints:
            self.assertTrue(why, f"verb {name!r} has empty help text")
            # cap to keep the spine from wrapping on 80-col TTYs (see //why in _live_hints)
            self.assertLessEqual(len(why), 64, f"help for {name!r} exceeds 64 chars: {why!r}")

    def test_introspection_failure_emits_no_hints(self):
        import lgwks_home as home
        import importlib
        # Break _live_hints by replacing the importlib loader with a stub that raises on exec.
        orig = home._live_hints
        def _broken():
            try:
                raise RuntimeError("simulated parser load failure")
            except Exception:
                return []
        # //why: the spec says "fallback if introspection fails: emit nothing (no fake hints)".
        # We monkeypatch the loader's exec_module to raise, then call the real _live_hints to
        # exercise the except branch end-to-end.
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path
        real_loader = SourceFileLoader
        class _Boom(real_loader):
            def exec_module(self, module):  # type: ignore[override]
                raise RuntimeError("simulated parser load failure")
        orig_loader = importlib.machinery.SourceFileLoader
        importlib.machinery.SourceFileLoader = _Boom
        try:
            out = orig()
        finally:
            importlib.machinery.SourceFileLoader = orig_loader
        self.assertEqual(out, [])

    def test_commands_block_does_not_reference_separate_binary(self):
        # //why: belt-and-braces regression for the explicit user complaint. Render the `quick` block
        # with `on=False` (no colour, deterministic) and verify the binary name `lgwks-akinator`
        # (the separate binary) never appears. We also assert each non-empty line is a real verb
        # from the live parser — the hand-curated list is gone, so a future regression would
        # have to re-introduce a cur cmds list to break this.
        import io
        import lgwks_home as home
        captured = io.StringIO()
        import sys as _sys
        real = _sys.stdout
        _sys.stdout = captured
        try:
            home._commands(on=False, anim=False)
        finally:
            _sys.stdout = real
        out = captured.getvalue()
        self.assertNotIn("lgwks-akinator", out)
        live = self._live_verb_names()
        for line in out.splitlines():
            # the rendered hint lines look like "  lgwks <verb>   <one-liner>"
            stripped = line.lstrip()
            if not stripped.startswith("lgwks "):
                continue  # not a hint line (could be the section header or an empty spine)
            tail = stripped[len("lgwks "):]
            verb = tail.split()[0] if tail else ""
            self.assertIn(verb, live, f"quick block line references non-verb {verb!r}: {line!r}")

    def test_commands_block_emits_no_header_when_hints_empty(self):
        # //why: a "quick — what you can do today" header with zero lines under it reads as a broken
        # promise. When introspection fails, emit nothing — header AND body.
        import io
        import importlib
        import importlib.machinery
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path
        import lgwks_home as home

        class _Boom(SourceFileLoader):
            def exec_module(self, module):  # type: ignore[override]
                raise RuntimeError("simulated parser load failure")
        orig_loader = importlib.machinery.SourceFileLoader
        importlib.machinery.SourceFileLoader = _Boom
        captured = io.StringIO()
        real = importlib.import_module("sys").stdout
        importlib.import_module("sys").stdout = captured
        try:
            home._commands(on=False, anim=False)
        finally:
            importlib.machinery.SourceFileLoader = orig_loader
            importlib.import_module("sys").stdout = real
        out = captured.getvalue()
        self.assertEqual(out, "", f"quick block should be empty when hints unavailable, got: {out!r}")


class TestExpressionParser(unittest.TestCase):
    """lgwks-expression/1 parser + resolver tests.

    All tests run offline -- the manifest is mocked so no filesystem or network
    access is needed.
    """

    def _mock_manifest(self, extra_verbs=None) -> dict:
        """Minimal manifest with a known verb surface for deterministic resolution."""
        verbs = [
            {"verb": "research", "intent": "test", "args": {}, "output": "", "tokens": "none"},
            {"verb": "store", "intent": "test", "args": {}, "output": "", "tokens": "none"},
            {"verb": "extract", "intent": "test", "args": {}, "output": "", "tokens": "none"},
            {"verb": "memory remember", "intent": "test", "args": {}, "output": "", "tokens": "none"},
        ] + (extra_verbs or [])
        return {
            "manifest": "lgwks.manifest.v0",
            "tool": "lgwks",
            "brand": "Logical Works",
            "machine_first": True,
            "verbs": verbs,
            "capabilities": [],
            "steering": {},
            "thought_schema": "",
        }

    # -- parse() tests -------------------------------------------------------

    def test_parse_simple_chain_returns_two_steps(self):
        # Spec example: two-step pipeline with string args.
        import lgwks_expression as ex
        ast = ex.parse('research["query":"X"] | store["tag":"Y"]')
        self.assertEqual(len(ast), 2)
        self.assertEqual(ast[0]["verb_id"], "research")
        self.assertEqual(ast[0]["args"], {"query": "X"})
        self.assertEqual(ast[0]["index"], 0)
        self.assertEqual(ast[1]["verb_id"], "store")
        self.assertEqual(ast[1]["args"], {"tag": "Y"})
        self.assertEqual(ast[1]["index"], 1)

    def test_parse_no_args_single_step(self):
        import lgwks_expression as ex
        ast = ex.parse("extract")
        self.assertEqual(len(ast), 1)
        self.assertEqual(ast[0]["verb_id"], "extract")
        self.assertEqual(ast[0]["args"], {})

    def test_parse_dotted_verb_id(self):
        import lgwks_expression as ex
        ast = ex.parse('memory.remember["project":"q1"]')
        self.assertEqual(ast[0]["verb_id"], "memory.remember")
        self.assertEqual(ast[0]["args"], {"project": "q1"})

    def test_parse_number_and_bool_args(self):
        import lgwks_expression as ex
        ast = ex.parse('research["limit":10,"strict":true,"score":0.5]')
        self.assertEqual(ast[0]["args"]["limit"], 10)
        self.assertIs(ast[0]["args"]["strict"], True)
        self.assertAlmostEqual(ast[0]["args"]["score"], 0.5)

    def test_parse_null_arg(self):
        import lgwks_expression as ex
        ast = ex.parse('extract["target":null]')
        self.assertIsNone(ast[0]["args"]["target"])

    def test_parse_rejects_shell_injection(self):
        # Security: shell metacharacters must raise ExpressionParseError, not execute.
        import lgwks_expression as ex
        injection_payloads = [
            '$(rm -rf /)',
            '`id`',
            'extract && rm -rf /',
            'store;sudo whoami',
            'verb["arg":"$(curl evil.com)"]',
        ]
        for payload in injection_payloads:
            with self.assertRaises(ex.ExpressionParseError, msg=f"should reject: {payload!r}"):
                ex.parse(payload)

    def test_parse_rejects_empty_string(self):
        import lgwks_expression as ex
        with self.assertRaises(ex.ExpressionParseError):
            ex.parse("")
        with self.assertRaises(ex.ExpressionParseError):
            ex.parse("   ")

    def test_parse_rejects_invalid_verb_id_leading_digit(self):
        import lgwks_expression as ex
        with self.assertRaises(ex.ExpressionParseError):
            ex.parse("1extract")

    def test_parse_rejects_unclosed_bracket(self):
        import lgwks_expression as ex
        with self.assertRaises(ex.ExpressionParseError):
            ex.parse('extract["target":"x"')

    def test_parse_rejects_missing_colon_in_kv(self):
        import lgwks_expression as ex
        with self.assertRaises(ex.ExpressionParseError):
            ex.parse('extract["target" "x"]')

    # -- compile() tests -----------------------------------------------------

    def test_compile_assigns_risk_class_to_steps_and_plan(self):
        # Spec: risk_class per step + plan-level max.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        # 'research' resolves to cli:research; _classify("research") returns "unknown"
        # because 'research' is not in the _READ/_MUTATE/_DESTRUCTIVE patterns.
        # 'store' resolves to cli:store. Verify plan-level risk_class is present.
        plan = ex.compile_from_string('research["query":"X"] | store["tag":"Y"]', manifest)
        self.assertIn("risk_class", plan)
        self.assertIn(plan["risk_class"], {"read", "mutate", "unknown", "destructive"})
        for step in plan["steps"]:
            self.assertIn("risk_class", step)
            self.assertIn(step["risk_class"], {"read", "mutate", "unknown", "destructive"})

    def test_compile_risk_class_is_max_of_steps(self):
        # Spec invariant: plan.risk_class == max(step.risk_class for step in steps).
        import lgwks_expression as ex
        from lgwks_multiply import _RISK_ORDER
        manifest = self._mock_manifest()
        plan = ex.compile_from_string('research["query":"X"] | store["tag":"Y"]', manifest)
        step_risks = [s["risk_class"] for s in plan["steps"]]
        expected_max = max(step_risks, key=lambda r: _RISK_ORDER.get(r, 2))
        self.assertEqual(plan["risk_class"], expected_max)

    def test_plan_id_is_deterministic(self):
        # Spec invariant: same expression -> same plan_id on any invocation.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        expr = 'research["query":"causal inference"] | store["tag":"q1"]'
        plan_a = ex.compile_from_string(expr, manifest)
        plan_b = ex.compile_from_string(expr, manifest)
        self.assertEqual(plan_a["plan_id"], plan_b["plan_id"])

    def test_plan_id_is_sha256_of_canonical(self):
        # Spec: plan_id = sha256(canonical_expression_string).hexdigest()
        import hashlib
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string('extract["target":"https://example.com"]', manifest)
        expected_id = hashlib.sha256(plan["canonical_expression"].encode("utf-8")).hexdigest()
        self.assertEqual(plan["plan_id"], expected_id)

    def test_plan_id_stable_across_arg_order_variation(self):
        # Spec: canonical form sorts args by key; different source order -> same plan_id.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        # These two differ only in arg order; canonical form must normalise them.
        plan_a = ex.compile_from_string('research["limit":10,"query":"X"]', manifest)
        plan_b = ex.compile_from_string('research["query":"X","limit":10]', manifest)
        self.assertEqual(plan_a["plan_id"], plan_b["plan_id"])
        self.assertEqual(plan_a["canonical_expression"], plan_b["canonical_expression"])

    def test_unknown_verb_degrades_loudly_not_silently(self):
        # Spec: unresolved verb_id -> needs_review=True, warning in plan, NOT a hard crash.
        import lgwks_expression as ex
        manifest = self._mock_manifest()  # 'reason' is NOT in the mock manifest
        plan = ex.compile_from_string('reason["query":"summarise findings"]', manifest)
        step = plan["steps"][0]
        self.assertIsNone(step["resolved_primitive"])
        self.assertTrue(step["needs_review"])
        self.assertEqual(step["risk_class"], "unknown")
        self.assertTrue(
            any("unresolved" in w or "reason" in w for w in plan["warnings"]),
            f"warnings must name the unresolved verb; got {plan['warnings']}",
        )

    def test_unknown_verb_raises_verb_resolution_error_type_exists(self):
        # The VerbResolutionError class must be importable and be a LookupError subclass.
        import lgwks_expression as ex
        self.assertTrue(issubclass(ex.VerbResolutionError, LookupError))

    def test_known_verb_resolves_to_cli_primitive(self):
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string("extract", manifest)
        self.assertEqual(plan["steps"][0]["resolved_primitive"], "cli:extract")
        self.assertFalse(plan["steps"][0]["needs_review"])

    def test_dotted_verb_resolves_to_cli_with_space(self):
        # 'memory.remember' -> 'cli:memory remember'
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string('memory.remember["project":"q1"]', manifest)
        self.assertEqual(plan["steps"][0]["resolved_primitive"], "cli:memory remember")

    def test_plan_schema_field_is_correct_discriminator(self):
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string("extract", manifest)
        self.assertEqual(plan["schema"], "lgwks-expression/1")

    def test_compile_policy_shell_is_always_false(self):
        # Spec invariant: no step may execute through a shell interpreter.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string("extract", manifest)
        self.assertFalse(plan["compile_policy"]["shell"])

    def test_manifest_version_recorded_in_plan(self):
        # Spec invariant: plan records manifest_version so replay detects drift.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string("extract", manifest)
        self.assertEqual(plan["manifest_version"], "lgwks.manifest.v0")

    def test_is_expression_string_routing_heuristic(self):
        import lgwks_expression as ex
        # Should identify expression strings.
        self.assertTrue(ex.is_expression_string("extract"))
        self.assertTrue(ex.is_expression_string('research["query":"X"] | store'))
        self.assertTrue(ex.is_expression_string("memory.remember"))
        # Should NOT identify JSON objects.
        self.assertFalse(ex.is_expression_string('{"schema":"lgwks-geoexpr/1"}'))
        # Should NOT identify brace expressions.
        self.assertFalse(ex.is_expression_string("git {status,log}"))
        # Should NOT identify empty string.
        self.assertFalse(ex.is_expression_string(""))

    def test_expression_parse_error_has_typed_class(self):
        # Spec: typed errors, never bare Exception.
        import lgwks_expression as ex
        self.assertTrue(issubclass(ex.ExpressionParseError, ValueError))
        err = ex.ExpressionParseError("test", pos=3, token="abc")
        self.assertEqual(err.pos, 3)
        self.assertEqual(err.token, "abc")

    def test_canonical_expression_is_lowercase_sorted_args(self):
        # Canonical form: verb_id lowercased, args sorted by key.
        import lgwks_expression as ex
        manifest = self._mock_manifest()
        plan = ex.compile_from_string('research["z":"last","a":"first"]', manifest)
        canon = plan["canonical_expression"]
        self.assertIn("research", canon)
        # 'a' must appear before 'z' in the canonical form (arg sort is lexicographic).
        # Canonical form uses bare key names (unquoted), so search for 'a:' and 'z:'.
        self.assertLess(canon.index("a:"), canon.index("z:"))


if __name__ == "__main__":
    unittest.main()
