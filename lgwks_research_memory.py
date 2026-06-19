"""Read-only recall adapter for the unified cross-repo codebase brain.

The project memory chain in ``lgwks_memory`` is append-only per project. This
module is different: it treats the operator's multimodal ingestion database as a
compressed codebase map. Reads are best-effort and never mutate the source DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_lexicon as _lex
from lgwks_lexicon import STOP_EN as _STOP

DEFAULT_BRAIN_DB: Path | None = None


@dataclass(frozen=True)
class _Source:
    table: str
    source_sql: str
    type_sql: str
    text_sql: str


_SOURCES: tuple[_Source, ...] = (
    _Source("research", "filepath", "type", "dense_summary"),
    _Source("chronicle", "repo || ':' || source_id", "type", "dense_summary"),
    _Source("timeline", "repo || ':' || filepath", "event_type", "summary"),
    _Source("intelligence", "source", "type", "coalesce(content, '') || ' ' || coalesce(logic, '')"),
    _Source("perception", "repo || ':' || filepath", "type", "coalesce(snippet, '')"),
)


def _tokens(text: str) -> list[str]:
    return _lex.tokens(text, profile=_lex.TERM, min_len=3, stop=_STOP)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_db(db_path: str | Path | None = None) -> Path | None:
    if db_path:
        return Path(db_path)
    env_path = os.environ.get("LGWKS_AGENT_BRAIN_DB", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_BRAIN_DB


def _not_configured(schema: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": schema,
        "ok": False,
        "configured": False,
        "db": "",
        "error": "codebase brain db not configured; pass --db or set LGWKS_AGENT_BRAIN_DB",
        **extra,
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type='table' and name=?",
        (table,),
    ).fetchone()
    return row is not None


def _score(query_terms: list[str], source: str, text: str) -> float:
    haystack = f"{source}\n{text}".lower()
    if not haystack.strip():
        return 0.0
    unique_terms = list(dict.fromkeys(query_terms))
    score = 0.0
    for term in unique_terms:
        if not term:
            continue
        tf = haystack.count(term)
        if tf:
            score += 2.0 + min(tf, 8) * 0.35
        if term in source.lower():
            score += 1.5
    if len(unique_terms) > 1:
        phrase = " ".join(unique_terms[:6])
        if phrase and phrase in haystack:
            score += 3.0
    coverage = sum(1 for term in unique_terms if term in haystack)
    if unique_terms:
        score += coverage / len(unique_terms)
    return round(score, 4)


def _matched_terms(query_terms: list[str], source: str, text: str) -> list[str]:
    haystack = f"{source}\n{text}".lower()
    return [term for term in list(dict.fromkeys(query_terms)) if term in haystack]


def stats(db_path: str | Path | None = None) -> dict[str, Any]:
    path = _resolve_db(db_path)
    if path is None:
        return _not_configured("lgwks.brain.stats.v1", tables={})
    if not path.exists():
        return {
            "schema": "lgwks.brain.stats.v1",
            "ok": False,
            "configured": True,
            "db": str(path),
            "error": "codebase brain db not found",
            "tables": {},
        }
    out: dict[str, Any] = {
        "schema": "lgwks.brain.stats.v1",
        "ok": True,
        "configured": True,
        "db": str(path),
        "tables": {},
    }
    with _connect_readonly(path) as conn:
        for source in _SOURCES:
            if not _table_exists(conn, source.table):
                continue
            count = conn.execute(f"select count(*) from {source.table}").fetchone()[0]
            out["tables"][source.table] = count
    return out


def recall(
    query: str,
    *,
    db_path: str | Path | None = None,
    limit: int = 8,
    per_table_limit: int = 300,
    snippet_chars: int = 420,
) -> dict[str, Any]:
    """Return deterministic lexical recall from the unified codebase brain DB.

    This intentionally starts with transparent lexical scoring instead of opaque
    embedding assumptions because the DB may contain heterogeneous embedding
    formats from several ingestion passes.
    """
    path = _resolve_db(db_path)
    if path is None:
        return _not_configured("lgwks.brain.recall.v1", query=query, hits=[])
    if not path.exists():
        return {
            "schema": "lgwks.brain.recall.v1",
            "ok": False,
            "configured": True,
            "db": str(path),
            "query": query,
            "error": "codebase brain db not found",
            "hits": [],
        }

    terms = _tokens(query)
    if not terms:
        return {
            "schema": "lgwks.brain.recall.v1",
            "ok": True,
            "configured": True,
            "db": str(path),
            "query": query,
            "terms": [],
            "hits": [],
            "context_rule": "No query terms survived tokenization; do not infer prior context.",
        }

    rows: list[dict[str, Any]] = []
    with _connect_readonly(path) as conn:
        for source in _SOURCES:
            if not _table_exists(conn, source.table):
                continue
            where = " or ".join([f"lower({source.text_sql}) like ?" for _ in terms])
            params = [f"%{term.lower()}%" for term in terms]
            sql = (
                f"select id as id, {source.source_sql} as source, "
                f"{source.type_sql} as kind, {source.text_sql} as text "
                f"from {source.table} where {where} limit ?"
            )
            for row in conn.execute(sql, [*params, per_table_limit]).fetchall():
                text = str(row["text"] or "")
                src = str(row["source"] or "")
                score = _score(terms, src, text)
                if score <= 0:
                    continue
                matched = _matched_terms(terms, src, text)
                rows.append(
                    {
                        "table": source.table,
                        "id": row["id"],
                        "source": src,
                        "kind": row["kind"],
                        "score": score,
                        "matched_terms": matched,
                        "snippet": text[:snippet_chars],
                    }
                )

    rows.sort(key=lambda item: (item["score"], item["table"], str(item["id"])), reverse=True)
    hits = rows[: max(0, limit)]
    global_matched = sorted({term for hit in hits for term in hit.get("matched_terms", [])})
    unique_terms = list(dict.fromkeys(terms))
    return {
        "schema": "lgwks.brain.recall.v1",
        "ok": True,
        "configured": True,
        "db": str(path),
        "query": query,
        "terms": unique_terms,
        "matched_terms": global_matched,
        "missing_terms": [term for term in unique_terms if term not in global_matched],
        "hit_count": len(hits),
        "candidate_count": len(rows),
        "hits": hits,
        "context_rule": (
            "Use these hits as prior context only; verify fresh external facts and "
            "preserve source provenance."
        ),
    }


def _emit_text(payload: dict[str, Any]) -> None:
    if not payload.get("ok"):
        print(payload.get("error", "codebase brain recall failed"))
        return
    for hit in payload.get("hits", []):
        print(f"[{hit['score']:.2f}] {hit['table']} {hit['source']}")
        snippet = str(hit.get("snippet", "")).replace("\n", " ").strip()
        if snippet:
            print(f"  {snippet[:240]}")


def brain_command(args: argparse.Namespace) -> int:
    if args.brain_command == "stats":
        payload = stats(getattr(args, "db", None))
    else:
        query = " ".join(getattr(args, "query", []) or [])
        payload = recall(
            query,
            db_path=getattr(args, "db", None),
            limit=getattr(args, "limit", 8),
        )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _emit_text(payload)
    return 0 if payload.get("ok") else 2


def add_parser(sub) -> None:
    p = sub.add_parser("brain", help="read-only compressed codebase brain recall")
    brain = p.add_subparsers(dest="brain_command", required=True)

    recall_p = brain.add_parser("recall", help="recall prior context for a query")
    recall_p.add_argument("query", nargs="+")
    recall_p.add_argument("--db", default="", help="override unified codebase brain SQLite path")
    recall_p.add_argument("--limit", type=int, default=8)
    recall_p.add_argument("--json", action="store_true")
    recall_p.set_defaults(func=brain_command)

    stats_p = brain.add_parser("stats", help="show unified codebase brain table counts")
    stats_p.add_argument("--db", default="", help="override unified codebase brain SQLite path")
    stats_p.add_argument("--json", action="store_true")
    stats_p.set_defaults(func=brain_command)
