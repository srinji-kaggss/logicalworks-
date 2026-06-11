"""lgwks_viz_project — deterministic 3-D viz projection, decoupled from semantic space (I10).

Viz-only artifact. NEVER feeds back into scoring/retrieval (INGESTION-LAYER §7.5).
No model call. Pure function of the embedding matrix Ê.

Authority: spec/second-harness/INGESTION-PLAN.md §I10
           spec/second-harness/INGESTION-LAYER.md §7.5 (decoupling law)
Issue:     I10

WARNING: this module must NEVER be imported into any scoring/ranking module.
The import graph isolation (separate file from lgwks_graph_viz.py) IS the
architectural decoupling — do not collapse it (INGESTION-PLAN §I10 scope fence).

Formula (INGESTION-PLAN §I10):
    Ê = n × d matrix of L2-normalised embeddings
    Ê_c = Ê − mean(Ê)              # mean-centred (canonical PCA requirement)
    W = top-3 right-singular vectors of Ê_c (via SVD), sign-fixed, d × 3
    sign-fix: for each column of W, if largest-magnitude entry is negative → flip column
    y_i = Wᵀ (êᵢ − mean) ∈ ℝ³    # (x, y, z) coordinate per node

Decisions:
    D1: sign-fix is mandatory — SVD columns are sign-ambiguous; without it the same
        Ê yields different coords across runs (replay fails).
    D2: centering is mandatory — SVD on uncentred data computes variance from origin,
        not variance from the data centroid. On hypersphere embeddings the first
        singular vector would point at the cluster mean rather than spanning the
        spread. True PCA = centre then SVD.
    D3: fit_axes() returns a ProjectionAxes(W, mean) named tuple; project() accepts
        mean for consistent centring at query time.
    D4: numpy.linalg.svd is the SVD backend. If numpy is unavailable the module is
        importable but fit_axes() raises RuntimeError with a clear install message.
    D5: optional seeded UMAP fallback ONLY if PCA reconstruction stress exceeds the
        PRE-REGISTERED threshold STRESS_THRESHOLD; PCA is the default.
    D6: Coords are bounded/finite — NaN/Inf is a loud error, not silent garbage.
"""

from __future__ import annotations

import math
import struct
from typing import Any, NamedTuple

try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# ---------------------------------------------------------------------------
# Constants (pre-registered — D5)
# ---------------------------------------------------------------------------

# PCA reconstruction stress threshold above which seeded UMAP fallback is invoked.
# //why pre-registered: must be a documented constant, not a runtime fiddle.
STRESS_THRESHOLD: float = 0.30   # fraction of variance unexplained by top-3 PCs
UMAP_SEED: int = 42              # seed for deterministic UMAP (if invoked)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class ProjectionAxes(NamedTuple):
    """Result of fit_axes — the sign-fixed projection basis and centring vector.

    W:    d × 3 numpy array — top-3 right singular vectors of the centred matrix,
          sign-fixed so the largest-magnitude entry in each column is positive.
    mean: d numpy array — per-dimension mean subtracted before projecting.
          Required to project new embeddings consistently (D3).
    """
    W: "Any"     # numpy ndarray, shape (d, 3)
    mean: "Any"  # numpy ndarray, shape (d,)


# ---------------------------------------------------------------------------
# Core projection API
# ---------------------------------------------------------------------------

def fit_axes(embeddings: "list[bytes | Any]") -> ProjectionAxes:
    """Compute sign-fixed top-3 PCA axes from L2-normalised embeddings.

    embeddings: list of packed float32 big-endian bytes (lgwks_vector.py format)
                or numpy float arrays. All must have the same dimension d.

    Returns ProjectionAxes(W, mean) where W is (d, 3) and mean is (d,).
    Pass both to project() for consistent centring (D3).
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy for I10 projection. "
            "Install it: pip install numpy (or add numpy to requirements.txt)."
        )
    if not embeddings:
        raise ValueError("fit_axes requires at least one embedding")

    rows = []
    for e in embeddings:
        if isinstance(e, bytes):
            d = len(e) // 4
            rows.append(struct.unpack(f">{d}f", e))
        else:
            rows.append(e)

    E = _np.array(rows, dtype=_np.float32)   # n × d
    if E.ndim != 2 or E.shape[1] < 3:
        raise ValueError(f"embedding matrix must be n × d with d >= 3, got shape {E.shape}")

    # Mean-centre before SVD (D2). SVD on raw E finds directions of maximum
    # total distance from origin; SVD on E - mean finds principal components.
    E_mean = E.mean(axis=0)                  # shape (d,)
    E_c = E - E_mean                         # centred matrix, shape (n, d)

    # SVD of centred matrix: E_c = U S Vt → right singular vectors are rows of Vt.
    _, _, Vt = _np.linalg.svd(E_c, full_matrices=False)
    W = Vt[:3].T   # d × 3 (top-3 right singular vectors as columns)

    # Sign-fix (D1): for each column, if the entry of largest magnitude is negative → flip.
    for j in range(W.shape[1]):
        col = W[:, j]
        idx = int(_np.argmax(_np.abs(col)))
        if col[idx] < 0:
            W[:, j] = -col

    return ProjectionAxes(W=W, mean=E_mean)


def project(
    embedding: "bytes | Any",
    W: "Any",
    *,
    mean: "Any | None" = None,
) -> tuple[float, float, float]:
    """Project one embedding to 3-D: y = Wᵀ (ê − mean).

    embedding: packed float32 big-endian bytes or numpy array.
    W:    d × 3 sign-fixed axes from fit_axes().W.
    mean: d centring vector from fit_axes().mean. Required for correct results
          when W was computed on centred data (i.e., always).
    Returns (x, y, z) as Python floats.
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy. Install: pip install numpy."
        )
    if isinstance(embedding, bytes):
        d = len(embedding) // 4
        e = _np.array(struct.unpack(f">{d}f", embedding), dtype=_np.float32)
    else:
        e = _np.asarray(embedding, dtype=_np.float32)

    if mean is not None:
        e = e - mean   # centre the query vector consistently with fit_axes (D3)

    y = W.T @ e   # shape (3,)
    _check_finite(y)
    return float(y[0]), float(y[1]), float(y[2])


def project_all(
    records: "list[Any]",
    axes: "ProjectionAxes | None" = None,
) -> dict[str, tuple[float, float, float]]:
    """Project all VectorRecord-like objects to (x, y, z) keyed by cid.

    records: objects with .cid (str) and .embedding (bytes) attributes.
    axes:    pre-computed ProjectionAxes from fit_axes(); computed if None.

    Returns {cid: (x, y, z)}.
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy. Install: pip install numpy."
        )
    if not records:
        return {}

    if axes is None:
        axes = fit_axes([r.embedding for r in records])

    out: dict[str, tuple[float, float, float]] = {}
    for r in records:
        out[r.cid] = project(r.embedding, axes.W, mean=axes.mean)
    return out


def reconstruction_stress(
    embeddings: "list[bytes | Any]",
    axes: "ProjectionAxes",
) -> float:
    """Fraction of total variance NOT explained by the top-3 PCA components.

    Uses centred data to measure variance (not distance from origin), matching
    the definition of PCA explained-variance ratio (D5, D2).

    Returns a float in [0, 1]: 0 = perfect reconstruction, 1 = pure noise.
    If stress > STRESS_THRESHOLD the seeded-UMAP fallback is warranted.
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy. Install: pip install numpy."
        )
    rows = []
    for e in embeddings:
        if isinstance(e, bytes):
            d = len(e) // 4
            rows.append(struct.unpack(f">{d}f", e))
        else:
            rows.append(e)

    E = _np.array(rows, dtype=_np.float32)       # n × d
    E_c = E - axes.mean                           # centre using the fitted mean (D3)
    E_hat = (E_c @ axes.W) @ axes.W.T            # reconstruction from top-3 PCs
    residual = float(_np.sum((E_c - E_hat) ** 2))
    total_var = float(_np.sum(E_c ** 2))          # total variance (centred)
    if total_var < 1e-12:
        return 0.0
    return residual / total_var


def _check_finite(y: "Any") -> None:
    """Raise loudly if any coordinate is NaN or Inf (D6 — no silent garbage)."""
    for v in y.flat:
        if not math.isfinite(float(v)):
            raise ValueError(
                f"non-finite coordinate from viz projection: {y!r}. "
                "This indicates a degenerate (near-zero) embedding — investigate the source."
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("viz-project", help="deterministic 3-D viz projection (I10)")
    sp = p.add_subparsers(dest="viz_project_cmd", required=True)

    info_p = sp.add_parser("info", help="show projection constants and decoupling guarantee")
    info_p.set_defaults(func=_cmd_info)


def _cmd_info(args) -> int:
    import json as _json

    print(_json.dumps({
        "formula": "y_i = Wᵀ (êᵢ − mean) ∈ ℝ³  (mean-centred PCA, top-3 sign-fixed singular vectors)",
        "centering": "E − mean(E) applied before SVD — canonical PCA, not truncated SVD from origin",
        "sign_fix": "largest-magnitude-positive rule per column — kills SVD sign ambiguity → replayable",
        "stress_threshold": STRESS_THRESHOLD,
        "umap_seed": UMAP_SEED,
        "numpy_available": _HAS_NUMPY,
        "return_type": "ProjectionAxes(W, mean) — mean required for consistent projection of new vectors",
        "decoupling_invariant": (
            "scoring/ranking output is bit-identical with this module present or absent "
            "(INGESTION-LAYER §7.5) — coords never feed back"
        ),
        "isolation": "separate module from lgwks_graph_viz.py — import graph cannot pull "
                     "projection into a scoring path",
    }, indent=2))
    return 0
