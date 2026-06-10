"""lgwks_rank — cubic node centrality (Z-eigenpair) + AI-discrepancy δ (I6).

Deterministic, batch-offline, no AI in path (INGESTION-LAYER §0, §4.3).
Same graph → byte-identical centrality vector, rankings, and δ values.

Authority: spec/second-harness/INGESTION-LAYER.md §4.3
Schema:    lgwks.rank.record.v1
Issue:     #60 (I6)

Formulas (§4.3):
    x ← normalize( Σ_k w_k T_k x )      power iteration (seeded, deterministic)
    δᵢ = | rank_det(i) − rank_ai(i) |    AI-discrepancy signal
    lane = "human" if δ in top DELTA_HUMAN_PERCENTILE, else "auto"

Representation: T_k is SPARSE — dict[int, dict[int, float]] per relation.
Never a dense n×n matrix; n≈5000 nodes / ~8k edges is pure-python fine.

Decisions (spec §"Decisions"):
  D1: conformance weight = edge confidence_score (standalone, no I5 store dep)
  D2: rank_ai = per-node mean of incident edge confidence_score (ascending mean = ascending rank)
  D3: δ → human threshold = top DELTA_HUMAN_PERCENTILE = 0.10
  D4: w_k = uniform 1.0 for all relations
  D5: symmetrize T_k after building (directed:false corpora)
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.rank.record.v1"

# ---------------------------------------------------------------------------
# Constants (pre-registered at module level per spec)
# ---------------------------------------------------------------------------

# The 8 declared relation types (mirrors RELATIONS in lgwks_score.py).
RELATIONS: tuple[str, ...] = (
    "calls", "contains", "method", "inherits",
    "uses", "rationale_for", "imports_from", "case_of",
)

# Relation weights w_k: uniform 1.0 (Decision D4).
RELATION_WEIGHTS: dict[str, float] = {r: 1.0 for r in RELATIONS}

# Power-iteration convergence threshold ‖Δx‖ < CONVERGE_TOL.
CONVERGE_TOL: float = 1e-9

# Maximum power-iteration steps before giving up (guards against degenerate inputs).
MAX_ITER: int = 5_000

# Top-decile δ threshold → human lane (Decision D3).
# Pre-registered: the 10% of nodes with the largest |rank_det − rank_ai| go to human review.
DELTA_HUMAN_PERCENTILE: float = 0.10


# ---------------------------------------------------------------------------
# Output contract: lgwks.rank.record.v1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankRecord:
    """One ranked node. schema_id is always lgwks.rank.record.v1.

    Fields match the output contract in the I6 spec exactly:
        node_cid   — node identifier from the graph (graph 'id' field)
        centrality — f32-precision Z-eigenvector component (non-negative)
        rank_det   — 1-indexed rank by descending centrality (deterministic)
        rank_ai    — 1-indexed rank by descending mean incident confidence_score (AI signal)
        delta      — |rank_det − rank_ai| (AI-discrepancy)
        lane       — "human" if δ in top DELTA_HUMAN_PERCENTILE, else "auto"
        schema_id  — always "lgwks.rank.record.v1"
    """
    node_cid: str
    centrality: float      # f32
    rank_det: int
    rank_ai: int
    delta: int
    lane: str              # "auto" | "human"
    schema_id: str


# ---------------------------------------------------------------------------
# D0: sparse relational tensor builder
# T_k[i][j] = conformance ∈ [0,1]; SPARSE: dict[int, dict[int, float]]
# Symmetrized after construction: T_k ← (T_k + T_kᵀ) / 2 (Decision D5)
# Conformance weight = edge confidence_score (Decision D1)
# ---------------------------------------------------------------------------


def build_tensor(
    graph: dict[str, Any],
    *,
    relations: tuple[str, ...] = RELATIONS,
) -> tuple[list[str], dict[str, dict[int, dict[int, float]]]]:
    """Build sparse relational tensor from a graph.json structure.

    Returns:
        node_ids: stable-ordered list of node id strings (index = matrix row/col)
        T_k:      dict[relation_str -> dict[i -> dict[j -> weight]]]

    The graph format (from eval corpora):
        nodes: list of {"id": str, ...}
        links: list of {"source": str, "target": str, "relation": str,
                         "confidence_score": float, "weight": float, ...}
    """
    # Build node index — stable order (insertion order from nodes list).
    node_ids: list[str] = [n["id"] for n in graph.get("nodes", [])]
    idx: dict[str, int] = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)

    # Initialize empty adjacency per relation (only known relations; unknowns skipped).
    T_k: dict[str, dict[int, dict[int, float]]] = {r: {} for r in relations}

    def _set(adj: dict[int, dict[int, float]], i: int, j: int, v: float) -> None:
        if i not in adj:
            adj[i] = {}
        adj[i][j] = adj[i].get(j, 0.0) + v

    # Accumulate directed edges first (may have duplicate (i,j) in same relation).
    for link in graph.get("links", []):
        rel = link.get("relation", "")
        if rel not in T_k:
            continue  # //why: unknown relations ignored; only declared 8 are modelled
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src not in idx or tgt not in idx:
            continue  # //why: dangling edge — skip silently; eval graphs are well-formed
        i = idx[src]
        j = idx[tgt]
        conf = float(link.get("confidence_score", link.get("weight", 1.0)))
        conf = max(0.0, min(1.0, conf))  # clamp to [0,1]
        _set(T_k[rel], i, j, conf)

    # Symmetrize: T_k ← (T_k + T_kᵀ) / 2 (Decision D5 — directed:false corpora).
    for rel in relations:
        adj = T_k[rel]
        # Collect all (i, j) pairs
        pairs: list[tuple[int, int, float]] = []
        for i, cols in adj.items():
            for j, v in cols.items():
                pairs.append((i, j, v))
        # Build symmetric version
        sym: dict[int, dict[int, float]] = {}
        all_keys: set[tuple[int, int]] = set()
        for i, j, _ in pairs:
            all_keys.add((i, j))
            all_keys.add((j, i))
        for (i, j) in all_keys:
            v_ij = adj.get(i, {}).get(j, 0.0)
            v_ji = adj.get(j, {}).get(i, 0.0)
            sym_val = (v_ij + v_ji) / 2.0
            if sym_val > 0.0:
                if i not in sym:
                    sym[i] = {}
                sym[i][j] = sym_val
        T_k[rel] = sym

    return node_ids, T_k


# ---------------------------------------------------------------------------
# D1: power iteration for Z-eigenpair
# x ← normalize( Σ_k w_k T_k x )    seeded deterministic; converge ‖Δx‖ < CONVERGE_TOL
# ---------------------------------------------------------------------------


def _l2_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _normalize(v: list[float]) -> list[float]:
    """L2-normalize v. Returns v unchanged (all zeros) if norm < 1e-12."""
    n = _l2_norm(v)
    if n < 1e-12:
        return v
    inv_n = 1.0 / n
    return [x * inv_n for x in v]


def _sparse_matvec(
    adj: dict[int, dict[int, float]],
    x: list[float],
    n: int,
) -> list[float]:
    """Sparse matrix-vector product y = A x.

    adj: row-major sparse dict; x: dense vector length n; returns dense y.
    //why: pure-python sparse is adequate for n~5k / ~8k edges per graph.
    """
    y = [0.0] * n
    for i, cols in adj.items():
        s = 0.0
        for j, v in cols.items():
            s += v * x[j]
        y[i] = s
    return y


def power_iteration(
    node_ids: list[str],
    T_k: dict[str, dict[int, dict[int, float]]],
    *,
    weights: dict[str, float] | None = None,
    tol: float = CONVERGE_TOL,
    max_iter: int = MAX_ITER,
    seed: int = 0,
) -> tuple[list[float], int, float]:
    """Z-eigenpair power iteration on the symmetric 3-tensor.

    x ← normalize( Σ_k w_k T_k x )

    Seed: deterministic uniform initialization with 1/sqrt(n).
    Returns: (x, iterations, final_delta)
    //why: seeded uniform x₀ → reproducible across runs (spec Decision D seeds).
    """
    n = len(node_ids)
    if n == 0:
        return [], 0, 0.0

    ws = weights if weights is not None else RELATION_WEIGHTS

    # Deterministic seed: uniform 1/sqrt(n).
    # //why: uniform is the standard PageRank-style seed; maximally non-committal.
    x: list[float] = [1.0 / math.sqrt(n)] * n

    final_delta = 0.0
    iters = 0
    for iters in range(1, max_iter + 1):
        # y = Σ_k w_k T_k x
        y = [0.0] * n
        for rel, adj in T_k.items():
            w = ws.get(rel, 1.0)
            if w == 0.0 or not adj:
                continue
            ty = _sparse_matvec(adj, x, n)
            for i in range(n):
                y[i] += w * ty[i]

        # Normalize
        x_new = _normalize(y)
        if not any(x_new):
            # All-zero: trivially converged (isolated graph or zero-weight tensor).
            break

        # Convergence check ‖Δx‖₂
        delta = _l2_norm([a - b for a, b in zip(x_new, x)])
        x = x_new
        final_delta = delta
        if delta < tol:
            break

    return x, iters, final_delta


# ---------------------------------------------------------------------------
# D2: AI signal — per-node mean incident confidence_score → rank_ai
# //why: uses the graph's own AI-emitted confidence_score as the AI signal;
# no external model call; standalone (Decision D2).
# ---------------------------------------------------------------------------


def compute_rank_ai(
    graph: dict[str, Any],
    node_ids: list[str],
) -> list[float]:
    """Compute per-node mean incident confidence_score (AI proxy signal).

    For isolated nodes (no incident edges), mean = 0.0.
    Returns a list aligned to node_ids index.
    """
    idx: dict[str, int] = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    total = [0.0] * n
    count = [0] * n

    for link in graph.get("links", []):
        src = link.get("source", "")
        tgt = link.get("target", "")
        conf = float(link.get("confidence_score", link.get("weight", 1.0)))
        for nid in (src, tgt):
            if nid in idx:
                i = idx[nid]
                total[i] += conf
                count[i] += 1

    return [total[i] / count[i] if count[i] > 0 else 0.0 for i in range(n)]


# ---------------------------------------------------------------------------
# D2: δ computation + lane assignment
# ---------------------------------------------------------------------------


def compute_delta(
    rank_det: list[int],
    rank_ai: list[int],
    *,
    human_percentile: float = DELTA_HUMAN_PERCENTILE,
) -> tuple[list[int], list[str]]:
    """Compute |rank_det(i) − rank_ai(i)| and assign lanes.

    Top human_percentile fraction of δ values → lane="human"; rest → "auto".
    Ties are resolved by placing them in "human" (conservative).
    Returns: (deltas, lanes)
    """
    n = len(rank_det)
    deltas = [abs(rank_det[i] - rank_ai[i]) for i in range(n)]

    # Determine threshold: top-decile cut (pre-registered DELTA_HUMAN_PERCENTILE).
    # //why: threshold is computed from the distribution itself so it adapts to graph size
    # while keeping the fraction constant — matches the spec "top-decile" language.
    if n == 0:
        return [], []

    threshold_count = max(1, math.ceil(n * human_percentile))
    sorted_deltas = sorted(deltas, reverse=True)
    # The threshold δ value is the smallest in the top-decile.
    delta_cutoff = sorted_deltas[threshold_count - 1]

    lanes = ["human" if d >= delta_cutoff else "auto" for d in deltas]
    return deltas, lanes


# ---------------------------------------------------------------------------
# Top-level: rank_graph → list[RankRecord]
# ---------------------------------------------------------------------------


def _to_f32(x: float) -> float:
    """Round-trip through float32 for storage precision (matches lgwks_score.py style)."""
    return float(struct.unpack("f", struct.pack("f", x))[0])


def rank_graph(
    graph: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> list[RankRecord]:
    """Full ranking pipeline: tensor → power iteration → δ → RankRecord list.

    Returns records sorted by rank_det (ascending = best first).
    """
    node_ids, T_k = build_tensor(graph)
    n = len(node_ids)
    if n == 0:
        return []

    # D1: cubic centrality
    x, _iters, _delta = power_iteration(node_ids, T_k, weights=weights)

    # rank_det: 1-indexed rank by descending centrality
    # Stable sort: ties broken by node_id string for determinism.
    order_det = sorted(range(n), key=lambda i: (-x[i], node_ids[i]))
    rank_det = [0] * n
    for rank, node_idx in enumerate(order_det, start=1):
        rank_det[node_idx] = rank

    # D2: AI signal — per-node mean incident confidence_score
    ai_scores = compute_rank_ai(graph, node_ids)
    order_ai = sorted(range(n), key=lambda i: (-ai_scores[i], node_ids[i]))
    rank_ai = [0] * n
    for rank, node_idx in enumerate(order_ai, start=1):
        rank_ai[node_idx] = rank

    # δ + lane assignment
    deltas, lanes = compute_delta(rank_det, rank_ai)

    records = []
    for i, nid in enumerate(node_ids):
        records.append(RankRecord(
            node_cid=nid,
            centrality=_to_f32(x[i]),
            rank_det=rank_det[i],
            rank_ai=rank_ai[i],
            delta=deltas[i],
            lane=lanes[i],
            schema_id=SCHEMA,
        ))

    # Return sorted by deterministic rank
    records.sort(key=lambda r: (r.rank_det, r.node_cid))
    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_parser(sub) -> None:
    p = sub.add_parser("rank", help="cubic node centrality + AI-discrepancy δ (I6)")
    sp = p.add_subparsers(dest="rank_cmd", required=True)

    run_p = sp.add_parser("run", help="rank a graph.json file")
    run_p.add_argument("graph", help="path to graph.json")
    run_p.add_argument("--top", type=int, default=20, metavar="N",
                       help="number of top nodes to display (default: 20)")
    run_p.add_argument("--json", action="store_true", help="output full JSON")
    run_p.add_argument("--human-only", action="store_true",
                       help="show only human-lane nodes")
    run_p.set_defaults(func=_cmd_run)

    info_p = sp.add_parser("info", help="show module constants (threshold, relations)")
    info_p.set_defaults(func=_cmd_info)


def _cmd_run(args) -> int:
    import sys as _sys

    try:
        with open(args.graph, encoding="utf-8") as f:
            graph = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot load graph: {e}", file=_sys.stderr)
        return 1

    records = rank_graph(graph)
    if not records:
        print("no nodes found in graph")
        return 0

    if getattr(args, "json", False):
        import json as _json
        output = [
            {
                "node_cid": r.node_cid,
                "centrality": r.centrality,
                "rank_det": r.rank_det,
                "rank_ai": r.rank_ai,
                "delta": r.delta,
                "lane": r.lane,
                "schema_id": r.schema_id,
            }
            for r in records
        ]
        if getattr(args, "human_only", False):
            output = [o for o in output if o["lane"] == "human"]
        print(_json.dumps(output, indent=2))
        return 0

    # Text display
    top = getattr(args, "top", 20)
    show = [r for r in records if not getattr(args, "human_only", False) or r.lane == "human"]
    show = show[:top]

    human_count = sum(1 for r in records if r.lane == "human")
    print(f"  {len(records)} nodes  [{SCHEMA}]")
    print(f"  human-lane: {human_count}  ({human_count/len(records)*100:.1f}%)")
    print(f"  threshold: top {DELTA_HUMAN_PERCENTILE*100:.0f}% δ  "
          f"(DELTA_HUMAN_PERCENTILE={DELTA_HUMAN_PERCENTILE})")
    print()
    print(f"  {'rank':>4}  {'node_cid':<40}  {'centrality':>12}  "
          f"{'rank_ai':>7}  {'delta':>5}  {'lane'}")
    print("  " + "-" * 82)
    for r in show:
        print(f"  {r.rank_det:>4}  {r.node_cid[:40]:<40}  {r.centrality:>12.6f}  "
              f"{r.rank_ai:>7}  {r.delta:>5}  {r.lane}")
    return 0


def _cmd_info(args) -> int:
    print(f"  schema:                {SCHEMA}")
    print(f"  DELTA_HUMAN_PERCENTILE: {DELTA_HUMAN_PERCENTILE}")
    print(f"  CONVERGE_TOL:          {CONVERGE_TOL}")
    print(f"  MAX_ITER:              {MAX_ITER}")
    print(f"  relations ({len(RELATIONS)}):")
    for r in RELATIONS:
        print(f"    {r:<20} w={RELATION_WEIGHTS[r]}")
    return 0
