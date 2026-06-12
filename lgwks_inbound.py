"""lgwks_inbound — L5 consumer pack: RRF fusion + token-budgeted reflex envelope (I7).

The AI-consumer tail (INGESTION-LAYER §7). Assembly + budgeting ONLY — no generation
(PRD-04 INV-3), no new scoring math (consume I6 graph rank + I1 vector cosine as-is),
no model layer. The consumer reads math + content-addressed pointers, never raw prose.

Authority: spec/second-harness/prd/PRD-04-context-economy.md §Contract / §04-a,b
           spec/second-harness/INGESTION-LAYER.md §7 (L1→L5 strip ladder, §7-INV)
Schema:    lgwks.inbound.v1   (family: harness)
Issue:     #61 (I7)

Formula — Reciprocal Rank Fusion (Cormack et al. 2009):
    RRF(cid) = Σ_lists  1 / (k + rank_list(cid))
    lists = { graph: rank_det from lgwks_rank ; vector: dense rank by cosine to query }
Deterministic by construction: same (graph ranks, vector ranks, k) → identical fused
order (ties broken by cid). §7-INV: no prose crosses into L5; pack ≤ reflex cap; every
handle resolves to a cid present in the store (no dangling/hallucinated reference).

Decisions:
  D1: RRF_K = 60 — the canonical Cormack 2009 constant, PRE-REGISTERED. The only knob;
      not tuned inside this packet (PRD-04 open-Q defers reflex-cap sizing to SCIENCE).
  D2: candidate universe = graph node cids that ALSO resolve in the vector store. A cid
      that does not resolve via get_record is NEVER emitted as a handle (zero-dangling).
  D3: token estimate = ceil(len(serialized_json)/4) — deterministic char/4 heuristic; no
      model call (repo has no token counter — grep'd). Cap is on the SERIALIZED reflex pack.
  D4: truncation drops bulk (lowest-RRF handle + its score) FIRST; a depth_handle pointer
      is dropped only if every bulk handle is already gone (PRD-04 line 52: "a pointer is
      never dropped for bulk"). Every dropped cid is recorded in budget.truncated — no
      silent drop (INV: no silent failure).
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

import lgwks_access
import lgwks_rank
import lgwks_vector
from lgwks_rank import RankRecord

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.inbound.v1"

# RRF fusion constant — PRE-REGISTERED (Cormack 2009). //why: the canonical default;
# RRF is insensitive to k near this value and tuning it here would be a hidden knob.
RRF_K = 60

# PRD-04 reflex cap default (tunable, never absent).
DEFAULT_LIMIT_TOKENS = 1500


class InboundError(RuntimeError):
    """Contract violation in the inbound assembly layer."""


# ---------------------------------------------------------------------------
# Token estimator (deterministic, no model call) — Decision D3
# ---------------------------------------------------------------------------

def est_tokens(text: str) -> int:
    """Deterministic char/4 token estimate. //why: repo has no tokenizer dep and a
    model call is out of scope (INGESTION-LAYER §0); char/4 is the standard offline
    heuristic and only needs to be a stable, monotone proxy for the cap to be enforceable.
    """
    return math.ceil(len(text) / 4)


def _serialize(pack: dict[str, Any]) -> str:
    """Canonical serialization the cap is measured against. sort_keys → replayable."""
    return json.dumps(pack, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def _dense_rank(scored: list[tuple[str, float]]) -> dict[str, int]:
    """1-indexed dense rank by descending score, ties broken by cid (deterministic)."""
    order = sorted(scored, key=lambda cs: (-cs[1], cs[0]))
    return {cid: i for i, (cid, _score) in enumerate(order, start=1)}


def fuse(
    graph_ranks: list[RankRecord],
    vector_ranks: list[tuple[str, float]],
    *,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion of the graph rank list ⊕ the vector cosine list.

    graph_ranks : RankRecords (use rank_det, already 1-indexed best-first).
    vector_ranks: (cid, cosine) pairs; dense-ranked here by cosine desc.
    Returns (cid, fused_score) best-first. A cid contributes only from the lists it
    appears in (standard RRF). Single-list fusion is valid (PRD-04 04-b).
    """
    if k <= 0:
        raise InboundError(f"RRF k must be positive, got {k}")

    graph_rank = {r.node_cid: r.rank_det for r in graph_ranks}
    vector_rank = _dense_rank(vector_ranks)

    cids = set(graph_rank) | set(vector_rank)
    fused: list[tuple[str, float]] = []
    for cid in cids:
        score = 0.0
        if cid in graph_rank:
            score += 1.0 / (k + graph_rank[cid])
        if cid in vector_rank:
            score += 1.0 / (k + vector_rank[cid])
        fused.append((cid, score))

    # Deterministic order: highest fused score first, ties broken by cid.
    fused.sort(key=lambda cs: (-cs[1], cs[0]))
    return fused


# ---------------------------------------------------------------------------
# Reflex pack assembly + budgeting
# ---------------------------------------------------------------------------

# Upper bound on the number of dropped cids listed inline in budget.truncated. The exact
# count is always in budget.truncated_count; the cid list is a bounded best-first sample so
# the receipt itself can never blow the cap. //why: on the real 5130-node graph an unbounded
# per-cid receipt is ~50k tokens — it would violate the hard cap it is supposed to report.
MAX_TRUNCATED_VISIBLE = 64


def build_pack(
    handles: list[str],
    scores: dict[str, float],
    *,
    limit_tokens: int = DEFAULT_LIMIT_TOKENS,
    depth_handles: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build the lgwks.inbound.v1 reflex envelope, enforcing the token cap.

    handles are ordered RRF-best-first. depth_handles are content-addressed pointers
    ({id, est_tokens, kind}). Truncation drops, in increasing order of protectedness:
    (1) lowest-RRF bulk handles (handle + its score), tail-first; (2) depth-handle pointers,
    only after ALL bulk is shed (PRD-04: "a pointer is never dropped for bulk"); (3) entries
    of the visible truncated sample, only after bulk and pointers are gone. The dropped
    COUNT is always exact (budget.truncated_count) — no silent drop — while the cid list is
    a bounded best-first sample. Returns the typed dict; never a free-text field (§7-INV).
    """
    if limit_tokens <= 0:
        raise InboundError(f"limit_tokens must be positive, got {limit_tokens}")
    missing = [h for h in handles if h not in scores]
    if missing:
        raise InboundError(f"handles without a score (contract violation): {missing}")

    kept_handles = list(handles)
    kept_depth = list(depth_handles or [])
    dropped: list[str] = []        # bulk cids dropped, in pop order (worst-RRF first)
    visible_cap = MAX_TRUNCATED_VISIBLE

    def assemble() -> dict[str, Any]:
        # Visible sample: highest-RRF among the dropped first (= reverse of pop order).
        visible = list(reversed(dropped))[:visible_cap]
        return {
            "schema": SCHEMA,
            "handles": list(kept_handles),
            "scores": {cid: scores[cid] for cid in kept_handles},
            "budget": {
                "limit_tokens": limit_tokens,
                # Measured against a MAX-WIDTH placeholder (= limit_tokens). used_tokens
                # itself is self-referential — writing it changes the serialized size — so
                # we size the pack as if the counter were at its widest. The emitted value
                # is always ≤ limit (hence ≤ digits), so the final pack can only be smaller:
                # the cap then holds by construction, never by luck.
                "used_tokens": limit_tokens,
                "truncated_count": len(dropped),   # exact — never silent
                "truncated": visible,              # bounded best-first sample
            },
            "depth_handles": list(kept_depth),
        }

    while True:
        pack = assemble()
        used = est_tokens(_serialize(pack))
        if used <= limit_tokens:
            pack["budget"]["used_tokens"] = used
            return pack
        if kept_handles:
            dropped.append(kept_handles.pop())     # lowest RRF (tail) first
        elif kept_depth:
            kept_depth.pop()                        # pointer shed only after all bulk gone
        elif visible_cap > 0:
            visible_cap = visible_cap // 2          # shrink the receipt sample (count stays exact)
        else:
            # Even an empty envelope (no handles, no pointers, no sample) exceeds the cap —
            # genuinely degenerate config, surface loudly.
            raise InboundError(
                f"reflex cap {limit_tokens} too small for an empty envelope "
                f"(needs {used}); raise limit_tokens"
            )


def assemble_inbound(
    query_embedding: Optional[lgwks_vector.VectorRecord],
    graph: dict[str, Any],
    store_conn=None,
    *,
    limit_tokens: int = DEFAULT_LIMIT_TOKENS,
    k: int = RRF_K,
    tenant_store: Optional[lgwks_access.TenantStore] = None,
    ctx: Optional[Any] = None,
) -> dict[str, Any]:
    """End-to-end: graph cubic rank ⊕ vector cosine rank → fused → token-budgeted pack.

    query_embedding : an ALREADY-embedded query vector (model layer out of scope — we do
                      NOT embed here). If None, RRF runs on the graph list alone.
    graph           : graph.json structure (consumed by lgwks_rank.rank_graph).
    store_conn      : open vector store connection (lgwks_vector). Required when ctx is None.
    tenant_store    : when set, every cid is resolved through a validated
                      CapabilityPort handle via lgwks_access.TenantStore.read —
                      own ⊕ world only (ARCH L1/L2). When None, the legacy
                      single-operator unscoped resolver is used (no multi-tenant
                      boundary, admin sentinel path).
    ctx             : lgwks_session.RequestContext — when provided, supersedes
                      store_conn + tenant_store. store_conn may be None when ctx is set.
    Raises lgwks_rank.RankError on non-convergence (no silent failure).
    Raises lgwks_vector.SpaceMismatchError if the query crosses embedding spaces.
    """
    if ctx is not None:
        tenant_store = ctx.store
    elif store_conn is None:
        raise ValueError("store_conn is required when ctx is None")
    graph_ranks = lgwks_rank.rank_graph(graph)

    # Candidate universe = graph cids that resolve in the store (zero-dangling, D2).
    # Under a tenant scope, "resolve" means own ⊕ world through the access router.
    def _resolve(cid: str) -> Optional[lgwks_vector.VectorRecord]:
        if tenant_store is not None:
            return tenant_store.read(cid)
        # tenant_store=None: single-operator fail-open (issue #99 keeps this escape hatch).
        if store_conn is None:
            raise ValueError("store_conn required when tenant_store is None")
        return lgwks_vector.get_record(store_conn, cid, admin=lgwks_vector.ADMIN)

    resolved: list[RankRecord] = []
    records: dict[str, lgwks_vector.VectorRecord] = {}
    for r in graph_ranks:
        rec = _resolve(r.node_cid)
        if rec is not None:
            resolved.append(r)
            records[r.node_cid] = rec

    # Vector lane: cosine of the query to each resolved record (surface space mismatch).
    vector_ranks: list[tuple[str, float]] = []
    if query_embedding is not None:
        for cid, rec in records.items():
            # require_same_space raises SpaceMismatchError — never silently skip.
            sim = lgwks_vector.cosine(query_embedding, rec)
            vector_ranks.append((cid, sim))

    fused = fuse(resolved, vector_ranks, k=k)

    handles = [cid for cid, _score in fused]
    score_map = {cid: score for cid, score in fused}
    depth_handles = [
        {
            "id": cid,
            "est_tokens": est_tokens(records[cid].embedding.hex()),
            "kind": records[cid].modality,   # typed enum (lgwks_vector.MODALITIES)
        }
        for cid in handles
    ]
    return build_pack(handles, score_map, limit_tokens=limit_tokens, depth_handles=depth_handles)


# ---------------------------------------------------------------------------
# CLI — verb `inbound` with run/info (mirrors lgwks_rank.add_parser)
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("inbound", help="L5 consumer pack: RRF fusion + reflex budget (I7)")
    sp = p.add_subparsers(dest="inbound_cmd", required=True)

    run_p = sp.add_parser("run", help="assemble a reflex pack from a graph.json + vector store")
    run_p.add_argument("graph", help="path to graph.json (graph rank lane)")
    run_p.add_argument("--store", metavar="PATH",
                       help="path to the vector store (.db); omit for graph-only RRF")
    run_p.add_argument("--query-cid", metavar="CID",
                       help="cid of an already-embedded query vector in the store "
                            "(enables the vector cosine lane)")
    run_p.add_argument("--limit-tokens", type=int, default=DEFAULT_LIMIT_TOKENS,
                       metavar="N", help=f"reflex cap (default: {DEFAULT_LIMIT_TOKENS})")
    run_p.add_argument("--tenant", metavar="T",
                       help="resolve cids under §1-INV (own ⊕ world) for tenant T; "
                            "cross-tenant nodes are dropped (ARCH L1). Omit for the "
                            "single-operator unscoped read.")
    run_p.set_defaults(func=_cmd_run)

    info_p = sp.add_parser("info", help="show module constants (RRF_K, cap, schema)")
    info_p.set_defaults(func=_cmd_info)


def _cmd_run(args) -> int:
    import sys as _sys
    from pathlib import Path

    try:
        with open(args.graph, encoding="utf-8") as f:
            graph = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot load graph: {e}", file=_sys.stderr)
        return 1

    store_path = getattr(args, "store", None)
    if not store_path:
        # Graph-only: no store means no zero-dangling guarantee against a store, so we
        # fuse the graph lane alone and emit handles + scores with empty depth_handles.
        graph_ranks = lgwks_rank.rank_graph(graph)
        fused = fuse(graph_ranks, [])
        handles = [cid for cid, _s in fused]
        scores = {cid: s for cid, s in fused}
        pack = build_pack(handles, scores, limit_tokens=args.limit_tokens)
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 0

    conn = lgwks_vector.create_store(Path(store_path))
    tenant = getattr(args, "tenant", None)
    try:
        ctx = None
        if tenant is not None:
            import lgwks_session as _session
            ctx = _session.make_context(tenant, "cli", "inbound-cli", conn)

        query_embedding = None
        qcid = getattr(args, "query_cid", None)
        if qcid:
            if ctx is not None:
                query_embedding = ctx.store.read(qcid)
            else:
                query_embedding = lgwks_vector.get_record(conn, qcid, admin=lgwks_vector.ADMIN)
            if query_embedding is None:
                print(f"error: query cid {qcid!r} not found in store", file=_sys.stderr)
                return 1
        try:
            pack = assemble_inbound(
                query_embedding, graph,
                None if ctx is not None else conn,
                limit_tokens=args.limit_tokens,
                ctx=ctx,
            )
        except lgwks_rank.RankError as e:
            print(f"error: graph rank did not converge: {e}", file=_sys.stderr)
            return 1
        except lgwks_vector.SpaceMismatchError as e:
            print(f"error: {e}", file=_sys.stderr)
            return 1
    finally:
        conn.close()

    print(json.dumps(pack, indent=2, sort_keys=True))
    return 0


def _cmd_info(args) -> int:
    print(f"  schema:          {SCHEMA}")
    print(f"  RRF_K:           {RRF_K}  (Cormack 2009, pre-registered)")
    print(f"  reflex cap:      {DEFAULT_LIMIT_TOKENS} tokens (default, tunable)")
    print(f"  token estimate:  ceil(len(serialized)/4)  (deterministic, no model call)")
    print(f"  truncation:      bulk (lowest-RRF) dropped first; depth pointers survive")
    return 0
