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

import math

__all__ = ["cosine", "dot", "l2_norm", "l2_normalize", "ZeroVectorError"]


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
