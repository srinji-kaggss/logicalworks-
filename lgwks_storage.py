"""lgwks_storage — D4 Three-Syscall Storage Gate (ADR-068).

Governs the transition from "local file storage" to "State Fabric":
1. Causal Tape: The local, tenant-isolated source of truth (Source of Record).
2. Global Fact List: The deduplicated, content-addressed moat (Cloud-ready).

This module is "Remotable": DB 2 (Fact List) can be moved to Cloudflare R2/D1
by switching the 'transport' from 'local' to 'http'.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol, TypeVar

import lgwks_sqlite
import lgwks_substrate_io as io

T = TypeVar("T")

class StorageTransport(Protocol):
    """Protocol for DB 2 transport — can be implemented as Local (SQLite) or Remote (HTTP/R2)."""
    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]: ...
    def executemany(self, sql: str, param_list: list[tuple]) -> None: ...

class LocalSQLiteTransport:
    """Local-first implementation of the transport protocol."""
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _get_conn(self):
        return lgwks_sqlite.connect(self.path)

    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def executemany(self, sql: str, param_list: list[tuple]) -> None:
        with self._get_conn() as conn:
            conn.executemany(sql, param_list)

class CausalTape:
    """DB 1: The Local Source of Truth. Append-only journal of tenant facts.
    Grounded in ADR-068 §D1. Relational tables are mere projections of this tape."""
    
    def __init__(self, path: Path, tenant_id: str):
        self.path = path
        self.tenant_id = tenant_id
        self._init_db()

    def _init_db(self):
        with lgwks_sqlite.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tape (
                    entry_hash TEXT PRIMARY KEY,
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

    def append(self, fact_cid: str, capability_id: str, ciphertext: bytes | None = None, meta: dict | None = None) -> str:
        """Append a new fact to the causal chain."""
        # Get tail for chaining
        with lgwks_sqlite.connect(self.path) as conn:
            tail = conn.execute("SELECT entry_hash FROM tape WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 1", (self.tenant_id,)).fetchone()
            prev_hash = tail[0] if tail else "genesis"
            
            # Simple hash for entry identity (In production: BLAKE3(prev + cid + tenant))
            entry_id = io._sha(f"{prev_hash}|{fact_cid}|{self.tenant_id}")
            
            conn.execute(
                "INSERT INTO tape (entry_hash, prev_hash, tenant_id, capability_id, fact_cid, ciphertext, meta_json) VALUES (?,?,?,?,?,?,?)",
                (entry_id, prev_hash, self.tenant_id, capability_id, fact_cid, ciphertext, json.dumps(meta or {}))
            )
            return entry_id

class GlobalFactList:
    """DB 2: The Deduplication Moat. Content-addressed global fact registry.
    Designed to be moved to Cloudflare (R2/D1) — interacts only via Transport."""

    def __init__(self, transport: StorageTransport):
        self.transport = transport
        self._init_db()

    def _init_db(self):
        # We assume the transport points to a valid storage backend
        self.transport.execute("""
            CREATE TABLE IF NOT EXISTS global_facts (
                fact_hash TEXT PRIMARY KEY,
                fact_text TEXT NOT NULL,
                modality TEXT NOT NULL,
                seen_count INTEGER DEFAULT 1,
                last_seen REAL DEFAULT (strftime('%s', 'now')),
                importance_score REAL DEFAULT 0.0
            )
        """)

    def register_fact(self, fact_hash: str, text: str, modality: str, score: float = 0.0):
        """Register a fact in the global list. If it exists, increment seen_count.

        //why single UPSERT not read-then-write: the SELECT-then-INSERT/UPDATE form
        is a TOCTOU race (two ingests of the same fact can both read seen_count=N and
        both write N+1, losing a count) and costs two round-trips per fact on the hot
        ingestion path. SQLite's ON CONFLICT does the increment atomically; this is
        also the shape a remote D1/R2 backend would expose.
        """
        self.transport.execute(
            """
            INSERT INTO global_facts (fact_hash, fact_text, modality, importance_score)
            VALUES (?,?,?,?)
            ON CONFLICT(fact_hash) DO UPDATE SET
                seen_count = seen_count + 1,
                last_seen = strftime('%s', 'now')
            """,
            (fact_hash, text, modality, score),
        )

    def lookup(self, fact_hash: str) -> dict[str, Any] | None:
        """Lookup a global fact by its CID."""
        results = self.transport.execute("SELECT * FROM global_facts WHERE fact_hash = ?", (fact_hash,))
        return results[0] if results else None

class StorageGate:
    """The unified entry point for all storage operations."""
    
    def __init__(self, root_dir: Path, tenant_id: str = "default"):
        self.root = root_dir
        self.tenant_id = tenant_id
        
        # DB 1: Local Causal Tape
        self.tape = CausalTape(self.root / "causal_tape.db", tenant_id)
        
        # DB 2: Global Fact List (Configurable Transport)
        # To move to Cloudflare: replace LocalSQLiteTransport with RemoteHttpTransport
        db2_path = self.root / "global_fact_list.db"
        self.fact_list = GlobalFactList(LocalSQLiteTransport(db2_path))

    def ingest_fact(self, fact_cid: str, text: str, modality: str, capability: str, meta: dict | None = None):
        """Standard flow: Record to local tape + Register in global list."""
        # 1. Local Persistence (Source of Record)
        self.tape.append(fact_cid, capability, meta=meta)
        
        # 2. Global Deduplication (The Moat)
        self.fact_list.register_fact(fact_cid, text, modality)

def get_gate(project_name: str, tenant_id: str = "default") -> StorageGate:
    """Convenience helper to get a gate for a specific project/workspace."""
    from lgwks_substrate_config import RUN_ROOT
    workspace_dir = RUN_ROOT / io._slug(project_name)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return StorageGate(workspace_dir, tenant_id)
