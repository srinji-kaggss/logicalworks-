"""lgwks_admission_store — durable cross-process admission queue (I8-hardening L4).

Persists the L3 admission queue + leases (lgwks_admission.TenantAdmissionGate) to a
WAL SQLite table so they survive process restart and coordinate ACROSS processes
(the daemon model). Backpressure not drop; crash-durable lease/reap.

No compute, no scoring, no model layer — durable queue/lease ONLY.

Authority: spec/second-harness/ARCH-two-db-multitenant.md (L4); issue #89.
Schema:    lgwks.admission_queue.v1   (family: harness)

Design:
  - Every op is capability-FIRST (require_scope(TENANT_RW)) — same contract as L3.
    A bad/missing cap raises CapabilityError before any row is read or written.
  - lease()/reap() carry the lease COUNT in the DB, so "fair leasing <= c" holds
    across processes (not just within one). Token-bucket *rate* limiting stays in
    lgwks_admission (per-process); only the queue + lease state are durable here.
  - Writes run in BEGIN IMMEDIATE transactions (autocommit off) so the
    check-then-act for enqueue/lease is atomic across concurrent processes; WAL +
    busy_timeout (lgwks_sqlite.connect) give readers concurrency and retry on BUSY.
  - `item` is an opaque handle/reference serialized as JSON — NOT raw content
    (the §1-INV scope fence: raw content stays absent or policy-gated upstream).
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

import lgwks_capability
import lgwks_workercap
from lgwks_admission import (
    Admitted,
    Rejected429,
    DEFAULT_Q_MAX,
    DEFAULT_ROLE_COUNT,
    _jitter,
)

SCHEMA_QUEUE = "lgwks.admission_queue.v1"

DEFAULT_LEASE_TTL: float = 30.0  # seconds a lease is held before reap reclaims it

# State machine: queued -> leased -> done; reap returns a stale lease to queued.
_QUEUED = "queued"
_LEASED = "leased"
_DONE = "done"
_ACTIVE_STATES = (_QUEUED, _LEASED)

_DDL = """
CREATE TABLE IF NOT EXISTS admission_queue (
    tenant         TEXT    NOT NULL,
    cid            TEXT    NOT NULL,
    item           TEXT,
    state          TEXT    NOT NULL DEFAULT 'queued',
    enqueued_at    REAL    NOT NULL,
    leased_at      REAL,
    lease_owner    TEXT,
    lease_deadline REAL,
    retry_count    INTEGER NOT NULL DEFAULT 0,
    schema         TEXT    NOT NULL DEFAULT 'lgwks.admission_queue.v1',
    PRIMARY KEY (tenant, cid)
);
CREATE INDEX IF NOT EXISTS idx_admission_fifo
    ON admission_queue (tenant, state, enqueued_at);
"""


def _ser(item: Any) -> str | None:
    return None if item is None else json.dumps(item, sort_keys=True, separators=(",", ":"))


def _deser(blob: str | None) -> Any:
    return None if blob is None else json.loads(blob)


class DurableAdmissionQueue:
    """Crash-durable, cross-process, capability-gated admission queue (L4).

    key is the HMAC capability key (REQUIRED — no keyless path, mirrors
    lgwks_capability.guard's D3). Every enqueue/lease/complete validates a
    CapabilityToken with TENANT_RW before touching rows.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        key: bytes,
        role_count: int = DEFAULT_ROLE_COUNT,
        q_max: int = DEFAULT_Q_MAX,
        lease_ttl: float = DEFAULT_LEASE_TTL,
        clock: Callable[[], float] = time.monotonic,
        rng: Any = None,
    ) -> None:
        if not key:
            raise ValueError("DurableAdmissionQueue requires a non-empty capability key")
        if q_max < 1:
            raise ValueError(f"q_max must be >= 1, got {q_max}")
        cap_info = lgwks_workercap.compute_worker_cap(role_count)
        self._key = key
        self._c = int(cap_info["computed_cap"])
        self._q_max = q_max
        self._lease_ttl = lease_ttl
        self._clock = clock
        self._rng = rng
        self.cap_info = cap_info
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()

    # -- connection ------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        try:
            import lgwks_sqlite  # type: ignore[import-untyped]
            conn = lgwks_sqlite.connect(self._path, check_same_thread=False)
        except ImportError:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_DDL)
        conn.commit()
        # autocommit off → we own BEGIN IMMEDIATE / COMMIT / ROLLBACK explicitly,
        # so the check-then-act in enqueue/lease is atomic across processes.
        conn.isolation_level = None
        return conn

    def close(self) -> None:
        self._conn.close()

    # -- capability gate -------------------------------------------------
    def _verified_tenant(self, token: lgwks_capability.CapabilityToken) -> str:
        # Raises CapabilityError on bad sig / empty / world / missing scope.
        return lgwks_capability.require_scope(
            token, lgwks_capability.TENANT_RW, lambda t: t, self._key
        )

    def _active_tenants(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(DISTINCT tenant) FROM admission_queue WHERE state IN (?,?)",
            _ACTIVE_STATES,
        ).fetchone()
        return max(1, int(row[0]))

    def fair_ceiling(self) -> int:
        """Per-tenant in-flight ceiling ⌈c / active_tenants⌉ (≥ 1), from live DB state."""
        return max(1, math.ceil(self._c / self._active_tenants(self._conn)))

    # -- enqueue (capability-FIRST, backpressure not drop) ---------------
    def enqueue(
        self,
        token: lgwks_capability.CapabilityToken,
        *,
        cid: str,
        item: Any = None,
        now: float | None = None,
    ) -> Admitted | Rejected429:
        """Durably enqueue (tenant, cid). Duplicate → idempotent Admitted; tenant
        queue at q_max → Rejected429(queue_full) (nothing dropped). CapabilityError
        on a bad/missing cap, before any row is touched."""
        tenant = self._verified_tenant(token)
        ts = now if now is not None else self._clock()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            dup = conn.execute(
                "SELECT 1 FROM admission_queue WHERE tenant=? AND cid=?", (tenant, cid)
            ).fetchone()
            if dup is not None:
                conn.execute("COMMIT")
                return Admitted(cid=cid)  # idempotent shed — one row
            depth = conn.execute(
                "SELECT COUNT(*) FROM admission_queue WHERE tenant=? AND state IN (?,?)",
                (tenant, _QUEUED, _LEASED),
            ).fetchone()[0]
            if depth >= self._q_max:
                conn.execute("COMMIT")
                return Rejected429(
                    cid=cid, reason="queue_full", retry_after=_jitter(1.0, rng=self._rng)
                )
            conn.execute(
                "INSERT INTO admission_queue "
                "(tenant, cid, item, state, enqueued_at, schema) "
                "VALUES (?,?,?,?,?,?)",
                (tenant, cid, _ser(item), _QUEUED, ts, SCHEMA_QUEUE),
            )
            conn.execute("COMMIT")
            return Admitted(cid=cid)
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- lease (fair leasing ≤ c, durable across processes) --------------
    def lease(
        self,
        token: lgwks_capability.CapabilityToken,
        *,
        owner: str,
        now: float | None = None,
        ttl: float | None = None,
    ) -> tuple[str, Any] | None:
        """Atomically claim the oldest queued row for the tenant IFF total leased < c
        AND tenant leased < ⌈c/active⌉. Returns (cid, item) or None when at capacity /
        nothing queued. The lease COUNT is the DB's → fairness holds across processes."""
        tenant = self._verified_tenant(token)
        ts = now if now is not None else self._clock()
        ttl = self._lease_ttl if ttl is None else ttl
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM admission_queue WHERE state=?", (_LEASED,)
            ).fetchone()[0]
            if total >= self._c:
                conn.execute("COMMIT")
                return None
            ceiling = max(1, math.ceil(self._c / self._active_tenants(conn)))
            tenant_leased = conn.execute(
                "SELECT COUNT(*) FROM admission_queue WHERE state=? AND tenant=?",
                (_LEASED, tenant),
            ).fetchone()[0]
            if tenant_leased >= ceiling:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT cid, item FROM admission_queue "
                "WHERE tenant=? AND state=? ORDER BY enqueued_at, cid LIMIT 1",
                (tenant, _QUEUED),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            cid, item = row
            conn.execute(
                "UPDATE admission_queue SET state=?, leased_at=?, lease_owner=?, "
                "lease_deadline=? WHERE tenant=? AND cid=?",
                (_LEASED, ts, owner, ts + ttl, tenant, cid),
            )
            conn.execute("COMMIT")
            return (cid, _deser(item))
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- complete (release the lease slot) -------------------------------
    def complete(
        self, token: lgwks_capability.CapabilityToken, *, cid: str
    ) -> bool:
        """Mark a leased row done (frees its lease slot). Returns True if a leased
        row was completed. Capability-gated; only the owning tenant can complete."""
        tenant = self._verified_tenant(token)
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE admission_queue SET state=? WHERE tenant=? AND cid=? AND state=?",
                (_DONE, tenant, cid, _LEASED),
            )
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- reap (crash-durability: reclaim stale leases) -------------------
    def reap(self, *, now: float | None = None) -> int:
        """Reclaim leases past their deadline → queued, retry_count++. A process that
        died holding a lease has its work reclaimed. Returns rows reclaimed. Admin/
        daemon op (no per-tenant cap — it scans all tenants)."""
        ts = now if now is not None else self._clock()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE admission_queue SET state=?, leased_at=NULL, lease_owner=NULL, "
                "lease_deadline=NULL, retry_count=retry_count+1 "
                "WHERE state=? AND lease_deadline < ?",
                (_QUEUED, _LEASED, ts),
            )
            n = cur.rowcount
            conn.execute("COMMIT")
            return n
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- introspection ---------------------------------------------------
    def depth(self, tenant: str) -> int:
        """Active (queued+leased) row count for a tenant."""
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM admission_queue WHERE tenant=? AND state IN (?,?)",
                (tenant, _QUEUED, _LEASED),
            ).fetchone()[0]
        )

    def leased_count(self, tenant: str | None = None) -> int:
        """Total leased rows, or leased rows for one tenant."""
        if tenant is None:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM admission_queue WHERE state=?", (_LEASED,)
                ).fetchone()[0]
            )
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM admission_queue WHERE state=? AND tenant=?",
                (_LEASED, tenant),
            ).fetchone()[0]
        )
