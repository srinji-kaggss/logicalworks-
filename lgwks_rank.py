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

Decisions (corrected end-to-end so δ is a real signal, not noise):
  D1: T conformance weight = edge confidence_score (standalone, no I5 store dep)
  D2: rank_det = relation-WEIGHTED centrality (schema w_k); rank_ai = relation-BLIND
      centrality (uniform w_k) — the §4.3 order-2 "relation-collapsed special case".
      δ = |rank_det − rank_ai| measures how the schema's relation typing reorders a node.
      //why not confidence_score: it is a constant 1.0 on the corpora — zero variance,
      so a confidence-based rank_ai degenerates to noise. Structure carries the real signal.
  D3: δ → human threshold = top DELTA_HUMAN_PERCENTILE = 0.10
  D4: w_k = schema-declared NON-UNIFORM (see RELATION_WEIGHTS) — required for order-3≠order-2
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


class RankError(RuntimeError):
    """Raised when ranking cannot produce a trustworthy result (e.g. non-convergence)."""

# ---------------------------------------------------------------------------
# Constants (pre-registered at module level per spec)
# ---------------------------------------------------------------------------

# The 8 declared relation types (mirrors RELATIONS in lgwks_score.py).
RELATIONS: tuple[str, ...] = (
    "calls", "contains", "method", "inherits",
    "uses", "rationale_for", "imports_from", "case_of",
    "image", "video",
)

# Schema-declared relation weights w_k (§4.3). NON-UNIFORM by design: this is exactly what
# makes the relation-typed (order-3) centrality differ from the relation-blind (order-2)
# view, and therefore what makes δ a real signal rather than noise. Pre-registered,
# replayable constants — not learned, no AI in path.
# //why these values: structural coupling strength — type/inheritance/import edges bind a
# node into the system more tightly than containment or narration. Tune via the relation schema.
RELATION_WEIGHTS: dict[str, float] = {
    "inherits": 1.0,
    "imports_from": 0.9,
    "calls": 0.8,
    "method": 0.7,
    "uses": 0.6,
    "contains": 0.5,
    "rationale_for": 0.4,
    "case_of": 0.4,
    "image": 0.3,
    "video": 0.3,
}

# Relation-BLIND weights — the order-2 / AI analog (§4.3 "relation-collapsed special case").
# rank_ai ranks by this; δ = |relation-weighted − relation-blind| is the discrepancy signal.
UNIFORM_WEIGHTS: dict[str, float] = {r: 1.0 for r in RELATIONS}

# Power-iteration convergence threshold ‖Δx‖ < CONVERGE_TOL.
CONVERGE_TOL: float = 1e-9

# Maximum power-iteration steps before giving up (guards against degenerate inputs).
# //why 20k: convergence is on the dominant eigenvalue (Rayleigh quotient); small-spectral-gap
# graphs (e.g. logic-os-kernel relation-blind) need a few thousand steps. Headroom over the
# observed worst case (~4.5k) so a tighter gap still lands inside the cap, not at the guard.
MAX_ITER: int = 20_000

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
        rank_det   — 1-indexed rank by relation-WEIGHTED (order-3) centrality
        rank_ai    — 1-indexed rank by relation-BLIND (order-2) centrality (§4.3 AI analog)
        delta      — |rank_det − rank_ai| (relation-typing discrepancy)
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
    """Z-eigenpair power iteration on the symmetric 3-tensor, spectrally shifted.

    x ← normalize( (M + σI) x )   where M = Σ_k w_k T_k,  σ = spectral-radius bound

    //why the shift: M is a symmetric non-negative matrix, so its spectrum can include a
    negative eigenvalue with |λ_min| ≈ λ_max (near-bipartite structure — e.g. the
    logic-os-kernel graph). Plain power iteration then OSCILLATES and never converges.
    Adding σI (σ ≥ ρ(M)) shifts every eigenvalue by σ → all ≥ 0, the Perron eigenvalue
    becomes the unique dominant one, and iteration converges to the Perron centrality
    vector. M and M+σI share eigenVECTORS exactly, so the ranking is unchanged — only
    convergence is fixed. Deterministic.

    Seed: deterministic uniform 1/sqrt(n). Returns: (x, iterations, final_delta).
    """
    n = len(node_ids)
    if n == 0:
        return [], 0, 0.0

    ws = weights if weights is not None else RELATION_WEIGHTS

    # σ = max weighted row-sum ≥ ρ(M) (Gershgorin bound on a symmetric non-negative matrix).
    row_sum = [0.0] * n
    for rel, adj in T_k.items():
        w = ws.get(rel, 1.0)
        if w == 0.0 or not adj:
            continue
        for i, cols in adj.items():
            row_sum[i] += w * sum(abs(v) for v in cols.values())
    sigma = max(row_sum) if row_sum else 0.0

    # Deterministic seed: uniform 1/sqrt(n).
    # //why: uniform is the standard PageRank-style seed; maximally non-committal.
    x: list[float] = [1.0 / math.sqrt(n)] * n

    final_delta = 0.0
    iters = 0
    lam_prev = 0.0
    for iters in range(1, max_iter + 1):
        # y = (M + σI) x = Σ_k w_k T_k x + σ x
        y = [sigma * xi for xi in x]
        for rel, adj in T_k.items():
            w = ws.get(rel, 1.0)
            if w == 0.0 or not adj:
                continue
            ty = _sparse_matvec(adj, x, n)
            for i in range(n):
                y[i] += w * ty[i]

        # Dominant-eigenvalue (Rayleigh quotient) estimate: ‖y‖ since x is unit-norm.
        lam = _l2_norm(y)

        x_new = _normalize(y)
        if not any(x_new):
            # All-zero: trivially converged (isolated graph or zero-weight tensor).
            break

        # Convergence on the eigenvalue, not the vector.
        # //why: under a small spectral gap the eigenVECTOR drifts for ~2x longer than the
        # eigenVALUE settles; the eigenvalue criterion converges quadratically faster and
        # still pins the dominant (Perron) subspace that the ranking reads. Deterministic.
        delta = abs(lam - lam_prev)
        x = x_new
        lam_prev = lam
        final_delta = delta
        if iters > 1 and delta < tol:
            break

    return x, iters, final_delta


# ---------------------------------------------------------------------------
# D2: AI signal — the relation-BLIND (order-2) centrality (§4.3)
# //why: §4.3 defines the AI/order-2 analog as the relation-collapsed special case
# (eigenvector of the uniformly-summed adjacency). δ = |relation-weighted rank −
# relation-blind rank| measures exactly how much the schema's relation typing reorders
# a node vs the AI's relation-agnostic view. Pure structure: no embeddings, no per-edge
# confidence_score (which is a constant 1.0 on the corpora and carries no signal).
# ---------------------------------------------------------------------------


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


def _centrality(
    node_ids: list[str],
    T_k: dict[str, dict[int, dict[int, float]]],
    weights: dict[str, float],
    max_iter: int,
    label: str,
) -> list[float]:
    """Run guarded power iteration and return the centrality vector.

    //why: never present a non-converged centrality as trustworthy (no silent failure).
    Early break leaves delta=0.0 (converged/degenerate); only a maxed-out run still above
    tolerance is a real failure.
    """
    x, iters, delta = power_iteration(node_ids, T_k, weights=weights, max_iter=max_iter)
    if delta >= CONVERGE_TOL and iters >= max_iter:
        raise RankError(
            f"{label} power iteration did not converge: Δλ={delta:.2e} after {iters} "
            f"iterations (tol={CONVERGE_TOL}). Raise MAX_ITER or inspect the graph."
        )
    return x


def _ranks_from(centrality: list[float], node_ids: list[str]) -> list[int]:
    """1-indexed rank by descending centrality; ties broken by node_id (deterministic)."""
    n = len(centrality)
    order = sorted(range(n), key=lambda i: (-centrality[i], node_ids[i]))
    ranks = [0] * n
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    return ranks


def rank_graph(
    graph: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
    max_iter: int = MAX_ITER,
) -> list[RankRecord]:
    """Full ranking pipeline: tensor → two centralities → δ → RankRecord list.

    rank_det = relation-WEIGHTED (order-3) centrality (schema w_k).
    rank_ai  = relation-BLIND (order-2) centrality (uniform w_k) — the §4.3 AI analog.
    δ        = |rank_det − rank_ai| — the slop signal the schema typing produces.
    Returns records sorted by rank_det (best first). Raises RankError on non-convergence.
    """
    node_ids, T_k = build_tensor(graph)
    n = len(node_ids)
    if n == 0:
        return []

    det_weights = weights if weights is not None else RELATION_WEIGHTS

    # rank_det — relation-typed (order-3) centrality
    x = _centrality(node_ids, T_k, det_weights, max_iter, "relation-weighted")
    rank_det = _ranks_from(x, node_ids)

    # rank_ai — relation-blind (order-2) centrality: the relation-collapsed special case
    x_ai = _centrality(node_ids, T_k, UNIFORM_WEIGHTS, max_iter, "relation-blind")
    rank_ai = _ranks_from(x_ai, node_ids)

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
    print(f"  δ = |relation-weighted rank − relation-blind rank|  (order-3 vs order-2)")
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
