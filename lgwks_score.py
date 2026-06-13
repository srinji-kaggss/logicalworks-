"""lgwks_score — deterministic schema scoring: RESCAL order-3 · R_k · MDL (I5).

No AI, no learning in path (INGESTION-LAYER §0, INV-3).
Same schema file + same instance → byte-identical operators, cid, scores across runs/machines.
Batch/offline only — not hot-path.

Authority: spec/second-harness/INGESTION-LAYER.md §4.2/§4.4/§4.5
Schema:    lgwks.score.record.v1
Relations: lgwks.schema.relations.v2  (I5.1: directional antisymmetric R_k activated)
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Schema identifiers (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.score.record.v1"
RELATIONS_SCHEMA = "lgwks.schema.relations.v2"   # v2 (I5.1): directional antisymmetric operators active

# ---------------------------------------------------------------------------
# D0 — relation schema (the pure-function source of R_k replayability)
# Vocab seeded from eval corpora: logicalworks-_graph + logic-os-kernel_graph.
# All eight declared directed for v1 (DECISION §1).
# dim_mask = None → default all-ones (DECISION §4 — defer MRL per-relation slicing).
# ---------------------------------------------------------------------------

RELATIONS: dict[str, dict[str, Any]] = {
    "calls":         {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "contains":      {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "method":        {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "inherits":      {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "uses":          {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "rationale_for": {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "imports_from":  {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "case_of":       {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "image":         {"direction": "directed", "arg_typing": None, "dim_mask": None},
    "video":         {"direction": "directed", "arg_typing": None, "dim_mask": None},
}

# ---------------------------------------------------------------------------
# D1 — factored relation operators  R_k = P_k · diag(d_k)
# Stored as O(d) per relation — R_k is NEVER materialized as a dense matrix.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactoredRelation:
    """R_k = P_k·diag(d_k) + N_k, stored O(d).

    perm=None    → identity P_k (default)
    signs=None   → all +1 (default)
    mask=None    → all-ones d_k (default, DECISION §4)
    antisym=None → no antisymmetric term, N_k = 0 (symmetric relation)

    antisym is a tuple of (a, b, c) generators meaning N_k[a,b] += c and N_k[b,a] -= c
    (antisymmetric by construction). It supplies relation DIRECTION (I5.1): a non-zero N_k
    makes R_k ≠ R_kᵀ, so score(i,k,j) ≠ score(j,k,i), while the per-relation family is built
    so Σ_k N_k = 0 → (1/m)Σ_k R_k = I, keeping the §4.2 marginal-identity proof EXACT.
    """
    relation_id: str
    perm: Optional[tuple[int, ...]]    # P_k permutation index; None = identity
    signs: Optional[tuple[int, ...]]   # ±1 per dim (signed perm); None = all +1
    mask: Optional[tuple[bool, ...]]   # d_k bitset; None = all True
    direction: str                      # "directed" | "symmetric"
    antisym: Optional[tuple[tuple[int, int, float], ...]] = None  # N_k generators (I5.1)


def _invert_perm(perm: tuple[int, ...]) -> tuple[int, ...]:
    """Inverse permutation: inv[perm[i]] = i."""
    inv = [0] * len(perm)
    for i, p in enumerate(perm):
        inv[p] = i
    return tuple(inv)


# Antisymmetric magnitude for directional operators (I5.1). PRE-REGISTERED, not tuned.
# //why 1.0: the term is a structural direction signal, not a learned weight; on L2-normalized
# embeddings it is a small bounded perturbation of cosine, and any positive constant gives the
# same sign structure for score(i,k,j) − score(j,k,i). Kept at unity for replay clarity.
ANTISYM_C: float = 1.0


def build_operators(dim: int, *, relations: dict = RELATIONS) -> dict[str, FactoredRelation]:
    """Build one FactoredRelation per relation in the schema.

    P_k stays identity (perm/signs/mask=None). DIRECTION is supplied by an antisymmetric
    term N_k (I5.1): directed relations are paired in sorted order, each pair sharing one
    coordinate pair (a,b) with opposite sign (+c / −c), so Σ_k N_k = 0 and the §4.2 marginal
    proof holds EXACTLY while every directed relation scores asymmetrically. Symmetric
    relations get N_k = None (identity, R_k = R_kᵀ). Pure function of the schema → replayable.

    Requires an EVEN number of directed relations (each needs a sign-opposite partner to keep
    Σ N_k = 0); an odd count cannot be both fully-directional and exact-marginal → raise loudly.
    """
    if dim < 1:
        raise ValueError(f"dim must be ≥ 1, got {dim}")

    directed = sorted(r for r, p in relations.items() if p["direction"] == "directed")
    if directed and dim < 2:
        raise ValueError(f"directional operators need dim ≥ 2 (got {dim}); a 1-D space has no antisymmetry")
    if len(directed) % 2 != 0:
        raise ValueError(
            f"directional P_k requires an even number of directed relations for exact "
            f"marginal identity (Σ_k N_k = 0); got {len(directed)}: {directed}"
        )

    # Assign each consecutive sorted pair its own coordinate pair (cycled if dim is small).
    slots = dim // 2
    antisym_for: dict[str, tuple[tuple[int, int, float], ...]] = {}
    for pair_idx in range(len(directed) // 2):
        slot = pair_idx % slots
        a, b = 2 * slot, 2 * slot + 1
        first, second = directed[2 * pair_idx], directed[2 * pair_idx + 1]
        antisym_for[first] = ((a, b, +ANTISYM_C),)
        antisym_for[second] = ((a, b, -ANTISYM_C),)

    return {
        rel_id: FactoredRelation(
            relation_id=rel_id,
            perm=None,
            signs=None,
            mask=None,
            direction=props["direction"],
            antisym=antisym_for.get(rel_id),
        )
        for rel_id, props in relations.items()
    }


# ---------------------------------------------------------------------------
# D2 — cubic score
# ---------------------------------------------------------------------------


def score_triple(
    ei: list[float] | tuple[float, ...],
    rel: FactoredRelation,
    ej: list[float] | tuple[float, ...],
) -> float:
    """score(i,k,j) = (P_k^T êᵢ)ᵀ (d_k ⊙ êⱼ).

    Two O(d) ops + one dot. R_k never materialized.
    Both vectors must be L2-normalized (VectorRecord guarantees this).
    """
    d = len(ei)
    if len(ej) != d:
        raise ValueError(f"dimension mismatch: len(ei)={d}, len(ej)={len(ej)}")
    # Operator factors must match the embedding dim, else silent corruption / IndexError.
    if rel.perm is not None and len(rel.perm) != d:
        raise ValueError(f"perm length {len(rel.perm)} != dim {d} for relation {rel.relation_id!r}")
    if rel.signs is not None and len(rel.signs) != d:
        raise ValueError(f"signs length {len(rel.signs)} != dim {d} for relation {rel.relation_id!r}")
    if rel.mask is not None and len(rel.mask) != d:
        raise ValueError(f"mask length {len(rel.mask)} != dim {d} for relation {rel.relation_id!r}")
    if rel.antisym is not None:
        for a, b, _c in rel.antisym:
            if not (0 <= a < d and 0 <= b < d):
                raise ValueError(
                    f"antisym coords ({a},{b}) out of range for dim {d}, relation {rel.relation_id!r}"
                )

    # Compute P_k^T êᵢ
    if rel.perm is not None:
        inv_perm = _invert_perm(rel.perm)
        lhs: list[float] = [ei[inv_perm[j]] for j in range(d)]
    else:
        lhs = list(ei)

    if rel.signs is not None:
        lhs = [lhs[j] * rel.signs[j] for j in range(d)]

    # Compute d_k ⊙ êⱼ
    if rel.mask is not None:
        rhs: list[float] = [ej[j] if rel.mask[j] else 0.0 for j in range(d)]
    else:
        rhs = list(ej)

    score = sum(l * r for l, r in zip(lhs, rhs))

    # Antisymmetric direction term N_k (I5.1): êᵢᵀ N_k êⱼ = Σ c·(êᵢ[a]êⱼ[b] − êᵢ[b]êⱼ[a]).
    # This is what makes score(i,k,j) ≠ score(j,k,i) for directed relations; the family's
    # generators cancel in the marginal (Σ_k N_k = 0), so cosine is reproduced exactly.
    if rel.antisym is not None:
        for a, b, c in rel.antisym:
            score += c * (ei[a] * ej[b] - ei[b] * ej[a])

    return score


# ---------------------------------------------------------------------------
# D3 — MDL conformance + content hash
# Canonical CBOR: sorted keys, normalized types, s_ai excluded (side-channel).
# ---------------------------------------------------------------------------


def _normalize_value(v: Any) -> Any:
    """Normalize types so logically-equal facts canonicalize identically.

    Two extract models emitting the same fact must produce the same cid even when
    one serializes a number as int (1) and the other as float (1.0). Rule: every
    non-bool integer is coerced to float; structures are normalized recursively.
    bool is preserved (CBOR/JSON treat it distinctly). //why: §4.4 cross-model cid.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, dict):
        return {k: _normalize_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_normalize_value(x) for x in v]
    return v


def canonicalize(instance: dict[str, Any]) -> bytes:
    """Canonical CBOR form of a graph instance.

    Excludes s_ai (side-channel per INV-3). Normalizes numeric types recursively
    (int→float) so model-to-model int/float variance does not fork the cid. cbor2
    canonical=True fixes map-key ordering at every level. Deterministic: identical
    logical content → byte-identical output regardless of insertion order or numeric type.
    """
    import cbor2  # soft dep; imported here so module loads without it

    cleaned = {k: _normalize_value(v) for k, v in instance.items() if k != "s_ai"}
    return cbor2.dumps(cleaned, canonical=True)


def content_cid(instance: dict[str, Any]) -> str:
    """blake2b content-address of the canonical form (digest_size=32)."""
    return hashlib.blake2b(canonicalize(instance), digest_size=32).hexdigest()


def score_mdl(instance: dict[str, Any], dict_bytes: bytes) -> float:
    """MDL conformance: 1 − |zstd(c(I)|S_dict)| / |zstd(c(I))|.

    Returns score ∈ [0, 1]. Higher = instance better predicted by the schema dictionary.
    Requires: cbor2, zstandard.
    """
    import zstandard as zstd  # soft dep

    canonical = canonicalize(instance)
    if not canonical:
        return 0.0

    size_no_dict = len(zstd.ZstdCompressor(level=3).compress(canonical))
    if size_no_dict == 0:
        return 0.0

    compression_dict = zstd.ZstdCompressionDict(dict_bytes)
    size_with_dict = len(
        zstd.ZstdCompressor(level=3, dict_data=compression_dict).compress(canonical)
    )

    return max(0.0, min(1.0, 1.0 - size_with_dict / size_no_dict))


# ---------------------------------------------------------------------------
# Output contract: lgwks.score.record.v1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreRecord:
    """One scored triple. schema_id is always lgwks.score.record.v1."""
    triple: dict            # {i_cid: str, k: str, j_cid: str}
    score: float            # f32-precision RESCAL score
    score_mdl: float        # MDL conformance ∈ [0, 1]
    cid: str                # blake2b(canonical_form)
    schema_id: str          # "lgwks.score.record.v1"
    s_ai: Optional[float]   # AI self-score (side-channel; INV-3: never consumed here)


def score_instance(
    i_cid: str,
    ei: list[float],
    k: str,
    j_cid: str,
    ej: list[float],
    instance_meta: dict[str, Any],
    operators: dict[str, FactoredRelation],
    dict_bytes: bytes,
) -> ScoreRecord:
    """Compute a full ScoreRecord for one typed triple (i, k, j).

    instance_meta: extra fields from the graph edge (weight, confidence_score, etc.)
    s_ai in instance_meta is recorded in the output but excluded from cid/canonical form.
    """
    rel = operators.get(k)
    if rel is None:
        raise ValueError(f"unknown relation {k!r}; register it in RELATIONS first")

    raw = score_triple(ei, rel, ej)
    f32 = float(struct.unpack("f", struct.pack("f", raw))[0])

    full = {"i_cid": i_cid, "k": k, "j_cid": j_cid, **instance_meta}
    mdl = score_mdl(full, dict_bytes)
    cid = content_cid(full)

    return ScoreRecord(
        triple={"i_cid": i_cid, "k": k, "j_cid": j_cid},
        score=f32,
        score_mdl=mdl,
        cid=cid,
        schema_id=SCHEMA,
        s_ai=instance_meta.get("s_ai"),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_parser(sub) -> None:
    p = sub.add_parser("score", help="deterministic schema scoring (I5: RESCAL+MDL)")
    sp = p.add_subparsers(dest="score_cmd", required=True)

    ls = sp.add_parser("relations", help="list registered relations (D0)")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=_cmd_relations)


def _cmd_relations(args) -> int:
    import json as _json
    import sys as _sys

    items = [
        {"relation": k, "direction": v["direction"]}
        for k, v in sorted(RELATIONS.items())
    ]
    if getattr(args, "json", False):
        print(_json.dumps({"schema": RELATIONS_SCHEMA, "relations": items}, indent=2))
    else:
        print(f"  {len(items)} relations  [{RELATIONS_SCHEMA}]")
        print("  note: v2 operators are directional (antisymmetric N_k); marginal stays identity (I5.1)")
        for r in items:
            print(f"    {r['relation']:<20} {r['direction']}")
    return 0
