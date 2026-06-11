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
    W = top-3 right-singular vectors of Ê (SVD), sign-fixed, d × 3
    sign-fix: for each column of W, if largest-magnitude entry is negative → flip column
    y_i = Wᵀ êᵢ ∈ ℝ³   # the (x, y, z) coordinate per node

Decisions:
    D1: sign-fix is mandatory — SVD columns are sign-ambiguous; without it the same
        Ê yields different coords across runs (replay fails).
    D2: numpy.linalg.svd is the SVD backend.  If numpy is unavailable the module is
        importable but fit_axes() raises RuntimeError with a clear install message.
    D3: optional seeded UMAP fallback ONLY if PCA reconstruction stress exceeds the
        PRE-REGISTERED threshold STRESS_THRESHOLD; PCA is the default.
    D4: Coords are bounded/finite — NaN/Inf in any coordinate is a loud error, not
        silent garbage (no silent failure, INGESTION-PLAN §I10 acceptance).
"""

from __future__ import annotations

import math
import struct
from typing import Any

try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# ---------------------------------------------------------------------------
# Constants (pre-registered — D3)
# ---------------------------------------------------------------------------

# PCA reconstruction stress threshold above which seeded UMAP fallback is invoked.
# //why pre-registered: must be a documented constant, not a runtime fiddle (D3).
STRESS_THRESHOLD: float = 0.30   # fraction of variance unexplained by top-3 PCs
UMAP_SEED: int = 42              # seed for deterministic UMAP (if invoked)


# ---------------------------------------------------------------------------
# Core projection API
# ---------------------------------------------------------------------------

def fit_axes(embeddings: "list[bytes | Any]") -> "Any":
    """Compute sign-fixed top-3 PCA axes W (d × 3) from L2-normalised embeddings.

    embeddings: list of either packed float32 big-endian bytes (lgwks_vector.py
                format) or numpy arrays of floats.

    Returns W as a numpy array of shape (d, 3).
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
            floats = struct.unpack(f">{d}f", e)
            rows.append(floats)
        else:
            rows.append(e)

    E = _np.array(rows, dtype=_np.float32)   # n × d
    if E.ndim != 2 or E.shape[1] < 3:
        raise ValueError(f"embedding matrix must be n × d with d >= 3, got shape {E.shape}")

    # SVD: E = U S Vt  →  right singular vectors are rows of Vt (= columns of V).
    # We want the top-3 columns of V (= rows of Vt[:3]).
    _, _, Vt = _np.linalg.svd(E, full_matrices=False)
    W = Vt[:3].T   # d × 3 (top-3 right singular vectors as columns)

    # Sign-fix (D1): for each column, if the entry of largest magnitude is negative → flip.
    for j in range(W.shape[1]):
        col = W[:, j]
        idx = int(_np.argmax(_np.abs(col)))
        if col[idx] < 0:
            W[:, j] = -col

    return W   # d × 3, sign-fixed, replayable


def project(embedding: "bytes | Any", W: "Any") -> tuple[float, float, float]:
    """Project one L2-normalised embedding to 3-D via y = Wᵀ ê.

    embedding: packed float32 big-endian bytes or numpy array.
    W: d × 3 sign-fixed axes from fit_axes().
    Returns (x, y, z) tuple of Python floats.
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy. Install: pip install numpy."
        )
    if isinstance(embedding, bytes):
        d = len(embedding) // 4
        floats = struct.unpack(f">{d}f", embedding)
        e = _np.array(floats, dtype=_np.float32)
    else:
        e = _np.asarray(embedding, dtype=_np.float32)

    y = W.T @ e   # 3-vector
    _check_finite(y)
    return float(y[0]), float(y[1]), float(y[2])


def project_all(records: "list[Any]", W: "Any | None" = None) -> dict[str, tuple[float, float, float]]:
    """Project all VectorRecord-like objects to (x, y, z) dicts keyed by cid.

    records: list with .cid (str) and .embedding (bytes) attributes.
    W: pre-computed axes from fit_axes(); if None, fit_axes() is called on the records.

    Returns {cid: (x, y, z)}.
    """
    if not _HAS_NUMPY:
        raise RuntimeError(
            "lgwks_viz_project requires numpy. Install: pip install numpy."
        )
    if not records:
        return {}

    if W is None:
        W = fit_axes([r.embedding for r in records])

    out: dict[str, tuple[float, float, float]] = {}
    for r in records:
        out[r.cid] = project(r.embedding, W)
    return out


def reconstruction_stress(embeddings: "list[bytes | Any]", W: "Any") -> float:
    """Fraction of total variance NOT explained by the top-3 PCA components.

    Returns a float in [0, 1]:  0 = perfect reconstruction, 1 = pure noise.
    If stress > STRESS_THRESHOLD the seeded-UMAP fallback is warranted (D3).
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

    E = _np.array(rows, dtype=_np.float32)   # n × d
    # Reconstruction: Ê_hat = (E @ W) @ Wᵀ
    E_hat = (E @ W) @ W.T
    residual = float(_np.sum((E - E_hat) ** 2))
    total = float(_np.sum(E ** 2))
    if total < 1e-12:
        return 0.0
    return residual / total


def _check_finite(y: "Any") -> None:
    """Raise loudly if any coordinate is NaN or Inf (no silent garbage — D4)."""
    import math as _math
    for v in y.flat:
        if not _math.isfinite(float(v)):
            raise ValueError(
                f"non-finite coordinate produced by viz projection: {y!r}. "
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
        "formula": "y_i = Wᵀ êᵢ ∈ ℝ³  (PCA, top-3 sign-fixed singular vectors)",
        "sign_fix": "largest-magnitude-positive rule — kills SVD sign ambiguity → replayable",
        "stress_threshold": STRESS_THRESHOLD,
        "umap_seed": UMAP_SEED,
        "numpy_available": _HAS_NUMPY,
        "decoupling_invariant": (
            "scoring/ranking output is bit-identical with this module present or absent "
            "(INGESTION-LAYER §7.5) — coords never feed back"
        ),
        "isolation": "separate module from lgwks_graph_viz.py — import graph cannot pull "
                     "projection into a scoring path",
    }, indent=2))
    return 0
