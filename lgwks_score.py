"""lgwks_score — deterministic schema scoring: RESCAL order-3 · R_k · MDL (I5).

No AI, no learning in path (INGESTION-LAYER §0, INV-3).
Same schema file + same instance → byte-identical operators, cid, scores across runs/machines.
Batch/offline only — not hot-path.

Authority: spec/second-harness/INGESTION-LAYER.md §4.2/§4.4/§4.5
Schema:    lgwks.score.record.v1
Relations: lgwks.schema.relations.v1
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
RELATIONS_SCHEMA = "lgwks.schema.relations.v1"

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
}

# ---------------------------------------------------------------------------
# D1 — factored relation operators  R_k = P_k · diag(d_k)
# Stored as O(d) per relation — R_k is NEVER materialized as a dense matrix.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactoredRelation:
    """R_k factored as permutation + sign + dimension mask.

    perm=None  → identity P_k (default v1)
    signs=None → all +1 (default v1)
    mask=None  → all-ones d_k (default v1, DECISION §4)
    """
    relation_id: str
    perm: Optional[tuple[int, ...]]    # P_k permutation index; None = identity
    signs: Optional[tuple[int, ...]]   # ±1 per dim (signed perm); None = all +1
    mask: Optional[tuple[bool, ...]]   # d_k bitset; None = all True
    direction: str                      # "directed" | "symmetric"


def _invert_perm(perm: tuple[int, ...]) -> tuple[int, ...]:
    """Inverse permutation: inv[perm[i]] = i."""
    inv = [0] * len(perm)
    for i, p in enumerate(perm):
        inv[p] = i
    return tuple(inv)


def build_operators(dim: int, *, relations: dict = RELATIONS) -> dict[str, FactoredRelation]:
    """Build one FactoredRelation per relation in the schema.

    v1 defaults: identity P_k, all-ones d_k (perm=None, mask=None).
    dim is validated; operators are dimension-agnostic at default.
    """
    if dim < 1:
        raise ValueError(f"dim must be ≥ 1, got {dim}")
    return {
        rel_id: FactoredRelation(
            relation_id=rel_id,
            perm=None,
            signs=None,
            mask=None,
            direction=props["direction"],
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

    return sum(l * r for l, r in zip(lhs, rhs))


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
        print("  note: v1 operators are identity; direction is declared, not yet active (I5.1)")
        for r in items:
            print(f"    {r['relation']:<20} {r['direction']}")
    return 0
