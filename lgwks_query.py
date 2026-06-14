"""lgwks_query — the unified daemon query surface (#124).

"Browser/Google for agents": graph, vector, transcripts, run artifacts, symbols,
facts, and source memory answer through ONE read contract that returns
**provenance + stable CIDs, not prose**. A pure READ boundary — one filter
envelope in, one hit envelope out. It UNIFIES the existing per-store query
contracts (`lgwks.daemon.events.query.v0`, `lgwks.substrate.*`, `lgwks.graph.*`,
vector recall, entity graph); it does not replace them. #124 is the front
contract; those are its backend adapters.

Two acceptance invariants, both following from "federate over existing
projections, attach the CID each backend already has":
  - PROVENANCE: every hit traces back to a #118 event (`provenance.event_id`) or
    an artifact CID (`provenance.artifact_cid`).
  - DETERMINISM: stable total order `(score desc, cid asc)`. Cross-projection
    scores are normalised to a common [0,1] scale BEFORE the merge.

Score normalisation (documented, reproducible — Calculator Test, no magic
constants): when the request carries text `q`, an adapter's raw score is the
fraction of distinct query tokens that appear in the hit's matched text
(`|matched ∩ q| / |q|`), already in [0,1]. When `q` is null (filter-only query),
every surviving hit scores 1.0. The merge tiebreaks on `cid` ascending, so the
order is a pure function of (store state, request).
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from axiom.cid import compute_cid
from lgwks_daemon_event import SOURCES, TRUST_CLASSES

REQUEST_SCHEMA = "lgwks.daemon.query.v1"
RESULT_SCHEMA = "lgwks.daemon.query.result.v1"

PROJECTIONS = frozenset({"graph", "vector", "transcript", "artifact", "fact", "symbol"})

from lgwks_substrate_config import WORD_RE as _TOKEN_RE  # one source of truth

# An adapter maps a validated request → a list of raw hit dicts for ONE projection.
Adapter = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def score_text(q: str | None, matched_text: str) -> float:
    """Normalised relevance in [0,1]. See module docstring for the definition."""
    if not q:
        return 1.0  # filter-only query: no text ranking signal
    qt = _tokens(q)
    if not qt:
        return 1.0
    return len(qt & _tokens(matched_text)) / len(qt)


def make_hit(
    *,
    cid: str,
    projection: str,
    score: float,
    source: str | None,
    event_id: str | None = None,
    artifact_cid: str | None = None,
    snippet: str | None = None,
    ts: str | None = None,
    trust: str | None = None,
) -> dict[str, Any]:
    """Build one normalised hit. Every hit carries provenance to an event or artifact."""
    return {
        "cid": cid,
        "projection": projection,
        "score": round(float(score), 6),
        "provenance": {"event_id": event_id, "artifact_cid": artifact_cid, "source": source},
        "snippet": snippet,
        "ts": ts,
        "trust": trust,
    }


def build_request(
    *,
    tenant: str,
    q: str | None = None,
    session: str | None = None,
    project: str | None = None,
    source: str | None = None,
    type: str | None = None,
    freshness: str | None = None,
    trust: str | None = None,
    limit: int = 50,
    order: str = "score_desc",
) -> dict[str, Any]:
    request = {
        "schema": REQUEST_SCHEMA,
        "q": q,
        "filters": {
            "tenant": tenant,
            "session": session,
            "project": project,
            "source": source,
            "type": type,
            "freshness": freshness,
            "trust": trust,
        },
        "limit": limit,
        "order": order,
    }
    return validate_request(request)


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("request must be a dict")
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"schema must be {REQUEST_SCHEMA}")
    filters = request.get("filters")
    if not isinstance(filters, dict):
        raise ValueError("filters must be a dict")
    if not filters.get("tenant"):
        raise ValueError("filters.tenant is required (isolation boundary)")
    src = filters.get("source")
    if src is not None and src not in SOURCES:
        raise ValueError(f"filters.source must be one of {sorted(SOURCES)} or null")
    tr = filters.get("trust")
    if tr is not None and tr not in TRUST_CLASSES:
        raise ValueError(f"filters.trust must be one of {sorted(TRUST_CLASSES)} or null")
    if not isinstance(request.get("limit"), int) or request["limit"] < 1:
        raise ValueError("limit must be a positive int")
    if request.get("order") != "score_desc":
        raise ValueError("order must be 'score_desc' (the only stable order: score desc, cid asc)")
    return request


def _passes_filters(hit: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Cross-cutting filters applied centrally after adapters return hits."""
    source = filters.get("source")
    if source is not None and hit["provenance"].get("source") != source:
        return False
    fresh = filters.get("freshness")
    if fresh is not None:
        ts = hit.get("ts")
        # A hit that cannot prove its freshness (no ts) must NOT pass a freshness
        # gate — absence of a timestamp can't masquerade as fresh.
        if ts is None or ts < fresh:
            return False
    trust = filters.get("trust")
    if trust is not None and hit.get("trust") != trust:
        return False
    return True


def query(request: dict[str, Any], adapters: dict[str, Adapter] | None = None) -> dict[str, Any]:
    """Federate the projection adapters into one deterministic, provenance-bearing result."""
    request = validate_request(request)
    adapters = adapters if adapters is not None else default_adapters()
    filters = request["filters"]

    merged: list[dict[str, Any]] = []
    for projection, adapter in adapters.items():
        if projection not in PROJECTIONS:
            raise ValueError(f"unknown projection adapter: {projection!r}")
        try:
            hits = adapter(request) or []
        except Exception:
            hits = []  # a degraded backend contributes nothing; it never breaks the federation
        for hit in hits:
            # A malformed hit from one (custom) adapter must not crash the whole
            # federation or the merge/sort — skip it, keep healthy adapters' hits.
            if not isinstance(hit, dict) or not {"cid", "score", "provenance"} <= hit.keys():
                continue
            hit.setdefault("projection", projection)
            if _passes_filters(hit, filters):
                merged.append(hit)

    # Stable total order: score desc, then cid asc (a CID is a full-width hex key).
    merged.sort(key=lambda h: (-h["score"], h["cid"]))
    merged = merged[: request["limit"]]
    return {"schema": RESULT_SCHEMA, "count": len(merged), "hits": merged}


# ── Default backend adapters (real projections, graceful when a store is absent) ──

def transcript_adapter(daemon_db) -> Adapter:
    """Adapt the daemon event store (#118 events) as the `transcript` projection."""
    def _adapter(request: dict[str, Any]) -> list[dict[str, Any]]:
        from lgwks_daemon_store import DaemonEventStore
        filters = request["filters"]
        store = DaemonEventStore(daemon_db)
        try:
            events = store.list_events(
                tenant_id=filters["tenant"],
                session_id=filters.get("session"),
                limit=request["limit"] * 4,  # over-fetch; central filters + sort trim
            )
        finally:
            store.close()
        hits = []
        for ev in events:
            body = json.dumps(ev, sort_keys=True, separators=(",", ":")).encode("utf-8")
            cid = ev.get("payload_cid") or compute_cid(body)
            snippet = json.dumps(ev.get("payload", {}), sort_keys=True)[:200]
            hits.append(make_hit(
                cid=cid,
                projection="transcript",
                score=score_text(request.get("q"), f"{ev.get('kind','')} {snippet}"),
                source=ev.get("source"),
                event_id=ev.get("event_id"),
                snippet=snippet,
                ts=ev.get("ts"),
                trust=ev.get("trust"),
            ))
        return hits
    return _adapter


def _safe_tenant(tenant: str) -> str:
    """Filesystem-safe tenant token for per-tenant store partitioning."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", tenant)


def graph_adapter(graph_db_base) -> Adapter:
    """Adapt the entity graph (`lgwks_entity_graph`) as the `graph` projection.

    TENANT-SCOPED: `graph_db_base` is a DIRECTORY; the adapter resolves a
    per-tenant partition `<base>/<safe(tenant)>.db` at request time. The shared,
    non-partitioned entity graph is NOT exposed through this tenant-mandatory
    surface — a tenant sees only its own partition (absent partition → []),
    so the graph projection cannot leak another tenant's nodes.
    """
    def _adapter(request: dict[str, Any]) -> list[dict[str, Any]]:
        import lgwks_entity_graph
        from pathlib import Path
        tenant = request["filters"]["tenant"]
        db = Path(graph_db_base) / f"{_safe_tenant(tenant)}.db"
        if not db.exists():
            return []
        g = lgwks_entity_graph.GraphDB(db)
        nodes = g.query_nodes(match=request.get("q") or None, limit=request["limit"] * 4)
        hits = []
        for n in nodes:
            label = n.get("label", "") or n.get("node_id", "")
            body = json.dumps(n, sort_keys=True, separators=(",", ":")).encode("utf-8")
            cid = compute_cid(body)
            hits.append(make_hit(
                cid=cid,
                projection="graph",
                score=score_text(request.get("q"), f"{n.get('node_id','')} {label} {n.get('type','')}"),
                source="repo",  # the entity graph is a derived projection over repo/ingest data
                artifact_cid=cid,
                snippet=f"{n.get('type','')}: {label}"[:200],
                ts=None,
                trust="deterministic",  # graph is a deterministic derived projection
            ))
        return hits
    return _adapter


def default_adapters() -> dict[str, Adapter]:
    """Wire the real local projections, each degrading to [] when its store is absent."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent
    return {
        "transcript": transcript_adapter(repo / "store" / "daemon" / "daemon-events.db"),
        "graph": graph_adapter(repo / "store" / "entity_graph"),  # per-tenant: <dir>/<tenant>.db
    }
