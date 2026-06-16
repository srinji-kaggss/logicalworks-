"""
lgwks_public — open-license public source layer.

Publicly reachable is not the same as reusable. This layer only emits records
from sources with an explicit open-license/open-reuse basis, and every record
carries that basis so later agents can filter or reject it deterministically.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

_UA = "lgwks-public/0.1 (+open-license research)"

SOURCES = {
    "openalex": {
        "kind": "scholarly-metadata",
        "license": "CC0",
        "basis": "OpenAlex data is CC0; works expose license/open-access metadata where available.",
        "url": "https://api.openalex.org/works",
    },
    "crossref": {
        "kind": "scholarly-metadata",
        "license": "CC0/public-domain metadata",
        "basis": "Crossref metadata is open for reuse; many facts are public-domain/CC0 metadata.",
        "url": "https://api.crossref.org/works",
    },
    "openverse": {
        "kind": "open-media",
        "license": "Creative Commons or public domain",
        "basis": "Openverse indexes openly licensed media and public-domain works; verify item license.",
        "url": "https://api.openverse.engineering/v1/images/",
    },
}


def _fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(2_000_000).decode("utf-8", errors="replace"))


def _openalex(query: str, limit: int) -> list[dict]:
    qs = urllib.parse.urlencode({"search": query, "per-page": limit, "filter": "is_oa:true"})
    data = _fetch_json(f"{SOURCES['openalex']['url']}?{qs}")
    rows = []
    for item in data.get("results", [])[:limit]:
        loc = item.get("best_oa_location") or {}
        rows.append({
            "source": "openalex",
            "title": item.get("display_name") or "",
            "url": loc.get("landing_page_url") or item.get("id") or "",
            "open_url": loc.get("pdf_url") or loc.get("landing_page_url") or "",
            "license": loc.get("license") or item.get("license") or "metadata:CC0",
            "license_url": loc.get("license_url") or "",
            "year": item.get("publication_year"),
            "basis": SOURCES["openalex"]["basis"],
        })
    return rows


def _crossref(query: str, limit: int) -> list[dict]:
    qs = urllib.parse.urlencode({"query": query, "rows": limit})
    data = _fetch_json(f"{SOURCES['crossref']['url']}?{qs}")
    rows = []
    for item in data.get("message", {}).get("items", [])[:limit]:
        licenses = item.get("license") or []
        first_license = licenses[0] if licenses else {}
        title = item.get("title") or [""]
        rows.append({
            "source": "crossref",
            "title": title[0] if title else "",
            "url": item.get("URL") or "",
            "open_url": item.get("URL") or "",
            "license": first_license.get("URL") or "metadata:CC0/public-domain",
            "license_url": first_license.get("URL") or "",
            "year": (item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[None]])[0][0],
            "basis": SOURCES["crossref"]["basis"],
        })
    return rows


def _openverse(query: str, limit: int) -> list[dict]:
    qs = urllib.parse.urlencode({"q": query, "page_size": limit})
    data = _fetch_json(f"{SOURCES['openverse']['url']}?{qs}")
    rows = []
    for item in data.get("results", [])[:limit]:
        rows.append({
            "source": "openverse",
            "title": item.get("title") or "",
            "url": item.get("foreign_landing_url") or item.get("url") or "",
            "open_url": item.get("url") or "",
            "license": item.get("license") or "",
            "license_url": item.get("license_url") or "",
            "creator": item.get("creator") or "",
            "basis": SOURCES["openverse"]["basis"],
        })
    return rows


_RUNNERS = {"openalex": _openalex, "crossref": _crossref, "openverse": _openverse}


def _relevance_score(query: str, record: dict) -> float:
    """Crude topical similarity: fraction of query terms appearing in title."""
    qterms = [t for t in query.lower().split() if len(t) > 2]
    if not qterms:
        return 0.0
    title = (record.get("title") or "").lower()
    hits = sum(1 for t in qterms if t in title)
    return round(hits / len(qterms), 2)


def _label_records(records: list[dict], query: str, floor: float = 0.25) -> list[dict]:
    """
    Relevance verifier: label every record honestly — no silent canon-as-relevance.
    //why DiD layer 1: explicit ranking on ALL records so absence-of-field is never
    interpreted as "proven relevant". Consumers switch on the value, not existence.
    //why DiD layer 2: floor is declared per-record so downstream gates can apply
    their own stricter thresholds without re-computing.
    """
    out: list[dict] = []
    for r in records:
        score = _relevance_score(query, r)
        if score < floor:
            # honest label: canon ranking, not proven relevance
            out.append({
                **r,
                "ranking": "citation-canon, not relevance",
                "relevance_score": score,
                "relevance_floor": floor,
            })
        else:
            out.append({
                **r,
                "ranking": "relevance-verified",
                "relevance_score": score,
                "relevance_floor": floor,
            })
    return out


def search_public(query: str, source: str = "all", limit: int = 5) -> dict:
    selected = list(_RUNNERS) if source == "all" else [source]
    records: list[dict] = []
    errors: dict[str, str] = {}
    for name in selected:
        fn = _RUNNERS.get(name)
        if not fn:
            errors[name] = "unknown source"
            continue
        try:
            # `limit` is per-source: each runner returns at most `limit` records,
            # so an "all" search yields up to limit×len(sources). No global cap —
            # truncating the union would silently drop whole sources.
            records.extend(fn(query, limit))
        except Exception as exc:
            errors[name] = type(exc).__name__

    # relevance gate: label honestly, never silent canon-as-relevance
    records = _label_records(records, query)
    return {
        "query": query,
        "source": source,
        "policy": "open-license-only; verify per-item license before redistribution",
        "sources": {name: SOURCES[name] for name in selected if name in SOURCES},
        "records": records,
        "errors": errors,
    }


def public_command(args: argparse.Namespace) -> int:
    payload = search_public(args.query, source=args.source, limit=args.limit)
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if payload["records"] or not payload["errors"] else 1


def add_parser(sub) -> None:
    p = sub.add_parser("public", help="search open-license public sources")
    p.add_argument("query")
    p.add_argument("--source", choices=["all", *sorted(SOURCES)], default="all")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=public_command)
