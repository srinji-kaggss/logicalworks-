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
        def fake_curl(url, data=None, timeout=20):
            calls.append(url)
            if "html.duckduckgo" in url:
                return ""                                   # first endpoint blocked/empty
            return '<a href="https://cl.com/acq">Canada Life acquisition</a>'  # second endpoint answers
        slept = []
        orig = search._curl
        search._curl = fake_curl
        try:
            rows = search._open("Canada Life acquisition", k=3, sleep=lambda s: slept.append(s))
        finally:
            search._curl = orig
        self.assertTrue(rows, "rotation must recover when the first endpoint is dry")
        self.assertEqual(rows[0]["url"], "https://cl.com/acq")
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
        self.assertLessEqual(search._backoff(10), 2.0, "backoff is capped, never unbounded")


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


if __name__ == "__main__":
    unittest.main()
