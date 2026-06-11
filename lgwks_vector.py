"""lgwks_vector — vector-space + cid contract (lgwks.vector.record.v1).

I1 of the INGESTION-PLAN: the spine every other ingestion packet reads and writes.
Replaces the lossy JSON-text vector storage (gap G-11) with:
  - binary float32 BLOB (not JSON text)
  - stored norm ‖e‖ for audit (ê = e/‖e‖₂ guaranteed at write)
  - blake2b-based cid for dedup + idempotency
  - space_id for cross-space guard (raises, never silently compares)

Authority: spec/second-harness/INGESTION-PLAN.md §I1
Schema id: lgwks.vector.record.v1
"""

from __future__ import annotations

import math
import sqlite3
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# axiom/ lives at the repo root alongside this file; insert root so the
# package resolves whether this module is imported or run directly.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from axiom.cid import compute_cid, require_cid  # noqa: E402
from axiom.wire import LEN, encode as wire_encode  # noqa: E402

SCHEMA = "lgwks.vector.record.v1"

MODALITIES = frozenset(("text", "image", "video"))

VECTOR_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS vector_records (
    cid        TEXT PRIMARY KEY,
    modality   TEXT NOT NULL CHECK(modality IN ('text', 'image', 'video')),
    embedding  BLOB NOT NULL,
    norm       REAL NOT NULL,
    dim        INTEGER NOT NULL,
    space_id   TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    source_cid TEXT NOT NULL,
    schema     TEXT NOT NULL DEFAULT 'lgwks.vector.record.v1'
);
CREATE INDEX IF NOT EXISTS vr_space_tenant ON vector_records(space_id, tenant);
CREATE INDEX IF NOT EXISTS vr_source       ON vector_records(source_cid);
"""


class VectorError(ValueError):
    """Contract violation in the vector layer."""


class SpaceMismatchError(VectorError):
    """Cross-space comparison attempted without explicit override."""


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VectorRecord:
    """Immutable, fully validated lgwks.vector.record.v1 instance."""
    cid: str
    modality: str
    embedding: bytes    # packed big-endian float32[dim], L2-normalized
    norm: float         # ‖e‖₂ before normalization (audit anchor)
    dim: int
    space_id: str
    tenant: str
    source_cid: str

    def floats(self) -> list[float]:
        """Unpack the normalized embedding to a Python float list."""
        return list(struct.unpack(f">{self.dim}f", self.embedding))


# ---------------------------------------------------------------------------
# Encoding helpers (pure, no I/O)
# ---------------------------------------------------------------------------

def _pack_f32(floats: list[float]) -> bytes:
    return struct.pack(f">{len(floats)}f", *floats)


def _norm_l2(floats: list[float]) -> float:
    return math.sqrt(sum(x * x for x in floats))


def _normalize(floats: list[float]) -> tuple[list[float], float]:
    """Return (normalized_floats, original_norm). Raises on zero-vector."""
    n = _norm_l2(floats)
    if n < 1e-12:
        raise VectorError("cannot normalize zero vector")
    return [x / n for x in floats], n


def _canonical_bytes(
    source_cid: str,
    modality: str,
    space_id: str,
    embedding_bytes: bytes,
) -> bytes:
    """Deterministic canonical form used to compute the record's cid.

    Fields sorted by field_no via axiom.wire, so any permutation of callers
    produces byte-identical output — the dedup guarantee.
    """
    return wire_encode([
        (1, LEN, source_cid.encode()),
        (2, LEN, modality.encode()),
        (3, LEN, space_id.encode()),
        (4, LEN, embedding_bytes),
    ])


def encode_record(
    floats: list[float],
    *,
    modality: str,
    space_id: str,
    tenant: str,
    source_cid: str,
) -> VectorRecord:
    """Normalize floats → pack → cid → VectorRecord.

    Guarantees ‖ê‖ = 1 at the byte level. Identical inputs → identical cid.
    """
    if modality not in MODALITIES:
        raise VectorError(f"unknown modality {modality!r}; must be one of {sorted(MODALITIES)}")
    if not space_id:
        raise VectorError("space_id must not be empty")
    if not source_cid:
        raise VectorError("source_cid must not be empty")
    if not floats:
        raise VectorError("floats must not be empty")

    normalized, pre_norm = _normalize(floats)
    embedding_bytes = _pack_f32(normalized)
    canonical = _canonical_bytes(source_cid, modality, space_id, embedding_bytes)
    cid = compute_cid(canonical)

    return VectorRecord(
        cid=cid,
        modality=modality,
        embedding=embedding_bytes,
        norm=pre_norm,
        dim=len(normalized),
        space_id=space_id,
        tenant=tenant,
        source_cid=source_cid,
    )


def decode_record(row: tuple) -> VectorRecord:
    """Reconstruct a VectorRecord from a DB row and verify its cid.

    Row order: cid, modality, embedding, norm, dim, space_id, tenant, source_cid
    Raises axiom.cid.CidError on cid mismatch (tampered or corrupt store).
    """
    cid, modality, embedding, norm, dim, space_id, tenant, source_cid = row[:8]
    embedding = bytes(embedding)
    canonical = _canonical_bytes(source_cid, modality, space_id, embedding)
    require_cid(canonical, cid)
    return VectorRecord(
        cid=cid, modality=modality, embedding=embedding, norm=float(norm),
        dim=int(dim), space_id=space_id, tenant=tenant, source_cid=source_cid,
    )


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def cosine(a: VectorRecord, b: VectorRecord) -> float:
    """Dot product of two already-normalized records = cos θ ∈ [−1, 1].

    Raises SpaceMismatchError if space_ids differ — never silently compares
    embeddings from different spaces (the §I1 cross-space invariant).
    """
    require_same_space(a, b)
    af, bf = a.floats(), b.floats()
    if len(af) != len(bf):
        raise VectorError(f"dimension mismatch: {len(af)} vs {len(bf)}")
    # clamp: f32→f64 unpack can produce dot > 1.0 by a tiny epsilon on near-identical vectors
    raw = sum(x * y for x, y in zip(af, bf))
    return max(-1.0, min(1.0, raw))


def require_same_space(a: VectorRecord, b: VectorRecord) -> None:
    if a.space_id != b.space_id:
        raise SpaceMismatchError(
            f"cross-space compare: {a.space_id!r} vs {b.space_id!r} — "
            "use explicit space override if intentional"
        )


# ---------------------------------------------------------------------------
# SQLite store
# ---------------------------------------------------------------------------

def _connect(path: Path) -> sqlite3.Connection:
    """Open (or create) a vector store with WAL and the vector_records table."""
    try:
        import lgwks_sqlite  # type: ignore[import-untyped]
        conn = lgwks_sqlite.connect(path)
    except ImportError:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(VECTOR_RECORDS_DDL)
    conn.commit()
    return conn


def create_store(path: Path) -> sqlite3.Connection:
    """Open/create a vector store at path; return an open connection (caller closes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return _connect(path)


def upsert_record(conn: sqlite3.Connection, record: VectorRecord) -> bool:
    """Insert record; skip silently if cid already present (idempotent).

    Returns True if inserted, False if already present.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO vector_records
            (cid, modality, embedding, norm, dim, space_id, tenant, source_cid, schema)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            record.cid, record.modality, record.embedding,
            record.norm, record.dim, record.space_id,
            record.tenant, record.source_cid, SCHEMA,
        ),
    )
    return cur.rowcount == 1


def get_record(conn: sqlite3.Connection, cid: str) -> Optional[VectorRecord]:
    """Fetch and verify a record by cid. Returns None if not found."""
    row = conn.execute(
        "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid "
        "FROM vector_records WHERE cid = ?",
        (cid,),
    ).fetchone()
    if row is None:
        return None
    return decode_record(row)


def query_by_source(
    conn: sqlite3.Connection, source_cid: str, *, space_id: Optional[str] = None
) -> list[VectorRecord]:
    """Return all records for a source_cid, optionally filtered by space_id."""
    if space_id:
        rows = conn.execute(
            "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid "
            "FROM vector_records WHERE source_cid = ? AND space_id = ?",
            (source_cid, space_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid "
            "FROM vector_records WHERE source_cid = ?",
            (source_cid,),
        ).fetchall()
    return [decode_record(r) for r in rows]


# Sentinel value for world-tier rows (shared across all tenants).
WORLD_TENANT = "world"


def query_for_tenant(
    conn: sqlite3.Connection,
    tenant: str,
    *,
    space_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[VectorRecord]:
    """Return own-tenant rows UNION world rows, never another tenant's standard rows.

    This is the §1-INV basic read: a query for tenant T sees T's rows ⊕ world rows.
    The vr_space_tenant index covers (space_id, tenant) so both arms of the OR hit
    the index when space_id is supplied.

    //why OR not UNION: a single WHERE … OR … is one index scan per arm; SQLite's
    query planner uses the vr_space_tenant index for both. Correct isolation follows:
    rows where tenant != T and tenant != 'world' are never returned.
    """
    if space_id:
        sql = (
            "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid "
            "FROM vector_records "
            "WHERE (tenant = ? OR tenant = ?) AND space_id = ?"
        )
        params: tuple = (tenant, WORLD_TENANT, space_id)
    else:
        sql = (
            "SELECT cid, modality, embedding, norm, dim, space_id, tenant, source_cid "
            "FROM vector_records WHERE tenant = ? OR tenant = ?"
        )
        params = (tenant, WORLD_TENANT)
    if limit is not None:
        sql += " LIMIT ?"
        params = params + (limit,)
    rows = conn.execute(sql, params).fetchall()
    return [decode_record(r) for r in rows]


def store_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM vector_records").fetchone()[0]


# ---------------------------------------------------------------------------
# Migration: code_embeddings.db (gap G-11) → vector_records
# ---------------------------------------------------------------------------

def migrate_code_embeddings(
    src_path: Path,
    dst_path: Path,
    *,
    space_id: str = "qwen3-embedding:8b:d4096",
    tenant: str = "logicalworks-",
) -> dict:
    """Migrate ~/ingestion_results/code_embeddings.db (JSON-TEXT) to vector_records (BINARY).

    This is the I1 proof fixture: proves the contract round-trips real embeddings.
    src columns: id, repo, filepath, chunk_index, content, embedding (JSON text), content_hash
    """
    import json as _json

    src_conn = sqlite3.connect(str(src_path))
    dst_conn = create_store(dst_path)

    rows = src_conn.execute(
        "SELECT id, repo, content, embedding, content_hash FROM embeddings"
    ).fetchall()

    migrated = skipped_null = skipped_dim = 0
    for row_id, repo, content, emb_json, content_hash in rows:
        if not emb_json:
            skipped_null += 1
            continue

        try:
            floats = _json.loads(emb_json)
        except Exception:
            skipped_null += 1
            continue

        if not (64 <= len(floats) <= 4096):
            skipped_dim += 1
            continue

        # source_cid: content-address the original text so dedup survives re-runs
        src_bytes = (content or "").encode()
        if src_bytes:
            source_cid = compute_cid(src_bytes)
        else:
            source_cid = f"legacy:{content_hash or row_id}"

        record = encode_record(
            floats,
            modality="text",
            space_id=space_id,
            tenant=repo or tenant,
            source_cid=source_cid,
        )
        upsert_record(dst_conn, record)
        migrated += 1

    dst_conn.commit()
    total = store_count(dst_conn)
    dst_conn.close()
    src_conn.close()

    return {
        "schema": SCHEMA,
        "source": str(src_path),
        "destination": str(dst_path),
        "migrated": migrated,
        "skipped_null": skipped_null,
        "skipped_dim": skipped_dim,
        "store_total": total,
    }
