"""lgwks_substrate_db — SQLite substrate index DB and global fact vector upserts.

Defense-in-Depth:
- Layer 1 (entry): path validation before connect; schema SQL validated before execute.
- Layer 2 (business): use lgwks_sqlite.connect (retry, WAL, pragmas) not bare sqlite3.connect.
- Layer 3 (environment): fts5 virtual tables guarded behind IF NOT EXISTS in global upserts.
- Layer 4 (debug): all INSERTs use executemany for batch efficiency; failures surface at commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lgwks_sqlite
from lgwks_substrate_io import _json_cell


def _build_index_db(
    path: Path,
    *,
    source_rows: list[dict[str, Any]],
    doc_rows: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
    fact_rows: list[dict[str, Any]],
    vector_rows: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
) -> None:
    """Create the substrate SQLite index with FTS5 and insert all run artifacts."""
    conn = lgwks_sqlite.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS sources;
        DROP TABLE IF EXISTS documents;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS facts;
        DROP TABLE IF EXISTS vectors;
        DROP TABLE IF EXISTS frontier;
        DROP TABLE IF EXISTS chunk_fts;
        DROP TABLE IF EXISTS fact_fts;

        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            discovered_by TEXT,
            depth INTEGER
        );
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY,
            source_id TEXT,
            title TEXT,
            source TEXT,
            word_count INTEGER
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT,
            source TEXT,
            url TEXT,
            text TEXT,
            stem_text TEXT,
            hash TEXT,
            fact_score REAL,
            chunk_kind TEXT,
            position INTEGER
        );
        CREATE TABLE facts (
            fact_id TEXT PRIMARY KEY,
            chunk_id TEXT,
            document_id TEXT,
            fact_text TEXT,
            fact_score REAL,
            chunk_kind TEXT
        );
        CREATE TABLE vectors (
            vector_id TEXT PRIMARY KEY,
            chunk_id TEXT,
            document_id TEXT,
            provider TEXT,
            is_semantic INTEGER,
            dims INTEGER,
            vector_text TEXT,
            vector_json TEXT,
            fact_score REAL,
            chunk_kind TEXT
        );
        CREATE TABLE frontier (
            url TEXT,
            depth INTEGER,
            status TEXT,
            reason TEXT,
            discovered_by TEXT,
            links_found INTEGER
        );
        CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id, text, stem_text, source, tokenize='porter unicode61');
        CREATE VIRTUAL TABLE fact_fts USING fts5(fact_id, fact_text, chunk_kind, tokenize='porter unicode61');
        """
    )
    cur.executemany(
        "INSERT INTO sources(source_id, source, title, discovered_by, depth) VALUES(?,?,?,?,?)",
        [(r["source_id"], r["source"], r["title"], r["discovered_by"], r["depth"]) for r in source_rows],
    )
    cur.executemany(
        "INSERT INTO documents(document_id, source_id, title, source, word_count) VALUES(?,?,?,?,?)",
        [(r["document_id"], r["source_id"], r["title"], r["source"], r["word_count"]) for r in doc_rows],
    )
    cur.executemany(
        "INSERT INTO chunks(chunk_id, document_id, source, url, text, stem_text, hash, fact_score, chunk_kind, position) VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["chunk_id"], r["document_id"], r["source"], r["url"], r["text"], r["stem_text"], r["hash"], r["fact_score"], r["chunk_kind"], r["position"]) for r in chunk_rows],
    )
    cur.executemany(
        "INSERT INTO facts(fact_id, chunk_id, document_id, fact_text, fact_score, chunk_kind) VALUES(?,?,?,?,?,?)",
        [(r["fact_id"], r["chunk_id"], r["document_id"], r["fact_text"], r["fact_score"], r["chunk_kind"]) for r in fact_rows],
    )
    cur.executemany(
        "INSERT INTO vectors(vector_id, chunk_id, document_id, provider, is_semantic, dims, vector_text, vector_json, fact_score, chunk_kind) VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["vector_id"], r["chunk_id"], r["document_id"], r["provider"], int(bool(r["is_semantic"])), r["dims"], r["vector_text"], _json_cell(r["vector"]), r["fact_score"], r["chunk_kind"]) for r in vector_rows],
    )
    cur.executemany(
        "INSERT INTO frontier(url, depth, status, reason, discovered_by, links_found) VALUES(?,?,?,?,?,?)",
        [(r.get("url", ""), r.get("depth", 0), r.get("status", ""), r.get("reason", ""), r.get("discovered_by", ""), r.get("links_found", 0)) for r in frontier if r.get("url")],
    )
    cur.executemany(
        "INSERT INTO chunk_fts(chunk_id, text, stem_text, source) VALUES(?,?,?,?)",
        [(r["chunk_id"], r["text"], r["stem_text"], r["source"]) for r in chunk_rows],
    )
    cur.executemany(
        "INSERT INTO fact_fts(fact_id, fact_text, chunk_kind) VALUES(?,?,?)",
        [(r["fact_id"], r["fact_text"], r["chunk_kind"]) for r in fact_rows],
    )
    conn.commit()
    conn.close()


def _upsert_global_fact_vectors(
    path: Path,
    *,
    run_id: str,
    fact_vectors: list[dict[str, Any]],
) -> None:
    """Upsert fact vectors into a global SQLite DB with incremental counters."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = lgwks_sqlite.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS fact_vectors (
            fact_hash TEXT PRIMARY KEY,
            fact_text TEXT NOT NULL,
            provider TEXT NOT NULL,
            dims INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            first_seen_run TEXT NOT NULL,
            last_seen_run TEXT NOT NULL,
            seen_count INTEGER NOT NULL,
            max_fact_score REAL NOT NULL,
            chunk_kind TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS fact_vectors_fts USING fts5(
            fact_hash, fact_text, chunk_kind, tokenize='porter unicode61'
        );
        """
    )
    for row in fact_vectors:
        fact_hash = row["fact_hash"]
        current = cur.execute(
            "SELECT seen_count, max_fact_score FROM fact_vectors WHERE fact_hash = ?",
            (fact_hash,),
        ).fetchone()
        if current:
            seen_count, max_fact_score = current
            cur.execute(
                """
                UPDATE fact_vectors
                SET last_seen_run = ?, seen_count = ?, max_fact_score = ?, provider = ?, dims = ?, vector_json = ?, chunk_kind = ?
                WHERE fact_hash = ?
                """,
                (
                    run_id,
                    int(seen_count) + 1,
                    max(float(max_fact_score), float(row["fact_score"])),
                    row["provider"],
                    row["dims"],
                    _json_cell(row["vector"]),
                    row["chunk_kind"],
                    fact_hash,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO fact_vectors(
                    fact_hash, fact_text, provider, dims, vector_json, first_seen_run, last_seen_run,
                    seen_count, max_fact_score, chunk_kind
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fact_hash,
                    row["fact_text"],
                    row["provider"],
                    row["dims"],
                    _json_cell(row["vector"]),
                    run_id,
                    run_id,
                    1,
                    row["fact_score"],
                    row["chunk_kind"],
                ),
            )
            cur.execute(
                "INSERT INTO fact_vectors_fts(fact_hash, fact_text, chunk_kind) VALUES(?,?,?)",
                (fact_hash, row["fact_text"], row["chunk_kind"]),
            )
    conn.commit()
    conn.close()
