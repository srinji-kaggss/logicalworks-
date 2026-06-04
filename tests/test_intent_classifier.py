"""
Tests for lgwks_intent_classifier — the CLI-membrane intent classifier whose
confidence gates how much tool authority Claude receives.

Focus: the production-safety invariants, not accuracy ceilings (semantic-grade
accuracy needs the trained encoder). Specifically we prove the #29 fix — a
non-semantic path can never emit a score that unlocks execution — and that the
classifier is deterministic (the old _embed stub used np.random and was noise).
"""

from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_intent_classifier as ic


VERBS = [
    {"verb": "manifest", "intent": "list the tool surface and verbs available"},
    {"verb": "geo compile", "intent": "compile a geographic expression"},
    {"verb": "fetch", "intent": "single-page browser fetch and extraction"},
    {"verb": "refine", "intent": "machine intent refinement class gaps specificity"},
]


def _classifier() -> ic.IntentClassifier:
    centroids, semantic = ic._build_centroids(VERBS)
    return ic.IntentClassifier(
        classes=[v["verb"] for v in VERBS], centroids=centroids, semantic=semantic)


class _Hermetic(unittest.TestCase):
    # //why per-test, not module-import: lgwks_run.embed routes through a LIVE
    # Ollama when the Eye is up, so determinism requires LGWKS_NO_MODELS=1. Setting
    # it once at import is NOT enough — test_constitution.py pops the var in its
    # finally blocks and (under `discover`) runs before us, so the flag would be
    # gone by the time our methods run. setUp re-asserts it for every method and
    # tearDown restores the prior value, so these tests are leak-proof regardless
    # of sibling test ordering. is_up() reads the env live, so this fully forces
    # the deterministic feature-hash path (is_semantic=False).
    def setUp(self):
        self._prev_no_models = os.environ.get("LGWKS_NO_MODELS")
        os.environ["LGWKS_NO_MODELS"] = "1"

    def tearDown(self):
        if self._prev_no_models is None:
            os.environ.pop("LGWKS_NO_MODELS", None)
        else:
            os.environ["LGWKS_NO_MODELS"] = self._prev_no_models


class TestEmbeddingDeterminism(_Hermetic):
    def test_embed_is_deterministic(self):
        # //why: the old stub was np.random.randn — confidence was noise. Same
        # text must yield byte-identical vectors now (hermetic feature-hash path).
        self.assertEqual(ic._embed("show me the manifest"), ic._embed("show me the manifest"))

    def test_embed_returns_vector_and_semantic_flag(self):
        # //why: the embed seam now carries is_semantic — the bool that gates the
        # authority law. Under LGWKS_NO_MODELS it must be False (no real Eye).
        vec, is_semantic = ic._embed("compile a geo expression")
        self.assertIsInstance(vec, list)
        self.assertFalse(is_semantic, "no Eye in test env → non-semantic")

    def test_embed_is_unit_normalized(self):
        v, _ = ic._embed("compile a geo expression")
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=4)

    def test_distinct_text_distinct_vector(self):
        self.assertNotEqual(ic._embed("fetch this website")[0], ic._embed("compile geography")[0])

    def test_centroids_align_with_classes(self):
        c, semantic = ic._build_centroids(VERBS)
        self.assertEqual(len(c), len(VERBS))
        self.assertTrue(all(len(vec) == 256 for vec in c))
        self.assertFalse(semantic, "feature-hash centroids are not semantic")


class TestAuthorityLaw(_Hermetic):
    """The #29 structural guarantee: non-semantic methods cannot grant execution."""

    def test_clamp_caps_non_semantic_methods(self):
        for method in ("cosine", "keyword", "empty", "error", "anything"):
            self.assertLessEqual(ic._clamp_for_method(0.99, method), ic.LEXICAL_CONFIDENCE_CEILING)

    def test_clamp_passes_semantic_method(self):
        self.assertAlmostEqual(ic._clamp_for_method(0.99, "coreml"), 0.99, places=6)

    def test_clamp_guards_nan_and_range(self):
        self.assertEqual(ic._clamp_for_method(float("nan"), "coreml"), 0.0)
        self.assertEqual(ic._clamp_for_method(-5.0, "coreml"), 0.0)
        self.assertEqual(ic._clamp_for_method(5.0, "coreml"), 1.0)

    def test_lexical_ceiling_below_authority_bar(self):
        # //why structural: even at its ceiling a lexical method is strictly
        # below the full-authority bar — no tie, no rounding into execution.
        self.assertLess(ic.LEXICAL_CONFIDENCE_CEILING, ic.FULL_AUTHORITY_THRESHOLD)

    def test_cosine_result_never_grants_full_authority(self):
        clf = _classifier()
        probes = [
            "manifest", "show me the tool manifest please",
            "fetch https://example.com and extract", "geo compile expression",
            "refine my intent", "list verbs", "a" * 200, "manifest manifest manifest",
        ]
        for text in probes:
            r = clf.classify(text)
            self.assertFalse(r.grants_full_authority, f"lexical path granted authority on: {text!r}")
            self.assertLessEqual(r.confidence, ic.LEXICAL_CONFIDENCE_CEILING)

    def test_property_guard_is_method_gated_not_just_score(self):
        # A hand-forged high score on a non-semantic method must still be denied.
        forged = ic.ClassifyResult(label="manifest", confidence=0.99, method="cosine")
        self.assertFalse(forged.grants_full_authority)
        # The same score on the semantic method is allowed.
        semantic = ic.ClassifyResult(label="manifest", confidence=0.99, method="coreml")
        self.assertTrue(semantic.grants_full_authority)
        # Semantic but below the bar → denied.
        weak = ic.ClassifyResult(label="manifest", confidence=0.80, method="coreml")
        self.assertFalse(weak.grants_full_authority)
        # Semantic, high score, but no label → denied.
        blank = ic.ClassifyResult(label="", confidence=0.99, method="coreml")
        self.assertFalse(blank.grants_full_authority)


class TestGateBehavior(_Hermetic):
    def test_empty_input_is_plan_only(self):
        r = _classifier().classify("")
        self.assertEqual(r.method, "empty")
        self.assertEqual(r.confidence, 0.0)
        self.assertTrue(r.plan_only)
        self.assertFalse(r.grants_full_authority)

    def test_gibberish_is_plan_only(self):
        r = _classifier().classify("xyzzy plugh frobnicate qwerty zzzz")
        self.assertTrue(r.plan_only)
        self.assertFalse(r.grants_full_authority)

    def test_classify_is_deterministic(self):
        clf = _classifier()
        a = clf.classify("list the manifest verbs and tool surface")
        b = clf.classify("list the manifest verbs and tool surface")
        self.assertEqual((a.label, a.confidence, a.method), (b.label, b.confidence, b.method))

    def test_overlapping_query_ranks_right_verb(self):
        # Lexical overlap should at least surface the right verb in top_k.
        clf = _classifier()
        r = clf.classify("manifest tool surface list verbs")
        labels = [lbl for lbl, _ in r.top_k]
        self.assertIn("manifest", labels)

    def test_uses_cosine_path_not_keyword_fallback(self):
        # //why: the old bug left centroids=None so every call fell to keyword.
        # With centroids built, the live path must be cosine.
        r = _classifier().classify("compile a geographic expression")
        self.assertEqual(r.method, "cosine")


class TestLiveManifestGateIsSafe(_Hermetic):
    def test_real_load_never_grants_authority_without_model(self):
        # //why: end-to-end on the real manifest. With no trained .mlpackage
        # present, only lexical paths exist, so NOTHING may grant execution.
        try:
            clf = ic.IntentClassifier.load()
        except Exception as e:  # pragma: no cover - environment-dependent
            self.skipTest(f"manifest load unavailable: {e}")
        if not clf.classes:
            self.skipTest("manifest produced no verbs")
        for text in ["manifest", "crawl a site", "do something vague", "", "????"]:
            r = clf.classify(text)
            self.assertFalse(r.grants_full_authority, f"real gate granted authority on {text!r}")


if __name__ == "__main__":
    unittest.main()
