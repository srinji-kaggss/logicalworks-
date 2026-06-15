"""lgwks_oriented — the basement seam for the Structural Inference Framework (#172).

HYPOTHESIS PHASE. This module fixes the FINAL shape of the *oriented inference*
objective so that the math proof (#173), variable-birth `Phi_V` (#174), capsule
encoding (#175), and the Aetherius harness (#180) extend it by filling terms,
never by reshaping the interface.

Terminology is provisional human-slop: `Pi`/"intent", C/G/P, "oriented" are
labels. The load-bearing contract is the math:

    L(K, D, Pi) = description_length(K)        # Occam   — compress the model
                + prediction_error(K, D)        # accuracy — fit what is
                + intent_divergence(K, Pi)       # teleology — distance from what's wanted

Every term is in BITS, so L is one honest code length. Two NESTED LIMITS make
Bayes the reference, not the foundation:

    flat Pi              -> intent_divergence == 0  -> the #172 structural limit
    flat Pi + frozen K   -> also no structure moves -> Bayes (belief update on fixed H)

Calculator test (feedback_calculator_test): every returned value is
reconstructable by hand from the inputs with a calculator and zero network.
No magic constants, no tuned weights, no AI in this layer. The weights on the
three terms are fixed at 1.0 BY CONSTRUCTION — all terms share the unit "bits",
so a weight other than 1 would be a magic constant. `Phi_V`'s ontology cost
`tau` (#174) is therefore the *encoding length in bits* of a proposed vertex,
not a free parameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional

SCHEMA = "lgwks.oriented.objective.v1"

# The three terms share the unit "bits"; their weights are 1 by construction.
# Exposed as a named constant only so the contract is greppable — it is NOT a
# tunable knob (changing it would reintroduce a magic constant; see module doc).
_UNIT_WEIGHT = 1.0


def _normalize(dist: Mapping[str, float]) -> dict[str, float]:
    """Project raw non-negative weights onto a probability distribution.

    Reconstructable by hand: each weight divided by the total. Empty/zero-mass
    input yields an empty distribution (caller decides what that means)."""
    total = sum(v for v in dist.values() if v > 0.0)
    if total <= 0.0:
        return {}
    return {k: v / total for k, v in dist.items() if v > 0.0}


def prediction_error_bits(predicted: Mapping[str, float], observed: str) -> float:
    """Surprisal of the observed outcome under the model's predictive distribution.

        prediction_error = -log2 P(observed)        [bits]

    This is the per-observation code length the model pays for what actually
    happened — the bridge between "PredictionError(K,D)" in the epic and a
    calculator-checkable number. An outcome the model assigned zero (or never
    listed) costs +inf bits: the model is infinitely surprised, which is the
    honest signal that its support is wrong (a `Phi` move is due)."""
    p = _normalize(predicted).get(observed, 0.0)
    if p <= 0.0:
        return math.inf
    return -math.log2(p)


def intent_divergence_bits(
    achievable: Mapping[str, float],
    preferred: Optional[Mapping[str, float]],
) -> float:
    """Teleology term: how far the achievable outcomes sit from what's wanted.

        intent_divergence = D_KL(preferred || achievable)      [bits]

    NESTED LIMIT: `preferred is None` (flat / no intent) returns 0.0 — no
    preference means no teleological pressure, which collapses the objective to
    the #172 structural limit. With a preference, it is the standard KL in bits:
    the extra bits to encode preferred-reality using the achievable model. A
    preferred outcome the model cannot achieve (achievable prob 0) costs +inf —
    the honest signal that intent demands structure the model lacks."""
    if preferred is None:
        return 0.0
    p = _normalize(preferred)
    q = _normalize(achievable)
    if not p:
        return 0.0
    total = 0.0
    for outcome, p_x in p.items():
        q_x = q.get(outcome, 0.0)
        if q_x <= 0.0:
            return math.inf
        total += p_x * math.log2(p_x / q_x)
    # KL is >= 0 for proper distributions; clamp -0.0/rounding noise to 0.
    return max(0.0, total)


@dataclass(frozen=True)
class OrientedObjective:
    """One evaluation of L(K, D, Pi). All fields in bits; total = sum of terms.

    `mode` names which nested limit this evaluation sits in, so a reader can see
    at a glance whether intent and/or structure were active:
        "bayes"      — flat intent AND frozen structure (belief update only)
        "structural" — flat intent, structure free to move (#172 limit)
        "oriented"   — intent active (the full objective)
    """

    schema: str
    description_length: float
    prediction_error: float
    intent_divergence: float
    total: float
    mode: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "description_length_bits": self.description_length,
            "prediction_error_bits": self.prediction_error,
            "intent_divergence_bits": self.intent_divergence,
            "total_bits": self.total,
            "mode": self.mode,
        }


def oriented_loss(
    description_length_bits: float,
    prediction_error_bits: float,
    intent_divergence_bits: float = 0.0,
    *,
    structure_frozen: bool = True,
) -> OrientedObjective:
    """Assemble the three-term objective and classify its nested limit.

    Default arguments (`intent_divergence=0`, `structure_frozen=True`) place the
    evaluation at the **Bayes limit**, so any caller that hasn't yet supplied
    intent or enabled structure moves gets today's behavior unchanged. Supplying
    a non-zero intent divergence promotes it to "oriented"; freeing structure
    with flat intent promotes it to "structural". This is the seam #173/#174/#180
    fill — no reshape required."""
    # intent_divergence is exactly 0.0 only at the flat-intent limit (KL of an
    # absent preference); any non-zero (or +inf) value means intent was applied.
    intent_active = intent_divergence_bits != 0.0
    if intent_active:
        mode = "oriented"
    elif structure_frozen:
        mode = "bayes"
    else:
        mode = "structural"
    total = (
        _UNIT_WEIGHT * description_length_bits
        + _UNIT_WEIGHT * prediction_error_bits
        + _UNIT_WEIGHT * intent_divergence_bits
    )
    return OrientedObjective(
        schema=SCHEMA,
        description_length=description_length_bits,
        prediction_error=prediction_error_bits,
        intent_divergence=intent_divergence_bits,
        total=total,
        mode=mode,
    )


def vertex_birth_justified(
    loss_before_bits: float,
    loss_after_bits: float,
    tau_bits: float,
) -> bool:
    """`Phi_V` gate (#174): a new vertex is justified iff it pays for itself.

        L(K') < L(K) - tau

    `tau_bits` is the *encoding length of the proposed vertex and its edges* in
    bits — derived, never tuned (see module doc). Returns True only when the
    compression gain strictly exceeds the cost of carrying the new ontology. The
    causal-identifiability guard (abstain-to-Hole) lives in #174's `f(R,K)`, not
    here: this is the necessary economic condition, not the sufficient one."""
    if tau_bits < 0.0:
        raise ValueError("tau_bits (ontology encoding cost) must be non-negative")
    return loss_after_bits < (loss_before_bits - tau_bits)
