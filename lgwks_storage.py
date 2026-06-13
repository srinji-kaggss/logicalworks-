"""lgwks_storage — D4 Three-Syscall Storage Gate (ADR-068).

Governs the transition from "local file storage" to "State Fabric":
1. Causal Tape: The local, tenant-isolated source of truth (Source of Record).
2. Global Fact List: the deduplicated, content-addressed moat.

DB 2 is provider-agnostic by contract: the gate depends on fact-list operations,
not a named cloud, framework, or wire protocol. A future remote port can satisfy
the same operation protocol without changing callers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

import lgwks_sqlite
import lgwks_substrate_io as io


class FactListPort(Protocol):
    """Provider-agnostic DB 2 port for content-addressed fact deduplication."""

    def init_global_facts(self) -> None: ...
    def register_fact(self, fact_hash: str, text: str, modality: str, score: float = 0.0) -> None: ...
    def lookup_fact(self, fact_hash: str) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


class LocalSQLiteFactListPort:
    """Local-first implementation of the fact-list port."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def init_global_facts(self) -> None:
        try:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_facts (
                    fact_hash TEXT PRIMARY KEY,
                    fact_text TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    seen_count INTEGER DEFAULT 1,
                    last_seen REAL DEFAULT (strftime('%s', 'now')),
                    importance_score REAL DEFAULT 0.0
                )
                """
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def register_fact(self, fact_hash: str, text: str, modality: str, score: float = 0.0) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO global_facts (fact_hash, fact_text, modality, importance_score)
                VALUES (?,?,?,?)
                ON CONFLICT(fact_hash) DO UPDATE SET
                    seen_count = seen_count + 1,
                    last_seen = strftime('%s', 'now')
                """,
                (fact_hash, text, modality, score),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def lookup_fact(self, fact_hash: str) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT * FROM global_facts WHERE fact_hash = ?", (fact_hash,))
        row = cur.fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> LocalSQLiteFactListPort:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class CausalTape:
    """DB 1: The Local Source of Truth. Append-only journal of tenant facts.
    Grounded in ADR-068 §D1. Relational tables are mere projections of this tape."""
    
    def __init__(self, path: Path, tenant_id: str):
        self.path = path
        self.tenant_id = tenant_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(self.path, check_same_thread=False)
        self._conn.isolation_level = None
        self._init_db()

    def _init_db(self):
        conn = self._conn
        conn.executescript("""
                CREATE TABLE IF NOT EXISTS tape (
                    entry_hash TEXT PRIMARY KEY,
                    sequence INTEGER,
                    prev_hash TEXT,
                    tenant_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    fact_cid TEXT NOT NULL,
                    ciphertext BLOB,
                    meta_json TEXT,
                    timestamp REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE INDEX IF NOT EXISTS idx_tape_tenant ON tape(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_tape_cid ON tape(fact_cid);
            """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tape)").fetchall()}
        if "sequence" not in columns:
            conn.execute("ALTER TABLE tape ADD COLUMN sequence INTEGER")
        self._backfill_sequences()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tape_tail ON tape(tenant_id, sequence DESC)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tape_tenant_sequence ON tape(tenant_id, sequence)")
        conn.commit()

    def _backfill_sequences(self) -> None:
        conn = self._conn
        rows = conn.execute(
            """
            SELECT rowid, tenant_id
            FROM tape
            WHERE sequence IS NULL
            ORDER BY tenant_id ASC, timestamp ASC, rowid ASC
            """
        ).fetchall()
        next_by_tenant: dict[str, int] = {}
        for tenant_id, max_seq in conn.execute(
            "SELECT tenant_id, COALESCE(MAX(sequence), 0) FROM tape WHERE sequence IS NOT NULL GROUP BY tenant_id"
        ).fetchall():
            next_by_tenant[str(tenant_id)] = int(max_seq)
        for rowid, tenant_id in rows:
            tenant = str(tenant_id)
            next_seq = next_by_tenant.get(tenant, 0) + 1
            next_by_tenant[tenant] = next_seq
            conn.execute("UPDATE tape SET sequence = ? WHERE rowid = ?", (next_seq, rowid))

    def append(self, fact_cid: str, capability_id: str, ciphertext: bytes | None = None, meta: dict | None = None) -> str:
        """Append a new fact to the causal chain."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            tail = conn.execute(
                """
                SELECT sequence, entry_hash
                FROM tape
                WHERE tenant_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (self.tenant_id,),
            ).fetchone()
            prev_sequence = int(tail[0]) if tail else 0
            prev_hash = tail[1] if tail else "genesis"
            sequence = prev_sequence + 1
            entry_id = io._sha(f"{self.tenant_id}|{sequence}|{prev_hash}|{fact_cid}")
            conn.execute(
                """
                INSERT INTO tape
                (entry_hash, sequence, prev_hash, tenant_id, capability_id, fact_cid, ciphertext, meta_json)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    entry_id,
                    sequence,
                    prev_hash,
                    self.tenant_id,
                    capability_id,
                    fact_cid,
                    ciphertext,
                    json.dumps(meta or {}, sort_keys=True),
                ),
            )
            conn.execute("COMMIT")
            return entry_id
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._conn.close()

class GlobalFactList:
    """DB 2: The Deduplication Moat. Content-addressed global fact registry.
    Interacts only through the fact-list port so the backend remains replaceable."""

    def __init__(self, port: FactListPort):
        self.port = port
        self._init_db()

    def _init_db(self):
        self.port.init_global_facts()

    def register_fact(self, fact_hash: str, text: str, modality: str, score: float = 0.0):
        """Register a fact in the global list. If it exists, increment seen_count.

        //why single UPSERT not read-then-write: the SELECT-then-INSERT/UPDATE form
        is a TOCTOU race (two ingests of the same fact can both read seen_count=N and
        both write N+1, losing a count) and costs two round-trips per fact on the hot
        ingestion path. The local port uses an atomic upsert; non-SQL ports must
        provide the same atomic "create or increment" operation.
        """
        self.port.register_fact(fact_hash, text, modality, score)

    def lookup(self, fact_hash: str) -> dict[str, Any] | None:
        """Lookup a global fact by its CID."""
        return self.port.lookup_fact(fact_hash)

class StorageGate:
    """The unified entry point for all storage operations."""
    
    def __init__(self, root_dir: Path, tenant_id: str = "default"):
        self.root = root_dir
        self.tenant_id = tenant_id
        self.root.mkdir(parents=True, exist_ok=True)
        
        # DB 1: Local Causal Tape
        self.tape = CausalTape(self.root / "causal_tape.db", tenant_id)
        
        # DB 2: Global Fact List (configurable provider-agnostic port).
        db2_path = self.root / "global_fact_list.db"
        self._fact_port = LocalSQLiteFactListPort(db2_path)
        self.fact_list = GlobalFactList(self._fact_port)

    def ingest_fact(self, fact_cid: str, text: str, modality: str, capability: str, meta: dict | None = None):
        """Standard flow: Record to local tape + Register in global list."""
        # 1. Local Persistence (Source of Record)
        self.tape.append(fact_cid, capability, meta=meta)
        
        # 2. Global Deduplication (The Moat)
        self.fact_list.register_fact(fact_cid, text, modality)

    def close(self) -> None:
        self.tape.close()
        self._fact_port.close()

    def __enter__(self) -> StorageGate:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

def get_gate(project_name: str, tenant_id: str = "default") -> StorageGate:
    """Convenience helper to get a gate for a specific project/workspace."""
    from lgwks_substrate_config import RUN_ROOT
    workspace_dir = RUN_ROOT / io._slug(project_name)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return StorageGate(workspace_dir, tenant_id)
