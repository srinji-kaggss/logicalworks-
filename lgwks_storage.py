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
import time
from pathlib import Path
from typing import Any, Protocol

import lgwks_artifact_tokenized as artifact_mod
import lgwks_sqlite
import lgwks_substrate_io as io
import lgwks_tokenizer_registry as tok_reg
import lgwks_vector as vec_mod


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

class VectorFabric:
    """Projection #1: vector records (lgwks.vector.record.v1/v2).

    Wraps the lgwks_vector SQLite store. The gate uses this to persist embeddings
    that arrive alongside an artifact. tokenization_id and artifact_cid are stored
    as metadata columns (not part of the vector cid, so identical embeddings still
    dedup regardless of which tokenizer named them).
    """

    def __init__(self, path: Path):
        self.path = path
        self._conn = vec_mod.create_store(path)

    def upsert(self, record: vec_mod.VectorRecord) -> bool:
        return vec_mod.upsert_record(self._conn, record, admin=vec_mod.ADMIN)

    def query_by_source(self, source_cid: str, *, space_id: str | None = None) -> list[vec_mod.VectorRecord]:
        return vec_mod.query_by_source(self._conn, source_cid, space_id=space_id, admin=vec_mod.ADMIN)

    def query_by_artifact(self, artifact_cid: str) -> list[vec_mod.VectorRecord]:
        rows = self._conn.execute(
            "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid, "
            "tokenization_id, artifact_cid FROM vector_records WHERE artifact_cid = ?",
            (artifact_cid,),
        ).fetchall()
        return [vec_mod.decode_record(r) for r in rows]

    def close(self) -> None:
        self._conn.close()


class TokenIndex:
    """Projection #2: token → artifact posting lists per tokenizer.

    This is the inverted index that the old per-run FTS5 approximated. Each row
    records that tokenizer `tokenization_id` produced token `token` in artifact
    `artifact_cid` at position `position`. The index is rebuilt/reconciled by
    replaying the Causal Tape in the future; for now it is maintained eagerly.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS token_postings (
        tokenization_id TEXT NOT NULL,
        token           INTEGER NOT NULL,
        artifact_cid    TEXT NOT NULL,
        position        INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (tokenization_id, token, artifact_cid, position)
    );
    CREATE INDEX IF NOT EXISTS idx_postings_tokenizer_token ON token_postings(tokenization_id, token);
    CREATE INDEX IF NOT EXISTS idx_postings_artifact ON token_postings(artifact_cid);
    """

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(path, check_same_thread=False)
        self._conn.executescript(self._DDL)
        self._conn.commit()

    def index_tokens(self, tokenization_id: str, artifact_cid: str, token_stream: tuple[int, ...]) -> int:
        """Insert one posting per token occurrence. Returns count inserted."""
        if not token_stream:
            return 0
        rows = [
            (tokenization_id, int(token), artifact_cid, pos)
            for pos, token in enumerate(token_stream)
        ]
        self._conn.executemany(
            "INSERT OR IGNORE INTO token_postings VALUES (?,?,?,?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def query_token(self, tokenization_id: str, token: int) -> list[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT artifact_cid FROM token_postings "
            "WHERE tokenization_id = ? AND token = ? ORDER BY artifact_cid",
            (tokenization_id, int(token)),
        )
        return [r[0] for r in cur.fetchall()]

    def query_artifact_tokens(self, artifact_cid: str) -> list[tuple[str, int, int]]:
        """Return (tokenization_id, token, position) for an artifact."""
        cur = self._conn.execute(
            "SELECT tokenization_id, token, position FROM token_postings "
            "WHERE artifact_cid = ? ORDER BY tokenization_id, position",
            (artifact_cid,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


class GraphFabric:
    """Projection #3: entity graph seam.

    Currently a lightweight wrapper around lgwks_entity_graph.GraphDB. In Phase 2
    this will link graph nodes/edges back to artifact_cids and tokenization_ids.
    For Phase 1 it exposes the same upsert_chunk/upsert_node/upsert_edge API so
    callers can begin routing graph writes through the gate.
    """

    def __init__(self, db_path: Path):
        import lgwks_entity_graph as graph_mod

        self.db_path = db_path
        self._db = graph_mod.GraphDB(db_path)

    def upsert_chunk(self, chunk_id: str, doc_id: str, text: str, url: str = "", schema: str = "UNKNOWN", labels: list[str] | None = None) -> None:
        self._db.upsert_chunk(chunk_id, doc_id, text, url=url, schema=schema, labels=labels or [])

    def upsert_node(self, node_id: str, node_type: str, label: str, attrs: dict | None = None) -> None:
        self._db.upsert_node(node_id, node_type, label, attrs)

    def upsert_edge(self, src: str, dst: str, rel: str, attrs: dict | None = None) -> None:
        self._db.upsert_edge(src, dst, rel, attrs)

    def commit(self) -> None:
        self._db.commit()

    def close(self) -> None:
        self._db.close()


class RelationalProjection:
    """Projection #4: disposable per-tenant relational query surface.

    For Phase 1 this is a minimal seam: it creates the same sources/documents/
    chunks/facts/vectors/frontier tables that lgwks_substrate_db.py builds, but
    owned by the gate. In Phase 2/3 it will be rebuilt by replaying the tape.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY,
        source TEXT,
        title TEXT,
        discovered_by TEXT,
        depth INTEGER
    );
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        source_id TEXT,
        title TEXT,
        source TEXT,
        word_count INTEGER
    );
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT,
        source TEXT,
        url TEXT,
        text TEXT,
        stem_text TEXT,
        hash TEXT,
        fact_score REAL,
        chunk_kind TEXT,
        position INTEGER,
        tokenization_id TEXT,
        artifact_cid TEXT
    );
    CREATE TABLE IF NOT EXISTS facts (
        fact_id TEXT PRIMARY KEY,
        chunk_id TEXT,
        document_id TEXT,
        fact_text TEXT,
        fact_score REAL,
        chunk_kind TEXT,
        tokenization_id TEXT,
        artifact_cid TEXT
    );
    CREATE TABLE IF NOT EXISTS vectors (
        vector_id TEXT PRIMARY KEY,
        chunk_id TEXT,
        document_id TEXT,
        provider TEXT,
        is_semantic INTEGER,
        dims INTEGER,
        vector_text TEXT,
        vector_json TEXT,
        fact_score REAL,
        chunk_kind TEXT,
        tokenization_id TEXT,
        artifact_cid TEXT
    );
    CREATE TABLE IF NOT EXISTS frontier (
        url TEXT,
        depth INTEGER,
        status TEXT,
        reason TEXT,
        discovered_by TEXT,
        links_found INTEGER
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_id, text, stem_text, source, tokenize='porter unicode61');
    CREATE VIRTUAL TABLE IF NOT EXISTS fact_fts USING fts5(fact_id, fact_text, chunk_kind, tokenize='porter unicode61');
    """

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(path, check_same_thread=False)
        self._conn.executescript(self._DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class StorageGate:
    """The unified entry point for all storage operations."""

    def __init__(self, root_dir: Path, tenant_id: str = "default"):
        self.root = root_dir
        self.tenant_id = tenant_id
        self.root.mkdir(parents=True, exist_ok=True)

        # Tokenizer registry (shared across tenants; definitions are global).
        self.tokenizers = tok_reg.TokenizerRegistry(self.root)

        # DB 1: Local Causal Tape
        self.tape = CausalTape(self.root / "causal_tape.db", tenant_id)

        # DB 2: Global Fact List (configurable provider-agnostic port).
        db2_path = self.root / "global_fact_list.db"
        self._fact_port = LocalSQLiteFactListPort(db2_path)
        self.fact_list = GlobalFactList(self._fact_port)

        # Projections over the tape. In Phase 2 these will be rebuilt by replay;
        # for now they are maintained eagerly on ingest.
        self.vector_fabric = VectorFabric(self.root / "vector_records.db")
        self.token_index = TokenIndex(self.root / "token_index.db")
        self.graph_fabric = GraphFabric(self.root / "graph.db")
        self.relational = RelationalProjection(self.root / "relational.db")

    def ingest_artifact(
        self,
        artifact: artifact_mod.TokenizedArtifact,
        *,
        vector_record: vec_mod.VectorRecord | None = None,
        index_tokens: bool = True,
    ) -> str:
        """Ingest a canonical tokenized artifact into the State Fabric.

        1. Append to the tenant's Causal Tape (source of record).
        2. Register in the Global Fact List (content-addressed dedup).
        3. Optionally persist a linked vector record.
        4. Optionally index the token stream in TokenIndex.

        Returns the tape entry_hash.
        """
        # 1. Local Persistence (Source of Record)
        meta = {
            "artifact_cid": artifact.artifact_cid,
            "source": artifact.source,
            "run_id": artifact.run_id,
            "session_id": artifact.session_id,
            "modality": artifact.modality,
            "tokenization_id": artifact.tokenization_id,
            "payload_cid": artifact.payload_cid,
            "payload_meta": artifact.payload_meta,
        }
        entry_hash = self.tape.append(artifact.artifact_cid, artifact.capability_id, meta=meta)

        # 2. Global Deduplication (The Moat)
        # Derive a short human-readable text label from payload_meta when present.
        label = artifact.payload_meta.get("title") or artifact.payload_meta.get("text") or artifact.payload_cid
        self.fact_list.register_fact(artifact.artifact_cid, label, artifact.modality)

        # 3. Vector projection
        if vector_record is not None:
            self.vector_fabric.upsert(vector_record)

        # 4. Token index projection
        if index_tokens and artifact.token_stream:
            self.token_index.index_tokens(
                artifact.tokenization_id, artifact.artifact_cid, artifact.token_stream
            )

        return entry_hash

    def ingest_fact(self, fact_cid: str, text: str, modality: str, capability: str, meta: dict | None = None):
        """Backward-compatible fact ingestion (wraps ingest_artifact).

        Uses the default word_regex tokenizer so existing callers participate in
        the same fabric without changes. The `modality` parameter historically
        carried chunk_kind values (e.g. "rule"); when it is not a canonical
        artifact modality we store it as `chunk_kind` in payload_meta and use
        "text" as the storage modality.
        """
        tokenization_id = self.tokenizers.default_word_regex_id()
        token_stream: tuple[int, ...] = ()
        payload_meta = dict(meta or {})
        payload_meta.setdefault("text", text)

        # Preserve the historical chunk_kind label while keeping modality canonical.
        if modality not in artifact_mod.VALID_MODALITIES:
            payload_meta["chunk_kind"] = modality
            canonical_modality = "text"
        else:
            canonical_modality = modality

        artifact = artifact_mod.build_artifact(
            tenant_id=self.tenant_id,
            source="substrate",
            modality=canonical_modality,
            tokenization_id=tokenization_id,
            token_stream=token_stream,
            payload_cid=fact_cid,
            payload_meta=payload_meta,
            capability_id=capability,
            timestamp=time.time(),
            artifact_cid=fact_cid,
        )
        return self.ingest_artifact(artifact, index_tokens=False)

    def close(self) -> None:
        self.tape.close()
        self._fact_port.close()
        self.vector_fabric.close()
        self.token_index.close()
        self.graph_fabric.close()
        self.relational.close()

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
