"""lgwks_substrate_db — global fact-vector upserts.

The per-run relational index DB (`_build_index_db`) was removed: the State Fabric
gate's RelationalProjection (lgwks_storage.RelationalProjection.project_run) is the
single, cumulative, parity-tested relational store. The global fact-vector store
remains here pending its fold into the gate's world tier (tracked follow-up).

Defense-in-Depth:
- Layer 2 (business): use lgwks_sqlite.connect (retry, WAL, pragmas) not bare sqlite3.connect.
- Layer 3 (environment): fts5 virtual tables guarded behind IF NOT EXISTS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lgwks_sqlite
from lgwks_substrate_io import _json_cell


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
