"""
lgwks_apple — Apple-local embedding provider seam.

Wraps the Apple MLX / Core ML inference path for text embeddings.  The module
is intentionally thin: it probes availability, exposes a single embed_one()
entry point, and records enough metadata for the substrate manifest/vector-space
contract (PR #46).

Availability contract
─────────────────────
- On non-Apple hardware, or when the mlx_lm / mlx-embeddings packages are absent,
  is_available() returns False and embed_one() returns None.
- Explicit apple-local callers should fail closed when embed_one() returns None; generic
  auto providers may choose a different provider before falling back to deterministic.
- No exception is raised for missing runtime — fail-silent at the provider level,
  fail-closed at the substrate level (manifested as a deterministic skip).

Provider token
──────────────
The resolved provider label written to manifest / vectors.jsonl is:
    "apple-local:<model_id>"
e.g. "apple-local:mlx-community/all-MiniLM-L6-v2-4bit"

This follows the same "provider:model" convention as "ollama:<model>".

Environment controls
────────────────────
LGWKS_APPLE_MODEL   — override default model id
LGWKS_APPLE_DIMS    — override output dimension slice (default: 384)
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lgwks_model_port import Embedder  # contract only — no runtime dep on the thin leaf

# Default model: small, widely tested on Apple Silicon.
DEFAULT_MODEL: str = os.environ.get(
    "LGWKS_APPLE_MODEL",
    "mlx-community/all-MiniLM-L6-v2-4bit",
)
DEFAULT_DIMS: int = int(os.environ.get("LGWKS_APPLE_DIMS", "384"))

# Canonical provider-label prefix written to manifests and vectors.
PROVIDER_PREFIX: str = "apple-local"


@lru_cache(maxsize=1)
def is_available() -> bool:
    """Return True iff the Apple MLX embedding runtime is usable right now.

    Checks in order:
    1. Platform must be Darwin (macOS).
    2. mlx package must be importable.
    3. mlx_lm or mlx_embeddings package must be importable (either gives us
       sentence-embedding capability).
    """
    if sys.platform != "darwin":
        return False
    try:
        import mlx.core  # noqa: F401
    except ImportError:
        return False
    try:
        import mlx_lm  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import mlx_embeddings  # noqa: F401
        return True
    except ImportError:
        pass
    return False


@lru_cache(maxsize=1)
def _load_model(model_id: str) -> Any | None:
    """Load and cache the MLX embedding model.  Returns None when unavailable."""
    if not is_available():
        return None
    try:
        # Prefer mlx_embeddings (purpose-built for embeddings).
        import mlx_embeddings
        return mlx_embeddings.load(model_id)
    except (ImportError, Exception):
        pass
    try:
        # Fallback: mlx_lm generic loader (works for instruction-tuned models
        # that also expose hidden states we can mean-pool).
        import mlx_lm
        return mlx_lm.load(model_id)
    except (ImportError, Exception):
        return None


def embed_one(
    text: str,
    *,
    model_id: str = DEFAULT_MODEL,
    dims: int = DEFAULT_DIMS,
) -> list[float] | None:
    """Compute a text embedding using the Apple-local MLX runtime.

    Returns a list[float] of length `dims`, or None when the runtime is
    unavailable or inference fails.  Never raises — returns None on any error.
    """
    if not is_available():
        return None
    model_bundle = _load_model(model_id)
    if model_bundle is None:
        return None
    try:
        # mlx_embeddings API: encode returns a numpy/mlx array.
        if hasattr(model_bundle, "encode"):
            arr = model_bundle.encode([text])
            vec = list(float(x) for x in arr[0])
        elif hasattr(model_bundle, "embeddings"):
            arr = model_bundle.embeddings([text])
            vec = list(float(x) for x in arr[0])
        else:
            # Fallback: try calling the bundle directly (some mlx_lm wrappers).
            result = model_bundle(text)
            if hasattr(result, "tolist"):
                vec = result.tolist()
            else:
                vec = list(float(x) for x in result)
    except Exception:
        return None
    # Slice or pad to requested dims.
    if len(vec) >= dims:
        raw = vec[:dims]
    else:
        raw = vec + [0.0] * (dims - len(vec))
    # L2-normalise so cosine similarity reduces to a dot product.
    norm = sum(x * x for x in raw) ** 0.5
    if norm < 1e-10:
        return raw
    return [x / norm for x in raw]


if TYPE_CHECKING:
    _conforms_embedder: Embedder = embed_one  # static conformance to the shared contract (#152)


def provider_label(model_id: str = DEFAULT_MODEL) -> str:
    """Return the canonical provider label for manifest recording."""
    return f"{PROVIDER_PREFIX}:{model_id}"
