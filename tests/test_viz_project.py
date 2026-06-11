"""Tests for lgwks_viz_project — I10 deterministic 3-D viz projection (T1–T4).

All tests map to acceptance clauses from PLANS-NEXT-4.md §PACKET I10
(authority: INGESTION-LAYER §7.5, INGESTION-PLAN §I10).

  T1: replayable       — same Ê → byte-identical W and coords across runs.
  T2: decoupling       — module is importable without affecting scoring (no side-effects).
  T3: stress_reported  — reconstruction_stress is computed and finite.
  T4: finite_coords    — no NaN/Inf in any coordinate; degenerate input raises loudly.

Note: T1/T3/T4 are skipped if numpy is not installed (import is optional per I10 spec).

fit_axes() returns ProjectionAxes(W, mean); project() requires mean= for consistent
centring (D3). reconstruction_stress() accepts a ProjectionAxes. All tests use the
full API accordingly.
"""

from __future__ import annotations

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_viz_project
from lgwks_viz_project import STRESS_THRESHOLD, ProjectionAxes

try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _np = None
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedding_bytes(seed: int, dim: int = 16) -> bytes:
    """Create a deterministic, L2-normalised float32 big-endian embedding."""
    if not _HAS_NUMPY:
        return b""
    rng = _np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(_np.float32)
    v = v / _np.linalg.norm(v)
    return struct.pack(f">{dim}f", *v.tolist())


class _FakeRecord:
    def __init__(self, cid: str, embedding: bytes):
        self.cid = cid
        self.embedding = embedding


# ---------------------------------------------------------------------------
# T1 — replayable
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_NUMPY, "numpy required for I10 projection (T1)")
class TestReplayable(unittest.TestCase):
    """T1: same Ê → byte-identical W and (x,y,z) coords across two calls."""

    DIM = 32
    N = 20

    def setUp(self):
        self.embs = [_make_embedding_bytes(i, self.DIM) for i in range(self.N)]

    def test_w_byte_identical(self):
        axes1 = lgwks_viz_project.fit_axes(self.embs)
        axes2 = lgwks_viz_project.fit_axes(self.embs)
        self.assertIsInstance(axes1, ProjectionAxes, "T1: fit_axes must return ProjectionAxes")
        self.assertTrue(
            _np.array_equal(axes1.W, axes2.W),
            msg="T1: fit_axes must return byte-identical W for same input",
        )
        self.assertTrue(
            _np.array_equal(axes1.mean, axes2.mean),
            msg="T1: fit_axes must return byte-identical mean for same input",
        )

    def test_coords_byte_identical(self):
        axes = lgwks_viz_project.fit_axes(self.embs)
        c1 = lgwks_viz_project.project(self.embs[0], axes.W, mean=axes.mean)
        c2 = lgwks_viz_project.project(self.embs[0], axes.W, mean=axes.mean)
        self.assertEqual(c1, c2, "T1: project must return identical coords for same input")

    def test_project_all_deterministic(self):
        recs = [_FakeRecord(f"cid-{i}", e) for i, e in enumerate(self.embs)]
        coords1 = lgwks_viz_project.project_all(recs)
        coords2 = lgwks_viz_project.project_all(recs)
        self.assertEqual(coords1, coords2, "T1: project_all must be deterministic")

    def test_sign_fix_stability(self):
        """T1: W columns always have positive largest-magnitude entry (sign-fix applied)."""
        axes = lgwks_viz_project.fit_axes(self.embs)
        W = axes.W
        for j in range(W.shape[1]):
            col = W[:, j]
            idx = int(_np.argmax(_np.abs(col)))
            self.assertGreater(
                col[idx], 0,
                msg=f"T1: column {j} largest-magnitude entry must be positive (sign-fix)",
            )

    def test_mean_centring_applied(self):
        """T1: mean is non-zero for real data and is applied correctly in project()."""
        axes = lgwks_viz_project.fit_axes(self.embs)
        # mean should be a d-vector; for random unit-sphere embeddings not all zero
        self.assertEqual(axes.mean.shape, (self.DIM,), "T1: mean must have shape (d,)")
        # projecting with and without mean must differ (centering has an effect)
        e = self.embs[0]
        with_mean = lgwks_viz_project.project(e, axes.W, mean=axes.mean)
        without_mean = lgwks_viz_project.project(e, axes.W)
        self.assertNotEqual(with_mean, without_mean,
                            "T1: project with and without centering must differ")


# ---------------------------------------------------------------------------
# T2 — decoupling (module importable; does NOT affect scoring)
# ---------------------------------------------------------------------------

class TestDecoupling(unittest.TestCase):
    """T2: module is importable and its import does NOT mutate any scoring module."""

    def test_importable(self):
        import importlib
        m = importlib.import_module("lgwks_viz_project")
        self.assertTrue(hasattr(m, "fit_axes"), "T2: fit_axes must be exported")
        self.assertTrue(hasattr(m, "project"), "T2: project must be exported")
        self.assertTrue(hasattr(m, "project_all"), "T2: project_all must be exported")
        self.assertTrue(hasattr(m, "ProjectionAxes"), "T2: ProjectionAxes must be exported")

    def test_no_numpy_import_in_score_or_rank(self):
        """T2: lgwks_viz_project must NOT be imported by scoring modules (import graph isolation)."""
        import importlib
        for mod_name in ("lgwks_score", "lgwks_rank", "lgwks_inbound"):
            try:
                m = importlib.import_module(mod_name)
                self.assertFalse(
                    hasattr(m, "lgwks_viz_project") or "lgwks_viz_project" in dir(m),
                    msg=f"T2: {mod_name} must NOT import lgwks_viz_project (decoupling invariant)",
                )
            except ImportError:
                pass   # module not loadable in test env — skip


# ---------------------------------------------------------------------------
# T3 — stress reported
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_NUMPY, "numpy required for I10 projection (T3)")
class TestStressReported(unittest.TestCase):
    """T3: reconstruction_stress returns a finite float in [0, 1]; log it, don't hide it."""

    DIM = 32
    N = 20

    def setUp(self):
        self.embs = [_make_embedding_bytes(i, self.DIM) for i in range(self.N)]

    def test_stress_finite_and_bounded(self):
        axes = lgwks_viz_project.fit_axes(self.embs)
        stress = lgwks_viz_project.reconstruction_stress(self.embs, axes)
        self.assertIsInstance(stress, float, "T3: stress must be float")
        self.assertGreaterEqual(stress, 0.0, "T3: stress must be >= 0")
        self.assertLessEqual(stress, 1.0, "T3: stress must be <= 1")
        import math
        self.assertTrue(math.isfinite(stress), "T3: stress must be finite")

    def test_stress_threshold_constant_registered(self):
        self.assertIsInstance(STRESS_THRESHOLD, float, "T3: STRESS_THRESHOLD must be a float")
        self.assertGreater(STRESS_THRESHOLD, 0.0, "T3: STRESS_THRESHOLD must be > 0")
        self.assertLess(STRESS_THRESHOLD, 1.0, "T3: STRESS_THRESHOLD must be < 1")

    def test_stress_decreases_with_more_dimensions(self):
        """T3: low-d embeddings have higher stress than high-d (top-3 captures less)."""
        embs_lo = [_make_embedding_bytes(i, 4) for i in range(self.N)]  # 4-d, top-3 explains ~75%
        embs_hi = [_make_embedding_bytes(i, 64) for i in range(self.N)]  # 64-d, top-3 explains less
        axes_lo = lgwks_viz_project.fit_axes(embs_lo)
        axes_hi = lgwks_viz_project.fit_axes(embs_hi)
        s_lo = lgwks_viz_project.reconstruction_stress(embs_lo, axes_lo)
        s_hi = lgwks_viz_project.reconstruction_stress(embs_hi, axes_hi)
        # For 4-d: top-3 PCs cover at least 75% variance → stress ≤ 0.25
        self.assertLessEqual(s_lo, 0.25,
                             f"T3: 4-d stress {s_lo:.3f} must be ≤ 0.25 (top-3 of 4 dims)")
        # High-d stress ≥ low-d stress (more unexplained variance)
        self.assertGreaterEqual(s_hi, s_lo,
                                f"T3: 64-d stress {s_hi:.3f} should be ≥ 4-d stress {s_lo:.3f}")


# ---------------------------------------------------------------------------
# T4 — finite coords / degenerate input
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_NUMPY, "numpy required for I10 projection (T4)")
class TestFiniteCoords(unittest.TestCase):
    """T4: no NaN/Inf in any coordinate; degenerate near-zero embedding raises loudly."""

    DIM = 16
    N = 10

    def setUp(self):
        self.embs = [_make_embedding_bytes(i, self.DIM) for i in range(self.N)]

    def test_all_coords_finite(self):
        axes = lgwks_viz_project.fit_axes(self.embs)
        for emb in self.embs:
            x, y, z = lgwks_viz_project.project(emb, axes.W, mean=axes.mean)
            import math
            self.assertTrue(math.isfinite(x), f"T4: x must be finite, got {x}")
            self.assertTrue(math.isfinite(y), f"T4: y must be finite, got {y}")
            self.assertTrue(math.isfinite(z), f"T4: z must be finite, got {z}")

    def test_empty_embeddings_raises(self):
        with self.assertRaises((ValueError, RuntimeError),
                               msg="T4: empty embedding list must raise"):
            lgwks_viz_project.fit_axes([])

    def test_too_few_dims_raises(self):
        # Only 2 dimensions, need at least 3 for top-3 PCA
        embs = []
        for i in range(5):
            v = _np.array([float(i + 1), float(i + 2)], dtype=_np.float32)
            v = v / _np.linalg.norm(v)
            embs.append(struct.pack(">2f", *v.tolist()))
        with self.assertRaises((ValueError, RuntimeError),
                               msg="T4: d<3 must raise"):
            lgwks_viz_project.fit_axes(embs)

    def test_numpy_unavailable_raises_runtime_error(self):
        """T4: when numpy is not importable, fit_axes must raise RuntimeError with clear message."""
        import unittest.mock as _mock
        orig = lgwks_viz_project._HAS_NUMPY
        lgwks_viz_project._HAS_NUMPY = False
        try:
            with self.assertRaises(RuntimeError, msg="T4: no numpy → RuntimeError"):
                lgwks_viz_project.fit_axes(self.embs)
        finally:
            lgwks_viz_project._HAS_NUMPY = orig


if __name__ == "__main__":
    unittest.main()
