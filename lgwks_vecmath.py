"""lgwks_vecmath — the single source of truth for vector similarity math.

cosine(a, b) is THE cosine similarity over two equal-length float lists. It used to
exist as four subtly-different `_cosine` copies (engine, intent_classifier, urlrisk)
plus one that wasn't cosine at all (pipeline delegated to a bare dot product). The
divergence mattered: intent_classifier's own comment warns that Eye vectors are NOT
unit-normalized, so a dot product conflates magnitude with similarity — yet pipeline
used exactly that under the name `_cosine`. One definition removes that trap.

Contract (calculator-derivable — the vectors are the frozen sensor layer, the math here
is the deterministic spine, see feedback_math_not_bert_scorer):
  - normalize both vectors (correct for non-unit Eye vectors AND unit feature-hashes),
  - return 0.0 on shape mismatch, empty input, a zero-magnitude vector, or non-finite result,
  - clamp the result to [-1, 1] (kills float-rounding overshoot like 1.0000000002).

This is the robust superset of the prior copies: identical output on well-formed vectors,
strictly safer on the edges.

The same drift then re-grew one level down: L2-normalisation was re-implemented in at
least five modules with SLIGHTLY DIFFERENT zero-handling (rank returned the vector
unchanged, vector/embed_port raised, run divided by 1.0). "Slightly different" is the
bug — the edge behaviour silently diverges. So the L2 primitives live here too, with
ONE explicit zero policy callers select, never re-derive: dot / l2_norm / l2_normalize.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable

__all__ = ["cosine", "dot", "l2_norm", "l2_normalize", "hash_bucket", "hash_embed", "ZeroVectorError"]


class ZeroVectorError(ValueError):
    """A zero-magnitude vector was passed where normalisation requires direction."""


def dot(a: list[float], b: list[float]) -> float:
    """Raw dot product; 0.0 on shape mismatch or empty input.

    For ALREADY-normalised vectors dot == cosine — but callers that aren't certain
    of normalisation must use cosine(), not this (the exact trap that produced the
    jarvis/pipeline bugs)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def l2_norm(v: list[float]) -> float:
    """Euclidean (L2) norm of v. 0.0 for empty/zero vectors."""
    return math.sqrt(sum(x * x for x in v))


def l2_normalize(v: list[float], *, on_zero: str = "keep") -> list[float]:
    """Scale v to unit L2 length. ONE place, ONE explicit zero policy.

    on_zero (what to do when ||v|| < 1e-12, i.e. no direction to preserve):
      "keep"  — return v unchanged (default; the never-block / audit-safe choice)
      "raise" — raise ZeroVectorError (the strict choice for typed vector records)
    """
    n = l2_norm(v)
    if n < 1e-12:
        if on_zero == "raise":
            raise ZeroVectorError("cannot L2-normalize a zero-magnitude vector")
        return v
    inv = 1.0 / n
    return [x * inv for x in v]


def hash_bucket(feat: str, dims: int, *, encode_errors: str = "strict") -> tuple[int, float]:
    """The signed-bucket ATOM: one feature string → (bucket index, ±1.0 sign).

    ``d = blake2b(feat, digest_size=8)``; bucket = first 4 bytes mod ``dims``;
    sign = parity of byte 4. This is the single byte-level definition of the
    feature-hash mechanism — ``hash_embed`` and the structured composite embedder
    in ``lgwks_concept`` both go through it, so the bucket/sign derivation cannot
    drift in one place without the other (#223 family 2). Fully deterministic.
    """
    d = hashlib.blake2b(feat.encode("utf-8", errors=encode_errors), digest_size=8).digest()
    return int.from_bytes(d[:4], "big") % dims, (1.0 if d[4] % 2 == 0 else -1.0)


def hash_embed(
    features: Iterable[str],
    dims: int,
    *,
    weighted: bool = False,
    encode_errors: str = "strict",
) -> list[float]:
    """Deterministic feature-hash embedding — the ONE shared MECHANISM (#223 family 2).

    The signed-bucket blake2b mechanism was copy-pasted across 5 n-gram embedders
    (run/jarvis/project_artifacts/embed/memory) plus the bucket/sign ATOM in the
    structured composite embedder ``lgwks_concept.concept_vector``. Each drifted
    independently and one sibling once rotted to ``np.random`` (#29), turning gating
    confidence into noise. This is the single tested mechanism; callers keep their
    OWN feature extraction (the part that legitimately differs) and pass the
    resulting feature strings here. ``concept`` uses ``hash_bucket`` directly because
    its per-token position/salt weighting does not fit this uniform-feature shape.

    For every ``feat``: ``d = blake2b(feat, digest_size=8)``; bucket = first 4 bytes
    mod ``dims``; sign = parity of byte 4; accumulate ``sign * weight``; then L2-
    normalise and round to 6 dp. Fully deterministic — no RNG, ever.

    weighted       : N-gram weighting (1.0 / 1.5 / 2.0 by space-count) — only the
                     lexical-fallback embedder in ``lgwks_run`` uses it; others = sign only.
    encode_errors  : utf-8 error policy. "strict" (default) matches most callers;
                     jarvis passes "ignore" to mirror its prior ``errors="ignore"``.

    NOT a semantic embedder — it is the deterministic lexical fallback. The real Eye
    (Qwen) is reached via ``lgwks_run.embed``; this never gates tool authority.
    """
    vec = [0.0] * dims
    for feat in features:
        bucket, sign = hash_bucket(feat, dims, encode_errors=encode_errors)
        weight = 1.0
        if weighted and " " in feat:
            weight = 1.5 if feat.count(" ") == 1 else 2.0
        vec[bucket] += sign * weight
    norm = l2_norm(vec) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; 0.0 on shape/degenerate/non-finite input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    sim = d / (na * nb)
    if not math.isfinite(sim):
        return 0.0
    return max(-1.0, min(1.0, sim))
