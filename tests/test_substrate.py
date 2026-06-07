from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_substrate as substrate


class TestSubstrateScoring(unittest.TestCase):
    def test_fact_score_prefers_numeric_rules(self):
        a = substrate._fact_score("RRSP minimum amount is $5,000 and form T2033 is required.")
        b = substrate._fact_score("I think RRSP is a great account and people love it.")
        self.assertGreater(a, b)

    def test_stem_text_filters_narrative(self):
        text = "I think this is great. Minimum amount is $5,000. Use form T2033."
        out = substrate._stem_text(text, 0.6)
        self.assertIn("Minimum amount is $5,000.", out)
        self.assertIn("Use form T2033.", out)
        self.assertNotIn("I think this is great.", out)

    def test_looks_like_login_gate(self):
        self.assertTrue(substrate._looks_like_login_gate("Sign in", "Use Touch ID to continue", "https://portal.example.com/login"))
        self.assertTrue(substrate._looks_like_login_gate("Just a moment...", "Checking your browser before accessing the portal", "https://portal.example.com/"))
        self.assertFalse(substrate._looks_like_login_gate("Overview", "Transfer threshold is 500 dollars.", "https://portal.example.com/docs"))


class TestSubstrateBuild(unittest.TestCase):
    def test_build_from_local_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            (root / "a.md").write_text(
                "RRSP minimum amount is $5,000. Use form T2033. I think this is great.",
                encoding="utf-8",
            )
            (root / "b.txt").write_text(
                "Transfer route TR01 to TR02. Settlement is T+1. Marketing story goes here.",
                encoding="utf-8",
            )

            args = type("Args", (), {
                "target": str(root),
                "project": "fundserv-test",
                "source_type": "folder",
                "max_pages": 10,
                "max_depth": 1,
                "max_files": 10,
                "max_chars": 10000,
                "chunk_words": 80,
                "chunk_overlap": 10,
                "fact_threshold": 0.6,
                "embed_provider": "auto",
                "embed_model": "",
                "login_if_needed": True,
                "login_url": "",
                "success_selector": None,
                "max_auto_bypass_attempts": 3,
                "max_auth_handoffs": 3,
                "browser_engine": "chromium",
            })()

            with mock.patch.object(substrate.lgwks_run, "embed", return_value=([0.1, 0.2, 0.3], "ollama:qwen3-embedding:8b", True)):
                with mock.patch.object(substrate, "GLOBAL_FACT_DB", Path(td) / "global-facts.db"):
                    manifest = substrate.build_run(args)

            run_dir = Path(manifest["artifacts"]["root"])
            self.assertTrue((run_dir / "facts.jsonl").exists())
            facts = [json.loads(line) for line in (run_dir / "facts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any("T2033" in row["fact_text"] for row in facts))
            vectors = [json.loads(line) for line in (run_dir / "vectors.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(row["provider"] == "ollama:qwen3-embedding:8b" for row in vectors))
            self.assertGreaterEqual(manifest["embedding"]["semantic_vectors"], len(vectors))
            self.assertGreater(manifest["embedding"]["global_fact_vectors_written"], 0)
            self.assertTrue(Path(manifest["global_artifacts"]["fact_vector_db"]).exists())

    def test_crawl_site_prompts_auth_then_retries(self):
        state = {"saved": False}

        def fake_render(url, **_kwargs):
            if not state["saved"]:
                return {"ok": True, "html": "<html>Sign in with passkey</html>", "text": "Sign in with passkey"}
            return {"ok": True, "html": "<html>Transfer threshold is $500.</html>", "text": "Transfer threshold is $500."}

        def fake_html_to_markdown(html, url):
            if "Sign in" in html:
                return "Sign in with passkey", "Sign in", []
            return "Transfer threshold is $500.", "Overview", []

        def fake_save_session(_url, **_kwargs):
            state["saved"] = True
            return {"ok": True, "path": "/tmp/session.json", "reason": "session saved (manual)"}

        with mock.patch.object(substrate.lgwks_browser, "_remote_allowed", return_value=True):
            with mock.patch.object(substrate.lgwks_browser, "render", side_effect=fake_render):
                with mock.patch.object(substrate.lgwks_browser, "save_session", side_effect=fake_save_session):
                    with mock.patch.object(substrate, "html_to_markdown", side_effect=fake_html_to_markdown):
                        docs, frontier = substrate._crawl_site(
                            "https://portal.example.com",
                            max_pages=1,
                            max_depth=0,
                            browser_engine="webkit",
                            login_if_needed=True,
                            login_url="",
                            success_selector=None,
                            max_auto_bypass_attempts=1,
                            max_auth_handoffs=2,
                        )
        self.assertEqual(len(docs), 1)
        self.assertIn("$500", docs[0]["text"])
        self.assertTrue(any(row["status"] == "retrying_gate" for row in frontier))
        self.assertTrue(any(row["status"] == "auth_verified" for row in frontier))

    def test_crawl_site_stops_after_failed_auth_verification(self):
        """If save_session returns ok but headless verification still shows a login gate,
        the crawler must NOT re-queue the URL and must NOT prompt again immediately."""
        call_count = {"render": 0}

        def fake_render(url, **_kwargs):
            call_count["render"] += 1
            # Always returns login-gate HTML — session never works in headless mode
            return {"ok": True, "html": "<html>Sign in with passkey</html>", "text": "Sign in with passkey"}

        def fake_html_to_markdown(html, url):
            if "Sign in" in html:
                return "Sign in with passkey", "Sign in", []
            return "Transfer threshold is $500.", "Overview", []

        def fake_save_session(_url, **_kwargs):
            return {"ok": True, "path": "/tmp/session.json", "reason": "session saved (manual)"}

        with mock.patch.object(substrate.lgwks_browser, "_remote_allowed", return_value=True):
            with mock.patch.object(substrate.lgwks_browser, "render", side_effect=fake_render):
                with mock.patch.object(substrate.lgwks_browser, "save_session", side_effect=fake_save_session):
                    with mock.patch.object(substrate, "html_to_markdown", side_effect=fake_html_to_markdown):
                        docs, frontier = substrate._crawl_site(
                            "https://portal.example.com",
                            max_pages=1,
                            max_depth=0,
                            browser_engine="chromium",
                            login_if_needed=True,
                            login_url="",
                            success_selector=None,
                            max_auto_bypass_attempts=0,
                            max_auth_handoffs=2,
                        )
        self.assertEqual(len(docs), 0)
        self.assertTrue(any(row["status"] == "auth_saved_but_failed" for row in frontier))
        # render should be called: initial + verification (2 times), NOT a second save_session
        self.assertEqual(call_count["render"], 2)


class TestCrawlMap(unittest.TestCase):
    def test_uses_last_status_per_url(self):
        """frontier is append-only: _crawl_map must surface the final status per URL."""
        frontier = [
            {"url": "https://example.com/a", "depth": 0, "status": "retrying_gate", "discovered_by": "seed"},
            {"url": "https://example.com/a", "depth": 0, "status": "auth_verified", "discovered_by": "seed", "links_found": 12},
            {"url": "https://example.com/b", "depth": 1, "status": "ok", "links_found": 5, "discovered_by": "https://example.com/a"},
        ]
        cmap = substrate._crawl_map(frontier)
        self.assertEqual(len(cmap["nodes"]), 2)
        node_a = next(n for n in cmap["nodes"] if n["url"] == "https://example.com/a")
        self.assertEqual(node_a["status"], "auth_verified")
        self.assertEqual(node_a["links_found"], 12)
        # seed is excluded from edges; only a→b
        self.assertEqual(len(cmap["edges"]), 1)
        self.assertEqual(cmap["edges"][0], {"from": "https://example.com/a", "to": "https://example.com/b"})


class TestBuildIndexDb(unittest.TestCase):
    def test_allows_duplicate_frontier_urls(self):
        """frontier table is append-only; duplicate URLs must not crash with UNIQUE constraint."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.db"
            substrate._build_index_db(
                db_path,
                source_rows=[],
                doc_rows=[],
                chunk_rows=[],
                fact_rows=[],
                vector_rows=[],
                frontier=[
                    {"url": "https://example.com", "depth": 0, "status": "retrying_gate", "discovered_by": "seed"},
                    {"url": "https://example.com", "depth": 0, "status": "auth_verified", "discovered_by": "seed"},
                ],
            )
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT status FROM frontier WHERE url = ? ORDER BY rowid", ("https://example.com",))
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "retrying_gate")
            self.assertEqual(rows[1][0], "auth_verified")
            conn.close()


class TestAuthHandoff(unittest.TestCase):
    def test_uses_chromium_for_manual_auth(self):
        """When auth handoff triggers, save_session must use chromium regardless of the
        headless browser_engine, because headed WebKit on macOS often fails to surface
        a visible window."""
        captured = {}

        def fake_render(url, **_kwargs):
            return {"ok": True, "html": "<html>Sign in</html>", "text": "Sign in"}

        def fake_html_to_markdown(html, url):
            return "Sign in", "Sign in", []

        def fake_save_session(url, **kwargs):
            captured["kwargs"] = kwargs
            return {"ok": True, "path": "/tmp/session.json", "reason": "session saved (manual)"}

        with mock.patch.object(substrate.lgwks_browser, "_remote_allowed", return_value=True):
            with mock.patch.object(substrate.lgwks_browser, "render", side_effect=fake_render):
                with mock.patch.object(substrate.lgwks_browser, "save_session", side_effect=fake_save_session):
                    with mock.patch.object(substrate, "html_to_markdown", side_effect=fake_html_to_markdown):
                        substrate._crawl_site(
                            "https://portal.example.com",
                            max_pages=1,
                            max_depth=0,
                            browser_engine="webkit",
                            login_if_needed=True,
                            login_url="",
                            success_selector=None,
                            max_auto_bypass_attempts=0,
                            max_auth_handoffs=2,
                        )
        self.assertEqual(captured["kwargs"]["browser_engine"], "chromium")
        self.assertTrue(captured["kwargs"]["manual"])


class TestVectorSpaceIdentity(unittest.TestCase):
    """Tests for issue #41: build/query vector-space identity enforcement."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_run_dir(self, tmp: str, *, provider: str = "deterministic", dims: int = 4) -> Path:
        """Write a minimal run directory (vectors.jsonl + manifest.json)."""
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        vec = [0.1, 0.2, 0.3, 0.4]
        vector_rows = [{
            "chunk_id": "chunk-aaa",
            "document_id": "doc-bbb",
            "provider": provider,
            "is_semantic": provider != "deterministic",
            "dims": dims,
            "vector_text": "Transfer route TR01 requires form T2033.",
            "vector": vec,
            "fact_score": 0.7,
            "chunk_kind": "stem_fact",
            "vector_id": "vec-001",
        }]
        with (run_dir / "vectors.jsonl").open("w") as fh:
            for row in vector_rows:
                fh.write(json.dumps(row) + "\n")
        manifest = {
            "schema": "lgwks.substrate.run.v0",
            "run_id": "test-run",
            "vector_space": {
                "provider_requested": provider,
                "model_requested": "",
                "providers_used": {provider: 1},
                "canonical_provider": provider,
                "canonical_model": "",
                "dims": dims,
                "semantic": provider != "deterministic",
                "ambiguous": False,
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return run_dir

    # ------------------------------------------------------------------
    # 1. No provider specified → resolves from manifest
    # ------------------------------------------------------------------

    def test_no_provider_resolves_from_manifest(self):
        """query with no provider specified must use the build-time provider from manifest."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir(td, provider="deterministic")
            with mock.patch.object(
                substrate.lgwks_run,
                "embed",
                return_value=([0.1, 0.2, 0.3, 0.4], "deterministic", False),
            ) as m_embed:
                result = substrate._vector_search(run_dir, "test query", 10, "", "")

        self.assertTrue(result.get("ok"), msg=result)
        # embed() must have been called with provider="deterministic"
        call_provider = m_embed.call_args.kwargs.get("provider") or m_embed.call_args[1].get("provider")
        self.assertEqual(call_provider, "deterministic")
        self.assertIn("stored_vector_space", result)
        self.assertIn("query_vector_space", result)

    # ------------------------------------------------------------------
    # 2. Explicit provider mismatch → structured error, no rows
    # ------------------------------------------------------------------

    def test_explicit_provider_mismatch_fails_closed(self):
        """Passing an explicit provider that differs from the stored space must return a structured error."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir(td, provider="deterministic")
            result = substrate._vector_search(run_dir, "test query", 10, "ollama", "")

        self.assertFalse(result.get("ok"), msg=result)
        self.assertEqual(result["error"], "embedding provider mismatch")
        self.assertIn("stored_vector_space", result)
        self.assertIn("requested_vector_space", result)
        self.assertIn("hint", result)
        self.assertEqual(result["rows"], [])

    # ------------------------------------------------------------------
    # 3. Mismatch + --force-cross-space → rows + warning
    # ------------------------------------------------------------------

    def test_mismatch_with_force_cross_space_succeeds_with_warning(self):
        """With --force-cross-space, a mismatched provider must succeed but include a warning."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir(td, provider="deterministic")
            with mock.patch.object(
                substrate.lgwks_run,
                "embed",
                return_value=([0.1, 0.2, 0.3, 0.4], "ollama:qwen3-embedding:8b", True),
            ):
                result = substrate._vector_search(
                    run_dir, "test query", 10, "ollama", "", force_cross_space=True
                )

        self.assertTrue(result.get("ok"), msg=result)
        self.assertTrue(result.get("cross_space_forced"))
        self.assertIn("warning", result)
        self.assertGreater(len(result["rows"]), 0)

    # ------------------------------------------------------------------
    # 4. Missing manifest → fallback from homogeneous vectors.jsonl
    # ------------------------------------------------------------------

    def test_missing_manifest_falls_back_to_homogeneous_jsonl(self):
        """When manifest.json is absent, a homogeneous vectors.jsonl must resolve the space."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir(td, provider="deterministic")
            (run_dir / "manifest.json").unlink()  # remove manifest

            with mock.patch.object(
                substrate.lgwks_run,
                "embed",
                return_value=([0.1, 0.2, 0.3, 0.4], "deterministic", False),
            ):
                result = substrate._vector_search(run_dir, "test query", 10, "", "")

        self.assertTrue(result.get("ok"), msg=result)
        vs = result["stored_vector_space"]
        self.assertEqual(vs["canonical_provider"], "deterministic")
        self.assertIn("fallback", vs.get("source", ""))

    # ------------------------------------------------------------------
    # 5. Mixed-provider vectors.jsonl → fails closed unless forced
    # ------------------------------------------------------------------

    def test_mixed_provider_jsonl_fails_closed(self):
        """Mixed providers in vectors.jsonl (no manifest) must be rejected unless forced."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            rows = [
                {"chunk_id": "c1", "document_id": "d1", "provider": "deterministic",
                 "is_semantic": False, "dims": 4, "vector": [0.1, 0.2, 0.3, 0.4],
                 "vector_text": "T+1", "fact_score": 0.6, "chunk_kind": "stem_fact", "vector_id": "v1"},
                {"chunk_id": "c2", "document_id": "d2", "provider": "ollama:qwen3-embedding:8b",
                 "is_semantic": True, "dims": 8, "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                 "vector_text": "RRSP", "fact_score": 0.5, "chunk_kind": "narrative_context", "vector_id": "v2"},
            ]
            with (run_dir / "vectors.jsonl").open("w") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
            # No manifest.json

            result = substrate._vector_search(run_dir, "test query", 10, "", "")

        self.assertFalse(result.get("ok"), msg=result)
        self.assertEqual(result["error"], "ambiguous stored vector space")
        self.assertIn("stored_vector_space", result)
        self.assertIn("hint", result)

    # ------------------------------------------------------------------
    # 6. Mixed-provider + --force-cross-space → proceeds
    # ------------------------------------------------------------------

    def test_mixed_provider_with_force_cross_space_proceeds(self):
        """--force-cross-space must override the ambiguous-space hard error."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            rows = [
                {"chunk_id": "c1", "document_id": "d1", "provider": "deterministic",
                 "is_semantic": False, "dims": 4, "vector": [0.1, 0.2, 0.3, 0.4],
                 "vector_text": "T+1", "fact_score": 0.6, "chunk_kind": "stem_fact", "vector_id": "v1"},
                {"chunk_id": "c2", "document_id": "d2", "provider": "ollama:qwen3-embedding:8b",
                 "is_semantic": True, "dims": 4, "vector": [0.2, 0.3, 0.4, 0.5],
                 "vector_text": "RRSP", "fact_score": 0.5, "chunk_kind": "narrative_context", "vector_id": "v2"},
            ]
            with (run_dir / "vectors.jsonl").open("w") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")

            with mock.patch.object(
                substrate.lgwks_run,
                "embed",
                return_value=([0.1, 0.2, 0.3, 0.4], "auto", False),
            ):
                result = substrate._vector_search(
                    run_dir, "test query", 10, "", "", force_cross_space=True
                )

        self.assertTrue(result.get("ok"), msg=result)
        self.assertTrue(result.get("cross_space_forced"))
        self.assertIn("warning", result)

    # ------------------------------------------------------------------
    # 7. build_run: manifest now includes vector_space field
    # ------------------------------------------------------------------

    def test_build_run_manifest_includes_vector_space(self):
        """build_run must write vector_space to manifest.json."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            (root / "a.md").write_text(
                "RRSP minimum amount is $5,000. Use form T2033.",
                encoding="utf-8",
            )
            args = type("Args", (), {
                "target": str(root),
                "project": "vs-test",
                "source_type": "folder",
                "max_pages": 10,
                "max_depth": 1,
                "max_files": 10,
                "max_chars": 10000,
                "chunk_words": 80,
                "chunk_overlap": 10,
                "fact_threshold": 0.6,
                "embed_provider": "deterministic",
                "embed_model": "",
                "login_if_needed": True,
                "login_url": "",
                "success_selector": None,
                "max_auto_bypass_attempts": 3,
                "max_auth_handoffs": 3,
                "browser_engine": "chromium",
            })()

            with mock.patch.object(
                substrate.lgwks_run, "embed",
                return_value=([0.5, 0.6, 0.7], "deterministic", False)
            ):
                with mock.patch.object(substrate, "GLOBAL_FACT_DB", Path(td) / "gfv.db"):
                    manifest = substrate.build_run(args)

        self.assertIn("vector_space", manifest)
        vs = manifest["vector_space"]
        self.assertEqual(vs["canonical_provider"], "deterministic")
        self.assertFalse(vs["ambiguous"])
        # Verify it was written to disk too
        run_dir = Path(manifest["artifacts"]["root"])
        on_disk = json.loads((run_dir / "manifest.json").read_text())
        self.assertIn("vector_space", on_disk)

    # ------------------------------------------------------------------
    # 8. _stored_vector_space helper: manifest takes priority over jsonl
    # ------------------------------------------------------------------

    def test_stored_vector_space_prefers_manifest(self):
        """_stored_vector_space must prefer manifest.json over vectors.jsonl."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir(td, provider="deterministic")
            # Corrupt vectors.jsonl to contain a different provider
            (run_dir / "vectors.jsonl").write_text(
                json.dumps({
                    "chunk_id": "c1", "document_id": "d1", "provider": "ollama:qwen3-embedding:8b",
                    "is_semantic": True, "dims": 256, "vector": [0.1],
                    "vector_text": "x", "fact_score": 0.5, "chunk_kind": "narrative_context", "vector_id": "v1",
                }) + "\n",
                encoding="utf-8",
            )
            vs = substrate._stored_vector_space(run_dir)

        # Should still return deterministic from manifest, not ollama from jsonl
        self.assertEqual(vs.get("canonical_provider"), "deterministic")


if __name__ == "__main__":
    unittest.main()

