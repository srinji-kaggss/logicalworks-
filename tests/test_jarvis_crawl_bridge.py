"""
Tests for issue #34: lgwks jarvis crawl -> substrate bridge.

All network I/O and substrate file I/O are mocked.  No real URLs are fetched.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The crawl→substrate bridge engine (#34) lives in lgwks_jarvis; the canonical
# `crawl` verb (lgwks_crawl) owns the user-facing flag surface and delegates to
# it. Behavioral tests exercise the engine directly; parser-registration tests
# inspect the canonical verb's source.
here = os.path.dirname(os.path.abspath(__file__))
import lgwks_jarvis as _lgwks
_lgwks_path = os.path.join(os.path.dirname(here), "lgwks_crawl.py")


# ---------------------------------------------------------------------------
# Shared fake substrate manifest returned by mocked build_run
# ---------------------------------------------------------------------------

def _fake_substrate_manifest(run_dir: Path, target: str = "https://example.com") -> dict:
    """Minimal manifest that matches lgwks_substrate.build_run() output shape."""
    return {
        "schema": "lgwks.substrate.run.v0",
        "run_id": "example-com-20260607-000000",
        "target": target,
        "source_type": "url",
        "project": "example-com",
        "created_at": "2026-06-07T00:00:00Z",
        "embedding": {
            "provider_requested": "deterministic",
            "model_requested": "",
            "providers_used": {"deterministic-feature-hash": 2},
            "semantic_vectors": 0,
            "total_vectors": 2,
            "global_fact_vectors_written": 1,
        },
        "vector_space": {
            "canonical_provider": "deterministic-feature-hash",
            "canonical_model": "",
            "dims": 256,
            "semantic": False,
            "ambiguous": False,
            "providers_used": {"deterministic-feature-hash": 2},
        },
        "auth": {
            "login_if_needed": True,
            "login_url": "",
            "success_selector": "",
            "max_auto_bypass_attempts": 3,
            "max_auth_handoffs": 3,
            "browser_engine": "webkit",
        },
        "counts": {
            "sources": 1,
            "documents": 1,
            "chunks": 2,
            "facts": 1,
            "frontier": 1,
            "graph_nodes": 3,
            "graph_edges": 2,
        },
        "artifacts": {
            "root": str(run_dir),
            "sources": "sources.jsonl",
            "documents": "documents.jsonl",
            "chunks": "chunks.jsonl",
            "facts": "facts.jsonl",
            "vectors": "vectors.jsonl",
            "frontier": "frontier.jsonl",
            "crawl_map": "crawl_map.json",
            "graph_db": "graph.db",
            "graph_json": "graph.json",
            "graph_mermaid": "graph.mmd",
            "substrate_db": "substrate.db",
        },
        "global_artifacts": {"fact_vector_db": str(run_dir / "global-facts.db")},
    }


def _make_jarvis_args(**overrides) -> argparse.Namespace:
    """Return a minimal Namespace that mimics the new crawl parser defaults."""
    defaults = dict(
        source="https://example.com",
        keyword_terms=[],
        keywords=None,
        prompt="map the machine-state understanding",
        name=None,
        max_pages=3,
        max_depth=1,
        workers=2,
        include_external=False,
        search_expansion=False,
        chunk_words=450,
        chunk_overlap=70,
        max_terms=120,
        compress_limit=96,
        similarity_threshold=0.72,
        estimate_only=False,
        engine="substrate",
        login_if_needed=True,
        login_url="",
        auth_selector=None,
        chromium=False,
        embed_provider="deterministic",
        embed_model="",
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# 1. --estimate-only returns estimate and never calls substrate
# ---------------------------------------------------------------------------

class TestEstimateOnly(unittest.TestCase):
    def test_estimate_only_does_not_call_substrate(self):
        """--estimate-only must short-circuit before any substrate call."""
        args = _make_jarvis_args(estimate_only=True)
        with mock.patch.object(_lgwks, "_import_substrate") as m_sub:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = _lgwks.crawl_command(args)
        self.assertEqual(rc, 0)
        m_sub.assert_not_called()
        out = json.loads(buf.getvalue())
        self.assertIn("estimated_seconds", out)
        self.assertIn("estimated_minutes", out)


# ---------------------------------------------------------------------------
# 2. URL crawl delegates to lgwks_substrate.build_run()
# ---------------------------------------------------------------------------

class TestUrlCrawlDelegatesToSubstrate(unittest.TestCase):
    def test_url_source_calls_build_run_with_mapped_args(self):
        """URL crawl must call substrate.build_run and return Jarvis-compatible summary."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            manifest = _fake_substrate_manifest(run_dir)

            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = manifest

            args = _make_jarvis_args(max_pages=3, max_depth=1)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    rc = _lgwks.crawl_command(args)

        self.assertEqual(rc, 0)
        fake_sub.build_run.assert_called_once()
        sub_args = fake_sub.build_run.call_args[0][0]
        # arg mapping checks
        self.assertEqual(sub_args.target, "https://example.com")
        self.assertEqual(sub_args.max_pages, 3)
        self.assertEqual(sub_args.max_depth, 1)

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["schema"], "lgwks.jarvis.substrate_crawl.v0")
        self.assertEqual(payload["engine"], "substrate")
        self.assertIn("run_id", payload)
        self.assertIn("substrate_manifest", payload)
        self.assertIn("substrate_db", payload)
        self.assertIn("counts", payload)
        self.assertIn("embedding", payload)
        self.assertIn("auth", payload)

    def test_run_id_and_target_propagated_from_manifest(self):
        """run_id and target in output must come from the substrate manifest."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            manifest = _fake_substrate_manifest(run_dir, target="https://example.com/docs")
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = manifest

            args = _make_jarvis_args(source="https://example.com/docs")
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    _lgwks.crawl_command(args)

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["target"], "https://example.com/docs")
        self.assertEqual(payload["run_id"], "example-com-20260607-000000")


# ---------------------------------------------------------------------------
# 3. Auth flags are accepted and mapped into sub_args
# ---------------------------------------------------------------------------

class TestAuthFlagsMapping(unittest.TestCase):
    def test_login_url_mapped_to_substrate_args(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(login_url="https://example.com/login", login_if_needed=True)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.login_url, "https://example.com/login")
        self.assertTrue(sub_args.login_if_needed)

    def test_no_login_flag_passes_false(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(login_if_needed=False)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertFalse(sub_args.login_if_needed)

    def test_chromium_flag_sets_browser_engine(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(chromium=True)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.browser_engine, "chromium")

    def test_default_no_chromium_uses_webkit(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(chromium=False)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.browser_engine, "webkit")

    def test_auth_selector_mapped_to_success_selector(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(auth_selector="#dashboard")
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.success_selector, "#dashboard")


# ---------------------------------------------------------------------------
# 4. Keyword-only crawl stays on legacy path (no substrate call)
# ---------------------------------------------------------------------------

class TestKeywordOnlyCrawlIsLegacy(unittest.TestCase):
    def test_keyword_only_does_not_call_substrate(self):
        """When source is None (keyword-only), substrate must NOT be called."""
        args = _make_jarvis_args(source=None, keyword_terms=["RRSP", "minimum"], engine="substrate")
        with mock.patch.object(_lgwks, "_import_substrate") as m_sub:
            # legacy path tries to fetch seeds; patch build_seed_urls to prevent I/O
            with mock.patch.object(_lgwks, "build_seed_urls", side_effect=SystemExit("no seed")):
                try:
                    _lgwks.crawl_command(args)
                except SystemExit:
                    pass
        m_sub.assert_not_called()


# ---------------------------------------------------------------------------
# 5. --engine legacy calls old Jarvis path (no substrate)
# ---------------------------------------------------------------------------

class TestLegacyEngine(unittest.TestCase):
    def test_engine_legacy_url_does_not_call_substrate(self):
        """--engine legacy must bypass substrate even for URL sources.

        #165 step 3: the per-run JarvisDB island was retired; the legacy path now
        persists through the one State Fabric gate. Both run roots are redirected to
        a temp dir so the gate store never touches the real workspace.
        """
        import lgwks_substrate_config as _sc
        args = _make_jarvis_args(source="https://example.com", engine="legacy")
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(_lgwks, "_import_substrate") as m_sub, \
                 mock.patch.object(_lgwks, "build_seed_urls", return_value=([], [])), \
                 mock.patch.object(_lgwks, "RUN_ROOT", Path(td) / "jarvis"), \
                 mock.patch.object(_sc, "RUN_ROOT", Path(td) / "gate"):
                # Legacy path builds the gate then raises SystemExit on empty seeds.
                try:
                    _lgwks.crawl_command(args)
                except SystemExit:
                    pass
        m_sub.assert_not_called()



# ---------------------------------------------------------------------------
# 6. Machine output shape: schema + engine field present
# ---------------------------------------------------------------------------

class TestMachineOutputShape(unittest.TestCase):
    def test_output_has_required_schema_fields(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args()
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    _lgwks.crawl_command(args)

        payload = json.loads(buf.getvalue())
        for field in ("schema", "engine", "run_id", "target",
                      "substrate_manifest", "substrate_db", "graph_json",
                      "counts", "embedding", "auth"):
            self.assertIn(field, payload, f"missing field: {field}")
        self.assertEqual(payload["schema"], "lgwks.jarvis.substrate_crawl.v0")
        self.assertEqual(payload["engine"], "substrate")

    def test_artifact_paths_are_absolute_strings(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args()
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    _lgwks.crawl_command(args)

        payload = json.loads(buf.getvalue())
        for field in ("substrate_manifest", "substrate_db", "graph_json"):
            self.assertIsInstance(payload[field], str, f"{field} must be a string path")
            if payload[field]:
                self.assertTrue(
                    Path(payload[field]).is_absolute(),
                    f"{field}={payload[field]!r} must be an absolute path",
                )


# ---------------------------------------------------------------------------
# 7. Parser registers the new flags
# ---------------------------------------------------------------------------

class TestParserRegistration(unittest.TestCase):
    """Verify the argparse surface has the new flags via source inspection."""

    def _get_crawl_block(self) -> str:
        import re
        src = Path(_lgwks_path).read_text(encoding="utf-8")
        block = re.search(
            r'crawl\s*=\s*sub\.add_parser\(\s*"crawl".*?crawl\.set_defaults',
            src,
            re.DOTALL,
        )
        self.assertIsNotNone(block, "could not locate the crawl parser block in lgwks_crawl")
        assert block is not None
        return block.group(0)

    def test_engine_flag_registered(self):
        self.assertIn("--engine", self._get_crawl_block())

    def test_login_if_needed_flag_registered(self):
        self.assertIn("--login-if-needed", self._get_crawl_block())

    def test_login_url_flag_registered(self):
        self.assertIn("--login-url", self._get_crawl_block())

    def test_auth_selector_flag_registered(self):
        self.assertIn("--auth-selector", self._get_crawl_block())

    def test_chromium_flag_registered(self):
        self.assertIn("--chromium", self._get_crawl_block())

    def test_embed_provider_flag_registered(self):
        self.assertIn("--embed-provider", self._get_crawl_block())

    def test_embed_model_flag_registered(self):
        self.assertIn("--embed-model", self._get_crawl_block())


# ---------------------------------------------------------------------------
# 8. Manifest still lists jarvis crawl
# ---------------------------------------------------------------------------

class TestManifestListsJarvisCrawl(unittest.TestCase):
    # #218 consolidated `jarvis crawl` into the canonical `crawl` verb; the
    # substrate bridge contract now lives on `crawl`.
    def test_jarvis_crawl_in_manifest(self):
        import lgwks_manifest as man
        m = man.build_manifest()
        verb_names = {v["verb"] for v in m["verbs"]}
        self.assertIn("crawl", verb_names)

    def test_jarvis_crawl_metadata_mentions_substrate(self):
        import lgwks_manifest as man
        meta = man._VERB_META.get("crawl", {})
        intent = meta.get("intent", "")
        self.assertIn("substrate", intent.lower(), "manifest intent must mention substrate engine")

    def test_jarvis_crawl_metadata_mentions_engine_arg(self):
        import lgwks_manifest as man
        meta = man._VERB_META.get("crawl", {})
        args = meta.get("args", {})
        self.assertIn("--engine", args)


# ---------------------------------------------------------------------------
# 9. _crawl_via_substrate: name arg is mapped to project
# ---------------------------------------------------------------------------

class TestSubstrateBridgeArgMapping(unittest.TestCase):
    def test_name_arg_maps_to_project(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(name="my-project")
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.project, "my-project")

    def test_chunk_words_propagated(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(chunk_words=200, chunk_overlap=30)
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.chunk_words, 200)
        self.assertEqual(sub_args.chunk_overlap, 30)

    def test_default_embed_provider_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args()
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.embed_provider, "deterministic")
        self.assertEqual(sub_args.embed_model, "")

    def test_embed_provider_and_model_propagated(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            fake_sub = mock.MagicMock()
            fake_sub.build_run.return_value = _fake_substrate_manifest(run_dir)

            args = _make_jarvis_args(embed_provider="ollama", embed_model="qwen3-embedding:8b")
            with mock.patch.object(_lgwks, "_import_substrate", return_value=fake_sub):
                with contextlib.redirect_stdout(io.StringIO()):
                    _lgwks.crawl_command(args)

        sub_args = fake_sub.build_run.call_args[0][0]
        self.assertEqual(sub_args.embed_provider, "ollama")
        self.assertEqual(sub_args.embed_model, "qwen3-embedding:8b")


class LegacyEngineContentDedupTests(unittest.TestCase):
    """#261 pillar 1: the legacy (--engine legacy) crawler must use content-addressed
    chunk identity so identical content across documents collapses to one node + one
    embedding, with provenance preserved as doc->chunk containment edges. Mirrors the
    substrate dedup locked by tests/test_substrate.py."""

    def _legacy_args(self):
        return argparse.Namespace(
            source="https://dedup.test",
            keywords=None,
            keyword_terms=None,
            name="dedup",
            engine="legacy",
            max_pages=2,
            max_depth=0,
            workers=1,
            chunk_words=450,
            chunk_overlap=70,
            similarity_threshold=0.72,
            max_terms=80,
            estimate_only=False,
            search_expansion=False,
            include_external=False,
            compress_limit=96,
            prompt="",
        )

    def test_identical_content_across_docs_dedups_and_keeps_provenance(self):
        """#165 step 3: the dedup+provenance contract now lives in the one State
        Fabric gate, not a per-run research.sqlite island. Identical content still
        collapses to one cid-keyed chunk + one embedding, and each document keeps a
        `contains` provenance edge. We assert against the gate's projection stores:
        relational.db (documents/chunks), graph.db (edges), vector_records.db.
        """
        import sqlite3
        import lgwks_substrate_config as _sc

        body = (
            "Deterministic compression collapses identical content to one node. "
            "This paragraph is byte-identical across both fetched documents so the "
            "content-addressed chunk identity must produce a single chunk row and a "
            "single embedding, while every containing document keeps a provenance edge."
        )

        def fake_seeds(source, keywords, max_pages, expansion):
            return ([("https://dedup.test/a", "seed"), ("https://dedup.test/b", "seed")], [])

        def fake_fetch(url, timeout=20):
            return _lgwks.CrawlResult(
                url=url, title=f"Doc {url[-1]}", text=body, links=[], status="ok", elapsed=0.01
            )

        with tempfile.TemporaryDirectory() as td:
            jarvis_root = Path(td) / "jarvis"
            gate_root = Path(td) / "gate"
            with mock.patch.object(_lgwks, "RUN_ROOT", jarvis_root), \
                 mock.patch.object(_sc, "RUN_ROOT", gate_root), \
                 mock.patch.object(_lgwks, "build_seed_urls", fake_seeds), \
                 mock.patch.object(_lgwks, "fetch_url", fake_fetch):
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    rc = _lgwks.crawl_command(self._legacy_args())
            self.assertEqual(rc, 0)

            # The gate is keyed on the run name ("dedup"); the run accumulates into
            # exactly one cumulative store under the (temp) substrate run root.
            store_dirs = [p for p in gate_root.glob("*") if (p / "relational.db").exists()]
            self.assertEqual(len(store_dirs), 1, "expected exactly one gate store")
            store = store_dirs[0]

            rel = sqlite3.connect(store / "relational.db")
            graph = sqlite3.connect(store / "graph.db")
            vrec = sqlite3.connect(store / "vector_records.db")
            try:
                docs = rel.execute("select count(*) from documents").fetchone()[0]
                chunks = rel.execute("select count(*) from chunks").fetchone()[0]
                chunk_cid = rel.execute("select artifact_cid from chunks").fetchone()[0]
                chunk_embeds = vrec.execute(
                    "select count(*) from vector_records where artifact_cid=?", (chunk_cid,)
                ).fetchone()[0]
                contains = graph.execute(
                    "select count(*) from edges where rel='contains'"
                ).fetchone()[0]
            finally:
                rel.close()
                graph.close()
                vrec.close()

        # Two distinct documents fetched...
        self.assertEqual(docs, 2)
        # ...but identical content collapses to ONE cid-keyed chunk + ONE embedding...
        self.assertEqual(chunks, 1)
        self.assertEqual(chunk_embeds, 1)
        # ...with a provenance edge from EACH document (lossless dedup).
        self.assertEqual(contains, 2)


if __name__ == "__main__":
    unittest.main()
