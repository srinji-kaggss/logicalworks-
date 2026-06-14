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
"""

from __future__ import annotations

import math

__all__ = ["cosine"]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; 0.0 on shape/degenerate/non-finite input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    sim = dot / (na * nb)
    if not math.isfinite(sim):
        return 0.0
    return max(-1.0, min(1.0, sim))
