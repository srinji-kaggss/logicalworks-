"""Invariant audit for lgwks_engine — U6.1 (issue #83).

This is the *agnostic* audit: it certifies the math by algebraic invariants that
must hold for ANY inputs, not by a domain-specific ground-truth set. The pure
operators (_decisiveness, _aggregate) are tested directly with synthetic inputs;
run_engine is checked for the degeneracy regression and score bounds.

I1 range          I2 determinism      I3 monotonicity     I4 cardinality-invariance
I6 null-collapse  I7 boundary         relabel-invariance  (regression: G != 1 - C)
I8 padding/verbosity-invariance (demand-weighted coverage — #86)

Deferred (NOT audited here): N novelty (needs the Qwen embedding layer).
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_engine as eng


class TestDecisiveness(unittest.TestCase):
    def test_i1_range(self):
        for scores in ([], [0.0], [1.0], [3.0, 1.0], [0.5, 0.5, 0.5], [1.333, 1.0, 1.0]):
            d = eng._decisiveness(scores)
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, 1.0)

    def test_i3_monotonicity(self):
        # a clearer dominant match -> higher decisiveness
        tie = eng._decisiveness([0.5, 0.5])
        clear = eng._decisiveness([0.9, 0.1])
        dominant = eng._decisiveness([0.99, 0.01])
        self.assertLess(tie, clear)
        self.assertLess(clear, dominant)
        self.assertAlmostEqual(tie, 0.0, places=3)

    def test_i4_cardinality_invariance(self):
        # adding a zero-score (non-matching) capability must not change d
        base = eng._decisiveness([3.0, 1.0])
        padded = eng._decisiveness([3.0, 1.0, 0.0, 0.0, 0.0])
        self.assertEqual(base, padded)

    def test_relabel_invariance(self):
        # d depends only on the score multiset, never on order/labels
        self.assertEqual(eng._decisiveness([3.0, 1.0, 0.5]),
                         eng._decisiveness([0.5, 3.0, 1.0]))

    def test_i7_boundary(self):
        self.assertEqual(eng._decisiveness([]), 0.0)        # nothing -> not decisive
        self.assertEqual(eng._decisiveness([2.0]), 1.0)     # single match -> fully decisive
        self.assertEqual(eng._decisiveness([1.0, 1.0]), 0.0)  # tie -> not decisive


class TestAggregate(unittest.TestCase):
    def test_i1_range(self):
        for axes in ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.5, 0.3, 0.9), (0.6, None, 0.4)):
            p = eng._aggregate(*axes)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_i6_null_collapse(self):
        # any zero axis collapses the index to 0
        self.assertEqual(eng._aggregate(0.0, 0.9, 0.9), 0.0)
        self.assertEqual(eng._aggregate(0.9, 0.0, 0.9), 0.0)
        self.assertEqual(eng._aggregate(0.9, 0.9, 0.0), 0.0)

    def test_none_axes_drop_out(self):
        # an unavailable (None) axis drops out rather than zeroing the index
        self.assertEqual(eng._aggregate(0.5, None, 0.5), eng._aggregate(0.5, 0.5))
        self.assertGreater(eng._aggregate(0.5, None, 0.5), 0.0)

    def test_i3_monotonicity(self):
        base = eng._aggregate(0.5, 0.5, 0.5)
        higher = eng._aggregate(0.5, 0.5, 0.9)
        self.assertLess(base, higher)

    def test_i7_boundary(self):
        self.assertEqual(eng._aggregate(1.0, 1.0, 1.0), 1.0)  # perfect -> 1
        self.assertEqual(eng._aggregate(), 0.0)               # nothing available -> 0

    def test_non_finite_dropped_not_maxed(self):
        # inf/nan must NOT become max confidence (min(1.0, nan) bug) — they drop out.
        self.assertEqual(eng._aggregate(float("inf"), 0.5), eng._aggregate(0.5))
        self.assertEqual(eng._aggregate(float("nan"), 0.5), eng._aggregate(0.5))
        self.assertTrue(math.isfinite(eng._decisiveness([float("inf"), 1.0])))
        self.assertTrue(math.isfinite(eng._decisiveness([float("nan"), float("nan")])))


class TestRunEngineContract(unittest.TestCase):
    PROMPT = "refactor the auth module and check for SQL injection"

    def test_degeneracy_regression(self):
        # The whole point of #83. Force the ungrounded branch for determinism.
        s = eng.run_engine(self.PROMPT, db_path=Path("/nonexistent/graph.db"))["insights"]["scores"]
        C, P = s["coverage_C"], s["confidence_P"]
        # Old engine ALWAYS returned gap_G = round(1 - C, 3) (a float, never None);
        # the new one returns None when ungrounded -> the "G = 1 - C" construction is gone.
        self.assertIsNone(s["gap_G"])
        self.assertEqual(s["grounding_status"], "unavailable")
        # P is no longer the old magic-constant closed form in C.
        old_P = round(0.30 + 0.58 * C * (1.0 - 0.2 * max(0.0, 1.0 - C)), 3)
        self.assertNotEqual(P, old_P)
        self.assertIn("decisiveness_d", s)

    def test_i1_run_bounds(self):
        for p in [self.PROMPT, "embed a PDF", "xyzzy frobnicate", ""]:
            s = eng.run_engine(p)["insights"]["scores"]
            self.assertGreaterEqual(s["coverage_C"], 0.0)
            self.assertLessEqual(s["coverage_C"], 1.0)
            self.assertGreaterEqual(s["decisiveness_d"], 0.0)
            self.assertLessEqual(s["decisiveness_d"], 1.0)
            self.assertGreaterEqual(s["confidence_P"], 0.0)
            self.assertLessEqual(s["confidence_P"], 1.0)
            self.assertIn(s["grounding_status"], ("grounded", "unresolved", "unavailable"))

    def test_i2_determinism(self):
        a = eng.run_engine(self.PROMPT)
        b = eng.run_engine(self.PROMPT)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_corrupt_graph_is_unavailable_not_zero_grounded(self):
        # A corrupt/unreadable DB must read as grounding *unavailable* (drops out),
        # NOT as "queried, grounded nothing" (which would silently zero P).
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"this is not a sqlite database")
            bad = Path(f.name)
        try:
            s = eng.run_engine(self.PROMPT, db_path=bad)["insights"]["scores"]
            self.assertEqual(s["grounding_status"], "unavailable")
            self.assertIsNone(s["gap_G"])
        finally:
            bad.unlink(missing_ok=True)

    def test_ungrounded_does_not_zero_confidence(self):
        # no graph -> grounding unavailable, but a covered+decisive prompt still
        # yields P > 0 (grounding drops out; it does not force confidence to 0).
        s = eng.run_engine(self.PROMPT, db_path=Path("/nonexistent/graph.db"))["insights"]["scores"]
        self.assertEqual(s["grounding_status"], "unavailable")
        self.assertIsNone(s["gap_G"])
        if s["coverage_C"] > 0 and s["decisiveness_d"] > 0:
            self.assertGreater(s["confidence_P"], 0.0)


class TestDemandWeighting(unittest.TestCase):
    """I8 — padding/verbosity-invariance via capability-vocabulary demand weights."""

    def test_idf_common_lt_rare(self):
        # A token in every capability discriminates nothing -> lower weight than a
        # token specific to one. Smoothed, so every weight stays positive.
        verbs = [
            {"verb": "alpha", "intent": "shared everywhere token"},
            {"verb": "beta", "intent": "shared everywhere token"},
            {"verb": "gamma", "intent": "shared everywhere rareword"},
        ]
        idf = eng._compute_capability_idf(verbs)
        self.assertLess(idf["shared"], idf["rareword"])
        self.assertTrue(all(w > 0.0 for w in idf.values()))

    def test_oov_filler_carries_zero_demand(self):
        demand = eng._compute_capability_idf([{"verb": "refactor", "intent": "rewrite code"}])
        self.assertEqual(demand.get("zzzqux", 0.0), 0.0)  # absent -> zero demand

    def test_i8_padding_invariance_exact(self):
        # Padding a prompt with guaranteed-OOV filler leaves C EXACTLY unchanged:
        # zero-demand tokens enter neither numerator nor denominator.
        db = Path("/nonexistent/graph.db")
        base = eng.run_engine("refactor the auth module", db_path=db)
        padded = eng.run_engine("refactor the auth module zzzqux blargh frobnix wibble", db_path=db)
        self.assertEqual(base["insights"]["scores"]["coverage_C"],
                         padded["insights"]["scores"]["coverage_C"])

    def test_i8_demand_weighting_is_the_fix(self):
        # Contrastive proof: under UNIFORM weights the same OOV padding lowers C
        # (denominator grows); demand weights are precisely what make it invariant.
        verbs = [{"verb": "auth", "intent": "manage auth", "score": 2.0}]
        demand = eng._compute_capability_idf(verbs)
        c_uni_base, _ = eng._capability_coverage(["auth"], verbs, demand=None)
        c_uni_pad, _ = eng._capability_coverage(["auth", "zzzqux", "blargh"], verbs, demand=None)
        c_dem_base, _ = eng._capability_coverage(["auth"], verbs, demand=demand)
        c_dem_pad, _ = eng._capability_coverage(["auth", "zzzqux", "blargh"], verbs, demand=demand)
        self.assertGreater(c_uni_base, c_uni_pad)   # uniform: padding hurts
        self.assertEqual(c_dem_base, c_dem_pad)      # demand: padding-invariant

    def test_coverage_mode_reported(self):
        s = eng.run_engine("refactor the auth module")["insights"]["scores"]
        self.assertIn(s["coverage_mode"], ("lexical", "lexical+demand", "qwen"))


class TestCosine(unittest.TestCase):
    """U6.2 — cosine is pure arithmetic on given vectors; guards on degenerate input."""

    def test_identities(self):
        self.assertAlmostEqual(eng._cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]), 1.0)
        self.assertAlmostEqual(eng._cosine([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]), 0.0)
        self.assertAlmostEqual(eng._cosine([1.0, 0.0], [-1.0, 0.0]), -1.0)

    def test_guards(self):
        self.assertEqual(eng._cosine([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)   # shape mismatch
        self.assertEqual(eng._cosine([0.0, 0.0], [1.0, 0.0]), 0.0)         # zero vector
        self.assertEqual(eng._cosine([], []), 0.0)                          # empty
        self.assertEqual(eng._cosine([float("inf"), 0.0], [1.0, 0.0]), 0.0)  # non-finite

    def test_ranking(self):
        q = [1.0, 1.0, 0.0]
        near = eng._cosine(q, [1.0, 0.9, 0.0])
        far = eng._cosine(q, [0.0, 0.0, 1.0])
        self.assertGreater(near, far)


class TestEmbeddingCoverage(unittest.TestCase):
    """U6.2 — Qwen-cosine coverage path + its availability gate (no model needed:
    the embed port is stubbed, so this verifies the WIRING deterministically)."""

    @staticmethod
    def _swap_port(port_cls):
        import types
        stub = types.SimpleNamespace(EmbedPort=port_cls)
        old = sys.modules.get("lgwks_embed_port")
        sys.modules["lgwks_embed_port"] = stub
        return old

    @staticmethod
    def _restore_port(old):
        if old is not None:
            sys.modules["lgwks_embed_port"] = old
        else:
            sys.modules.pop("lgwks_embed_port", None)

    def test_qwen_coverage_with_stub_port(self):
        artifact = {"dim": 3, "verbs": [
            {"verb": "alpha", "intent": "a", "vec": [1.0, 0.0, 0.0]},
            {"verb": "beta", "intent": "b", "vec": [0.0, 1.0, 0.0]},
        ]}

        class _Port:
            def __init__(self, *a, **k):
                pass
            def embed_text(self, text, instruction=""):
                return [1.0, 0.0, 0.0]   # identical to alpha, orthogonal to beta
            def close(self):
                pass

        old = self._swap_port(_Port)
        try:
            res = eng._embedding_coverage("anything", artifact)
        finally:
            self._restore_port(old)
        self.assertIsNotNone(res)
        C, sels = res
        self.assertEqual(C, 1.0)                     # top cosine = identical match
        self.assertEqual(sels[0]["verb"], "alpha")   # ranked first
        self.assertAlmostEqual(sels[1]["score"], 0.0, places=3)  # orthogonal -> 0

    def test_unavailable_port_returns_none(self):
        class _Port:
            def __init__(self, *a, **k):
                raise RuntimeError("no model downloaded")  # ~ EmbedUnavailableError

        old = self._swap_port(_Port)
        try:
            res = eng._embedding_coverage("x", {"dim": 3, "verbs": [{"verb": "a", "vec": [1.0, 0.0, 0.0]}]})
        finally:
            self._restore_port(old)
        self.assertIsNone(res)   # caller must fall back to the lexical floor

    def test_engine_default_is_lexical_floor(self):
        # No frozen vector artifact on this machine -> engine uses the lexical
        # floor, never errors, never claims qwen mode.
        s = eng.run_engine("refactor the auth module")["insights"]["scores"]
        self.assertIn(s["coverage_mode"], ("lexical", "lexical+demand"))


class TestArtifactTampering(unittest.TestCase):
    """The frozen .lgwks/*.json artifacts are an untrusted input surface. A
    tampered/corrupt artifact must NEVER raise out of run_engine (INV-6) or push a
    score out of [0,1] — it must degrade silently to the lexical floor. These
    regressions cover the three HIGH findings from the 2026-06-11 adversarial pass.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._idf_orig = eng._CAP_IDF_ARTIFACT
        self._vec_orig = eng._CAP_VEC_ARTIFACT
        eng._CAP_IDF_ARTIFACT = Path(self._tmp.name) / "capability_idf.json"
        eng._CAP_VEC_ARTIFACT = Path(self._tmp.name) / "capability_vectors.json"

    def tearDown(self):
        eng._CAP_IDF_ARTIFACT = self._idf_orig
        eng._CAP_VEC_ARTIFACT = self._vec_orig
        self._tmp.cleanup()
        sys.modules.pop("lgwks_embed_port", None)

    def _C(self):
        return eng.run_engine("refactor the auth module",
                              db_path=Path("/nonexistent/g.db"))["insights"]["scores"]["coverage_C"]

    def test_negative_idf_weight_clamped(self):
        eng._CAP_IDF_ARTIFACT.write_text('{"idf":{"refactor":100.0,"auth":100.0,"module":-199.9}}')
        c = self._C()
        self.assertGreaterEqual(c, 0.0)
        self.assertLessEqual(c, 1.0)

    def test_nonfinite_idf_weight_dropped(self):
        for literal in ('{"idf":{"refactor":Infinity,"auth":1.0,"module":1.0}}',
                        '{"idf":{"refactor":NaN,"auth":1.0,"module":1.0}}'):
            eng._CAP_IDF_ARTIFACT.write_text(literal)
            c = self._C()
            self.assertTrue(math.isfinite(c))
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)

    def test_poisoned_vectors_do_not_raise(self):
        # str vecs, non-dict records, non-list verbs, lying dim — with a working
        # stub port — must all fall back to lexical, never raise (HIGH#1).
        class _Port:
            def __init__(self, *a, **k):
                pass
            def embed_text(self, text, instruction=""):
                return [1.0, 0.0, 0.0]
            def close(self):
                pass
        import types
        for poison in ('{"dim":3,"verbs":[{"verb":"a","vec":["x","y","z"]}]}',
                       '{"dim":3,"verbs":1234}',
                       '{"dim":3,"verbs":[42]}',
                       '{"dim":-5,"verbs":[{"verb":"a","vec":[1,0,0]}]}',
                       '{"verbs":[{"vec":[NaN,0,0]}]}'):
            eng._CAP_VEC_ARTIFACT.write_text(poison)
            sys.modules["lgwks_embed_port"] = types.SimpleNamespace(EmbedPort=_Port)
            try:
                s = eng.run_engine("refactor the auth module")["insights"]["scores"]
            except Exception as exc:  # noqa: BLE001
                self.fail(f"run_engine raised on poisoned vectors {poison[:40]}: {exc!r}")
            finally:
                sys.modules.pop("lgwks_embed_port", None)
            # The invariant is: never raise, and C stays a finite [0,1] axis —
            # whether it fell back to lexical or salvaged a valid-vec record.
            self.assertIn(s["coverage_mode"], ("lexical", "lexical+demand", "qwen"))
            self.assertTrue(math.isfinite(s["coverage_C"]))
            self.assertGreaterEqual(s["coverage_C"], 0.0)
            self.assertLessEqual(s["coverage_C"], 1.0)


class TestInputBounds(unittest.TestCase):
    def test_oversized_prompt_capped_and_fast(self):
        import time
        big = "a and also b " * 1_500_000  # ~20MB
        t0 = time.time()
        s = eng.run_engine(big, db_path=Path("/nonexistent/g.db"))["insights"]["scores"]
        self.assertLess(time.time() - t0, 1.0)  # INV-7
        self.assertGreaterEqual(s["coverage_C"], 0.0)
        self.assertLessEqual(s["coverage_C"], 1.0)

    def test_non_str_verb_tokens_no_raise(self):
        # the demand recompute path must tolerate non-str verb/intent fields
        self.assertIsInstance(eng._compute_capability_idf([{"verb": 123, "intent": None}]), dict)


if __name__ == "__main__":
    unittest.main()
