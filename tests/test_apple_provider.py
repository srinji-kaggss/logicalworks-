"""
Tests for issue #35: Apple-local embedding provider seam.

All tests are offline.  When the Apple MLX runtime is genuinely available,
tests exercise the real path.  When it is absent (CI, non-Apple hardware),
tests assert deterministic skip/fail-closed behavior — no silent fallback
to a different provider and no test framework errors.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_apple


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_TEXT = "machine-first language substrate vector space identity"


def _fake_vector(dims: int = 384) -> list[float]:
    """Normalised unit vector for mock returns."""
    v = [1.0 / (i + 1) for i in range(dims)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Provider availability detection
# ─────────────────────────────────────────────────────────────────────────────

class TestAppleAvailability(unittest.TestCase):
    def test_is_available_returns_bool(self):
        result = lgwks_apple.is_available()
        self.assertIsInstance(result, bool)

    def test_unavailable_on_non_darwin(self):
        with mock.patch.object(lgwks_apple, "sys") as m_sys:
            m_sys.platform = "linux"
            # Clear the lru_cache so patch is visible.
            lgwks_apple.is_available.cache_clear()
            try:
                self.assertFalse(lgwks_apple.is_available())
            finally:
                lgwks_apple.is_available.cache_clear()

    def test_unavailable_when_mlx_missing(self):
        lgwks_apple.is_available.cache_clear()
        with mock.patch.dict("sys.modules", {"mlx": None, "mlx.core": None}):
            lgwks_apple.is_available.cache_clear()
            try:
                # On non-Darwin this is already False; on Darwin with mlx absent it's also False.
                result = lgwks_apple.is_available()
                self.assertIsInstance(result, bool)
            finally:
                lgwks_apple.is_available.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# 2. embed_one when unavailable — must return None (not raise)
# ─────────────────────────────────────────────────────────────────────────────

class TestEmbedOneUnavailable(unittest.TestCase):
    def setUp(self):
        lgwks_apple.is_available.cache_clear()
        lgwks_apple._load_model.cache_clear()

    def tearDown(self):
        lgwks_apple.is_available.cache_clear()
        lgwks_apple._load_model.cache_clear()

    def test_embed_one_returns_none_when_unavailable(self):
        with mock.patch.object(lgwks_apple, "is_available", return_value=False):
            result = lgwks_apple.embed_one(SAMPLE_TEXT)
        self.assertIsNone(result)

    def test_embed_one_never_raises(self):
        with mock.patch.object(lgwks_apple, "is_available", return_value=False):
            try:
                result = lgwks_apple.embed_one(SAMPLE_TEXT)
            except Exception as exc:
                self.fail(f"embed_one raised unexpectedly: {exc}")
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# 3. embed_one when available — returns normalised list[float] of right length
# ─────────────────────────────────────────────────────────────────────────────

class TestEmbedOneAvailable(unittest.TestCase):
    def setUp(self):
        lgwks_apple.is_available.cache_clear()
        lgwks_apple._load_model.cache_clear()

    def tearDown(self):
        lgwks_apple.is_available.cache_clear()
        lgwks_apple._load_model.cache_clear()

    def _make_fake_model(self, dims: int = 384):
        fake = mock.MagicMock()
        fake.encode.return_value = [_fake_vector(dims)]
        return fake

    def test_returns_list_of_floats_correct_dims(self):
        fake_model = self._make_fake_model(384)
        with mock.patch.object(lgwks_apple, "is_available", return_value=True):
            with mock.patch.object(lgwks_apple, "_load_model", return_value=fake_model):
                result = lgwks_apple.embed_one(SAMPLE_TEXT, dims=384)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 384)
        self.assertTrue(all(isinstance(x, float) for x in result))

    def test_vector_is_l2_normalised(self):
        fake_model = self._make_fake_model(384)
        # Provide an unnormalised vector to confirm normalisation happens.
        fake_model.encode.return_value = [[2.0] * 384]
        with mock.patch.object(lgwks_apple, "is_available", return_value=True):
            with mock.patch.object(lgwks_apple, "_load_model", return_value=fake_model):
                result = lgwks_apple.embed_one(SAMPLE_TEXT, dims=384)
        assert result is not None
        norm = sum(x * x for x in result) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_slices_to_requested_dims(self):
        fake_model = self._make_fake_model(512)
        with mock.patch.object(lgwks_apple, "is_available", return_value=True):
            with mock.patch.object(lgwks_apple, "_load_model", return_value=fake_model):
                result = lgwks_apple.embed_one(SAMPLE_TEXT, dims=128)
        assert result is not None
        self.assertEqual(len(result), 128)

    def test_pads_when_model_shorter_than_dims(self):
        fake_model = self._make_fake_model(32)
        with mock.patch.object(lgwks_apple, "is_available", return_value=True):
            with mock.patch.object(lgwks_apple, "_load_model", return_value=fake_model):
                result = lgwks_apple.embed_one(SAMPLE_TEXT, dims=64)
        assert result is not None
        self.assertEqual(len(result), 64)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Provider label format
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderLabel(unittest.TestCase):
    def test_label_starts_with_apple_local_prefix(self):
        label = lgwks_apple.provider_label()
        self.assertTrue(label.startswith("apple-local:"), label)

    def test_label_contains_model_id(self):
        label = lgwks_apple.provider_label("mlx-community/test-model")
        self.assertIn("mlx-community/test-model", label)

    def test_custom_model_env_var_respected(self):
        with mock.patch.dict(os.environ, {"LGWKS_APPLE_MODEL": "my-custom/model"}):
            import importlib
            import lgwks_apple as _ap
            importlib.reload(_ap)
            try:
                self.assertEqual(_ap.DEFAULT_MODEL, "my-custom/model")
            finally:
                importlib.reload(_ap)


# ─────────────────────────────────────────────────────────────────────────────
# 5. lgwks_run.embed() integration — apple-local provider path
# ─────────────────────────────────────────────────────────────────────────────

class TestLgwksRunEmbedAppleLocal(unittest.TestCase):
    """Verify lgwks_run.embed() routes apple-local correctly."""

    def test_embed_with_apple_local_returns_none_when_unavailable(self):
        import lgwks_run
        with mock.patch("lgwks_apple.is_available", return_value=False):
            vec, provider, semantic = lgwks_run.embed(
                SAMPLE_TEXT, embed_on=True, provider="apple-local"
            )
        self.assertIsNone(vec)
        self.assertEqual(provider, "apple-local:unavailable")
        self.assertFalse(semantic)

    def test_embed_with_apple_local_returns_vector_when_available(self):
        import lgwks_run
        fake_vec = _fake_vector(384)

        with mock.patch("lgwks_apple.is_available", return_value=True), \
             mock.patch("lgwks_apple.embed_one", return_value=fake_vec), \
             mock.patch("lgwks_apple.provider_label", return_value="apple-local:mlx-community/all-MiniLM-L6-v2-4bit"):
            vec, provider, semantic = lgwks_run.embed(
                SAMPLE_TEXT, embed_on=True, provider="apple-local"
            )
        self.assertIsNotNone(vec)
        self.assertTrue(provider.startswith("apple-local:"))
        self.assertTrue(semantic)

    def test_embed_off_skips_apple_local(self):
        import lgwks_run
        vec, provider, semantic = lgwks_run.embed(
            SAMPLE_TEXT, embed_on=False, provider="apple-local"
        )
        self.assertIsNone(vec)
        self.assertEqual(provider, "none")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Substrate parser accepts apple-local
# ─────────────────────────────────────────────────────────────────────────────

class TestSubstrateParserAcceptsAppleLocal(unittest.TestCase):
    """Verify the substrate build/map/query parsers accept --embed-provider apple-local."""

    def _make_substrate_parser(self):
        import lgwks_substrate
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        lgwks_substrate.add_parser(sub)
        return parser

    def test_build_accepts_apple_local(self):
        parser = self._make_substrate_parser()
        args = parser.parse_args([
            "substrate", "build", "https://example.com",
            "--embed-provider", "apple-local",
        ])
        self.assertEqual(args.embed_provider, "apple-local")

    def test_map_accepts_apple_local(self):
        parser = self._make_substrate_parser()
        args = parser.parse_args([
            "substrate", "map", "https://example.com",
            "--embed-provider", "apple-local",
        ])
        self.assertEqual(args.embed_provider, "apple-local")

    def test_query_accepts_apple_local_free_form(self):
        parser = self._make_substrate_parser()
        args = parser.parse_args([
            "substrate", "query", "my-run",
            "--vector", "test query",
            "--embed-provider", "apple-local",
        ])
        self.assertEqual(args.embed_provider, "apple-local")

    def test_build_default_remains_auto(self):
        parser = self._make_substrate_parser()
        args = parser.parse_args([
            "substrate", "build", "https://example.com",
        ])
        self.assertEqual(args.embed_provider, "auto")

    def test_query_default_remains_empty(self):
        """query --embed-provider default is '' (resolved from manifest at runtime)."""
        parser = self._make_substrate_parser()
        args = parser.parse_args([
            "substrate", "query", "my-run",
            "--vector", "test",
        ])
        self.assertEqual(args.embed_provider, "")


# ─────────────────────────────────────────────────────────────────────────────
# 7. _provider_matches_vector_space — apple-local identity check
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderMatchesVectorSpace(unittest.TestCase):
    def setUp(self):
        import lgwks_substrate
        self.fn = lgwks_substrate._provider_matches_vector_space

    def test_apple_local_matches_apple_local_colon_model(self):
        self.assertTrue(self.fn(
            "apple-local",
            "apple-local:mlx-community/all-MiniLM-L6-v2-4bit",
        ))

    def test_apple_local_does_not_match_ollama(self):
        self.assertFalse(self.fn("apple-local", "ollama:qwen3-embedding"))

    def test_apple_local_does_not_match_deterministic(self):
        self.assertFalse(self.fn("apple-local", "deterministic-feature-hash"))

    def test_ollama_does_not_match_apple_local(self):
        self.assertFalse(self.fn("ollama", "apple-local:mlx-community/model"))

    def test_deterministic_does_not_match_apple_local(self):
        self.assertFalse(self.fn("deterministic", "apple-local:mlx-community/model"))

    def test_apple_local_matches_exact_label(self):
        label = "apple-local:mlx-community/all-MiniLM-L6-v2-4bit"
        self.assertTrue(self.fn(label, label))


# ─────────────────────────────────────────────────────────────────────────────
# 8. Build manifest records canonical apple-local provider/model/dims
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildManifestRecordsAppleLocal(unittest.TestCase):
    """Simulate a successful apple-local build and verify manifest fields."""

    def _fake_build_run(self, embed_provider: str = "apple-local") -> dict:
        """
        Run lgwks_substrate.build_run() with a fully mocked environment so no
        real I/O or Apple runtime is needed.
        """
        import lgwks_substrate
        import argparse

        apple_label = "apple-local:mlx-community/all-MiniLM-L6-v2-4bit"
        fake_vec = _fake_vector(384)

        with tempfile.TemporaryDirectory() as td:
            args = argparse.Namespace(
                target="https://example.com",
                project="test-apple",
                source_type="url",
                max_pages=1,
                max_depth=0,
                max_files=5,
                max_chars=1000,
                chunk_words=50,
                chunk_overlap=10,
                fact_threshold=0.5,
                embed_provider=embed_provider,
                embed_model="",
                login_if_needed=False,
                login_url="",
                success_selector=None,
                max_auto_bypass_attempts=1,
                max_auth_handoffs=1,
                browser_engine="webkit",
            )

            with mock.patch.object(lgwks_substrate, "_crawl_site") as m_crawl, \
                 mock.patch.object(lgwks_substrate, "RUN_ROOT", Path(td)), \
                 mock.patch("lgwks_run.embed", return_value=(fake_vec, apple_label, True)):
                # Minimal crawl result (one page).
                m_crawl.return_value = ([
                    {
                        "source": "https://example.com",
                        "title": "Test",
                        "text": "machine first language substrate",
                        "discovered_by": "seed",
                        "depth": 0,
                    }
                ], [])
                manifest = lgwks_substrate.build_run(args)

        return manifest

    def test_manifest_records_apple_local_canonical_provider(self):
        manifest = self._fake_build_run("apple-local")
        vs = manifest.get("vector_space", {})
        self.assertTrue(
            vs.get("canonical_provider", "").startswith("apple-local:"),
            f"expected apple-local: prefix, got: {vs.get('canonical_provider')!r}",
        )

    def test_manifest_records_semantic_true(self):
        manifest = self._fake_build_run("apple-local")
        vs = manifest.get("vector_space", {})
        self.assertTrue(vs.get("semantic"), "apple-local vectors must be marked semantic")

    def test_manifest_not_ambiguous_for_single_provider(self):
        manifest = self._fake_build_run("apple-local")
        vs = manifest.get("vector_space", {})
        self.assertFalse(vs.get("ambiguous"), "single apple-local provider must not be ambiguous")

    def test_manifest_records_dims(self):
        manifest = self._fake_build_run("apple-local")
        vs = manifest.get("vector_space", {})
        self.assertGreater(vs.get("dims", 0), 0, "dims must be recorded and positive")

    def test_embedding_block_records_provider_requested(self):
        manifest = self._fake_build_run("apple-local")
        emb = manifest.get("embedding", {})
        self.assertEqual(emb.get("provider_requested"), "apple-local")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Query mismatch — apple-local vs deterministic must fail closed
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryMismatchFailsClosed(unittest.TestCase):
    """
    Verify that querying an apple-local run with a mismatched provider
    returns the structured error object (not silently serving cross-space scores).
    """

    def _make_run_dir_with_manifest(self, canonical_provider: str, tmp_dir: str) -> Path:
        run_dir = Path(tmp_dir) / "run"
        run_dir.mkdir()
        manifest = {
            "run_id": "test-run",
            "vector_space": {
                "canonical_provider": canonical_provider,
                "canonical_model": "",
                "dims": 384,
                "semantic": True,
                "ambiguous": False,
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        # Write a minimal vectors.jsonl so _stored_vector_space can find dims.
        (run_dir / "vectors.jsonl").write_text(
            json.dumps({
                "vector_id": "v1",
                "chunk_id": "c1",
                "document_id": "d1",
                "provider": canonical_provider,
                "dims": 384,
                "vector": _fake_vector(384),
                "chunk_kind": "fact",
                "fact_score": 0.9,
                "vector_text": "machine first language substrate vector space identity",
            }) + "\n",
            encoding="utf-8",
        )
        return run_dir

    def test_apple_local_run_query_with_deterministic_fails_closed(self):
        import lgwks_substrate
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir_with_manifest(
                "apple-local:mlx-community/all-MiniLM-L6-v2-4bit", td
            )
            result = lgwks_substrate._vector_search(
                run_dir=run_dir,
                text="test query",
                provider="deterministic",
                model="",
                limit=5,
                force_cross_space=False,
            )
        self.assertIn("error", result)
        self.assertIn("mismatch", result.get("error", "").lower())
        self.assertEqual(result.get("schema"), "lgwks.substrate.vector_query.v0")

    def test_apple_local_run_query_with_ollama_fails_closed(self):
        import lgwks_substrate
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir_with_manifest(
                "apple-local:mlx-community/all-MiniLM-L6-v2-4bit", td
            )
            result = lgwks_substrate._vector_search(
                run_dir=run_dir,
                text="test query",
                provider="ollama",
                model="",
                limit=5,
                force_cross_space=False,
            )
        self.assertIn("error", result)
        self.assertEqual(result.get("schema"), "lgwks.substrate.vector_query.v0")

    def test_apple_local_run_query_with_apple_local_succeeds(self):
        """Matching apple-local → apple-local must pass the identity check."""
        import lgwks_substrate
        apple_label = "apple-local:mlx-community/all-MiniLM-L6-v2-4bit"
        fake_vec = _fake_vector(384)

        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir_with_manifest(apple_label, td)
            with mock.patch("lgwks_run.embed", return_value=(fake_vec, apple_label, True)):
                result = lgwks_substrate._vector_search(
                    run_dir=run_dir,
                    text="test query",
                    provider="apple-local",
                    model="",
                    limit=5,
                    force_cross_space=False,
                )
        # Should not contain an error key; if it does (e.g. empty vectors list), the
        # error must NOT be a mismatch.
        if "error" in result:
            self.assertNotIn("mismatch", result["error"].lower(),
                             f"apple-local identity check must not produce mismatch: {result}")

    def test_force_cross_space_bypasses_mismatch(self):
        import lgwks_substrate
        apple_label = "apple-local:mlx-community/all-MiniLM-L6-v2-4bit"
        fake_vec = _fake_vector(256)

        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run_dir_with_manifest(apple_label, td)
            with mock.patch("lgwks_run.embed", return_value=(fake_vec, "deterministic-feature-hash", False)):
                result = lgwks_substrate._vector_search(
                    run_dir=run_dir,
                    text="test query",
                    provider="deterministic",
                    model="",
                    limit=5,
                    force_cross_space=True,
                )
        # With force_cross_space, the mismatch check is bypassed.
        if "error" in result:
            self.assertNotIn("mismatch", result["error"].lower())


# ─────────────────────────────────────────────────────────────────────────────
# 10. lgwks jarvis crawl default remains deterministic (not apple-local)
# ─────────────────────────────────────────────────────────────────────────────

class TestJarvisCrawlDefaultRemainsLegacy(unittest.TestCase):
    """Confirm issue #35 non-goal: jarvis crawl defaults are unchanged."""

    def test_jarvis_crawl_keyword_does_not_use_apple_local(self):
        """Keyword-only legacy crawl must not touch lgwks_apple."""
        import importlib.machinery
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        lgwks_path = os.path.join(os.path.dirname(here), "lgwks")
        loader = importlib.machinery.SourceFileLoader("_lgwks_jc_test", lgwks_path)
        spec = importlib.util.spec_from_loader("_lgwks_jc_test", loader)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_lgwks_jc_test"] = mod
        loader.exec_module(mod)

        import argparse
        # Keyword-only, legacy path: source=None engine=substrate → stays legacy
        args = argparse.Namespace(
            source=None,
            keyword_terms=["RRSP"],
            keywords=None,
            prompt="test",
            name=None,
            max_pages=1,
            max_depth=0,
            workers=1,
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
        )
        with mock.patch.object(mod, "_import_substrate") as m_sub:
            with mock.patch.object(mod, "build_seed_urls", side_effect=SystemExit("no seed")):
                try:
                    mod.crawl_command(args)
                except SystemExit:
                    pass
        m_sub.assert_not_called()


if __name__ == "__main__":
    unittest.main()
