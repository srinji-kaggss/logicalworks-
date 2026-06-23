"""lgwks_daemon_store — durable event log + work queue for the daemon referee runtime.

Provides:
- WAL-backed append/read event store with idempotent ingest and session-head maintenance.
- Work queue with atomic dequeue, priority ordering, and per-tenant isolation.
- Deterministic session packet projection (recent events + queue state + head).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_daemon_event
import lgwks_sqlite

EVENT_QUERY_SCHEMA = "lgwks.daemon.events.query.v0"
SESSION_QUERY_SCHEMA = "lgwks.daemon.sessions.query.v0"
WORK_ITEM_SCHEMA = "lgwks.daemon.work_item.v0"
QUEUE_SCHEMA = "lgwks.daemon.queue.v0"
PACKET_SCHEMA = "lgwks.context.packet.v1"  # #122: promoted from lgwks.daemon.packet.v0 (superseded)
# Locked section set (build-the-basement): every packet carries all of these keys,
# even when a section ships empty. Filling a stubbed section later is additive —
# no schema bump, no consumer refactor.
CONTEXT_PACKET_SECTIONS = (
    "session_head", "queue", "recent_events", "event_count",
    "active_task", "retrieval", "known_failures", "commitments",
    "constraints", "allowed_capabilities", "next_steps", "provenance",
)
WORKTREE_SCHEMA = "lgwks.daemon.worktree.v0"

@dataclass(frozen=True)
class WorkCapability:
    """The typed contract behind one daemon WORK_KIND — the single source of truth
    for 'what work the daemon can do'. This is a PULSE *operation schema*: the
    daemon WORK_KIND is a PULSE op, a context-packet next-step is a PULSE
    *affordance* (a valid state-dependent move), and the affordance set is the
    packet's next_steps. Hardened against the PULSE research package (#pulse-okf,
    2026-06-23): an affordance carries not just its form fields but its speech-act
    modes, policy (risk/confirmation), execution semantics (side-effect/
    reversibility/idempotency/retry-safety), declared pre/post state, and — the
    key one — a machine-readable REPAIR map so a blocked or failed move emits the
    NEXT LEGAL MOVE, never a dead error (PULSE P5).

    Fields:
      summary       one-line 'what this does', shown verbatim in the form.
      args_schema   {arg: {"type","required","help"}} — PULSE slots; the form fields.
      effect_class  read | network | write — coarse lane (mirrors the agent door).
      modes         PULSE speech-acts this op accepts: ask (query) / do (mutate).
      preconditions predicate names (= PULSE state.pre); ALL must hold to be ready.
      produces      state tokens this adds (= PULSE state.post; affordance chaining).
      fallbacks     ORDERED alt kinds (declared seam; real chains live in-capability).
      risk          low | medium | high — PULSE policy.
      requires_confirmation  PULSE policy: a human/explicit confirm gate.
      side_effect   none | reads | writes_state | external_message — PULSE semantics.
      reversible / idempotent / retry_safe  PULSE execution semantics; drive the
                    approval gate and the retry hint in a repair frame.
      repair        PULSE P5: {unmet_precondition -> next-legal-move frame string}.
                    Encodes the affordance-graph edge to traverse when blocked.
    """
    kind: str
    summary: str
    args_schema: dict[str, dict[str, Any]]
    effect_class: str
    modes: tuple[str, ...] = ("do",)
    preconditions: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    fallbacks: tuple[str, ...] = ()
    risk: str = "low"
    requires_confirmation: bool = False
    side_effect: str = "none"
    reversible: bool = True
    idempotent: bool = True
    retry_safe: bool = True
    repair: dict[str, str] = field(default_factory=dict)

    def approval(self) -> str:
        """Approval class the form advertises, derived from PULSE policy+semantics —
        not effect_class alone. high-risk OR irreversible external side-effect ⇒
        'force'; any confirmation/medium-risk/write ⇒ 'once'; otherwise 'none'.
        This tightens the gate: an op classed 'network' but irreversible (e.g. an
        external send) now demands confirmation instead of slipping through."""
        irreversible_send = (not self.reversible) and self.side_effect == "external_message"
        if self.risk == "high" or irreversible_send:
            return "force"
        if self.requires_confirmation or self.risk == "medium" or self.effect_class == "write":
            return "once"
        return "none"


# The canonical work-capability registry — PULSE operation schemas. Adding a kind
# here makes it appear in the smart form automatically (no keyword classifier).
WORK_REGISTRY: dict[str, WorkCapability] = {
    cap.kind: cap for cap in (
        WorkCapability(
            kind="research_run",
            summary="crawl a target into a complete research substrate (chunks + STEM facts + vectors + graph)",
            args_schema={
                "target": {"type": "string", "required": True, "help": "URL or path to research"},
                "project": {"type": "string", "required": False, "help": "slug (default: derived from target)"},
                "max_pages": {"type": "int", "required": False, "help": "crawl budget (default 12)"},
            },
            effect_class="network", modes=("do",),
            produces=("substrate_run",),
            risk="low", side_effect="writes_state",
            reversible=True, idempotent=True, retry_safe=True,
            repair={"network": "need human.login (auth wall) or retry with smaller max_pages"},
        ),
        WorkCapability(
            kind="ingest_file",
            summary="ingest one local file/dir into the substrate (no network fetch)",
            args_schema={
                "target": {"type": "string", "required": True, "help": "file or directory path"},
            },
            effect_class="network", modes=("do",),
            produces=("substrate_run",),
            risk="low", side_effect="writes_state",
            reversible=True, idempotent=True, retry_safe=True,
        ),
        WorkCapability(
            kind="index_run",
            summary="register a completed substrate run into long-lived shared daemon state",
            args_schema={
                "run_id": {"type": "string", "required": True, "help": "run to index"},
            },
            effect_class="read", modes=("do",),
            preconditions=("has_unindexed_run",),
            produces=("indexed_run",),
            risk="low", side_effect="writes_state",
            reversible=True, idempotent=True, retry_safe=True,
            repair={"has_unindexed_run": "do research_run (no unindexed run exists — produce one first)"},
        ),
        WorkCapability(
            kind="worktree_open",
            summary="create a daemon-refereed git worktree for this session",
            args_schema={},
            effect_class="write", modes=("do",),
            preconditions=("no_active_worktree",),
            produces=("worktree",),
            risk="medium", side_effect="writes_state",
            reversible=True, idempotent=False, retry_safe=False,
            repair={"no_active_worktree": "do worktree_close (a worktree is already active — close it first)"},
        ),
        WorkCapability(
            kind="worktree_close",
            summary="close this session's active worktree and reconverge its CRDT sidecar",
            args_schema={
                "worktree_id": {"type": "string", "required": True, "help": "worktree to close"},
            },
            effect_class="write", modes=("do",),
            preconditions=("has_active_worktree",),
            risk="medium", side_effect="writes_state",
            reversible=False, idempotent=True, retry_safe=True,
        ),
        WorkCapability(
            kind="workflow",
            summary="run a typed multi-phase workflow plan",
            args_schema={
                "plan": {"type": "object", "required": True, "help": "workflow plan"},
            },
            effect_class="write", modes=("do",),
            risk="medium", requires_confirmation=True, side_effect="writes_state",
            reversible=False, idempotent=False, retry_safe=False,
        ),
        WorkCapability(
            kind="custom",
            summary="generic escape-hatch work item (fail-closed: treated as high-risk write)",
            args_schema={
                "payload": {"type": "object", "required": False, "help": "free-form payload"},
            },
            effect_class="write", modes=("do",),
            risk="high", requires_confirmation=True, side_effect="writes_state",
            reversible=False, idempotent=False, retry_safe=False,
        ),
    )
}

# Derived: every consumer that validated against the string-set keeps working.
WORK_KINDS = frozenset(WORK_REGISTRY)
ITEM_STATUSES = frozenset({"queued", "running", "done", "failed"})
STATS_SCHEMA = "lgwks.daemon.stats.v0"


class QueueFullError(RuntimeError):
    """Raised when an enqueue is rejected by per-tenant admission control (backpressure)."""


from lgwks_clock import now_iso as _now  # one source of truth for timestamps

_MIGRATIONS = [
    (
        1,
        "daemon_event_store_v1",

        """
        CREATE TABLE IF NOT EXISTS daemon_events (
            event_id    TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            agent_id    TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            actor       TEXT NOT NULL,
            client      TEXT NOT NULL,
            lane        TEXT NOT NULL,
            kind        TEXT NOT NULL,
            scope       TEXT NOT NULL,
            ts          TEXT NOT NULL,
            refs_json   TEXT,
            payload_json TEXT NOT NULL,
            raw_json    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_daemon_events_tenant_ts
            ON daemon_events (tenant_id, ts DESC, event_id DESC);
        CREATE INDEX IF NOT EXISTS idx_daemon_events_session_ts
            ON daemon_events (tenant_id, session_id, ts DESC, event_id DESC);
        CREATE INDEX IF NOT EXISTS idx_daemon_events_agent_ts
            ON daemon_events (tenant_id, agent_id, ts DESC, event_id DESC);

        CREATE TABLE IF NOT EXISTS daemon_session_heads (
            tenant_id      TEXT NOT NULL,
            agent_id       TEXT NOT NULL,
            session_id     TEXT NOT NULL,
            first_event_id TEXT NOT NULL,
            last_event_id  TEXT NOT NULL,
            event_count    INTEGER NOT NULL,
            last_ts        TEXT NOT NULL,
            last_lane      TEXT NOT NULL,
            last_kind      TEXT NOT NULL,
            last_scope     TEXT NOT NULL,
            PRIMARY KEY (tenant_id, agent_id, session_id)
        );
        """,
    ),
    (
        2,
        "daemon_work_queue_v1",
        """
        CREATE TABLE IF NOT EXISTS daemon_work_queue (
            item_id      TEXT PRIMARY KEY,
            tenant_id    TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            agent_id     TEXT NOT NULL,
            kind         TEXT NOT NULL,
            priority     INTEGER NOT NULL DEFAULT 0,
            status       TEXT NOT NULL DEFAULT 'queued',
            payload_json TEXT NOT NULL,
            enqueued_at  TEXT NOT NULL,
            started_at   TEXT,
            done_at      TEXT,
            result_json  TEXT,
            error        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_daemon_queue_pop
            ON daemon_work_queue (tenant_id, status, priority DESC, enqueued_at ASC);
        CREATE INDEX IF NOT EXISTS idx_daemon_queue_session
            ON daemon_work_queue (tenant_id, session_id, status);
        """,
    ),
    (
        3,
        "daemon_runs_v1",
        """
        CREATE TABLE IF NOT EXISTS daemon_runs (
            run_id        TEXT PRIMARY KEY,
            tenant_id     TEXT NOT NULL,
            target        TEXT NOT NULL,
            run_dir       TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            indexed_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_daemon_runs_tenant
            ON daemon_runs (tenant_id, indexed_at DESC);
        """,
    ),
    (
        4,
        "daemon_worktrees_v1",
        """
        CREATE TABLE IF NOT EXISTS daemon_worktrees (
            worktree_id   TEXT PRIMARY KEY,
            tenant_id     TEXT NOT NULL,
            session_id    TEXT NOT NULL,
            agent_id      TEXT NOT NULL,
            repo_path     TEXT NOT NULL,
            worktree_path TEXT NOT NULL,
            branch        TEXT NOT NULL,
            base_sha      TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active',
            created_at    TEXT NOT NULL,
            closed_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_daemon_worktrees_tenant
            ON daemon_worktrees (tenant_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_daemon_worktrees_session
            ON daemon_worktrees (tenant_id, session_id, status);
        """,
    ),
    (
        5,
        "daemon_runs_export_v1",
        """
        ALTER TABLE daemon_runs ADD COLUMN exported_at TEXT;
        ALTER TABLE daemon_runs ADD COLUMN export_path TEXT;
        ALTER TABLE daemon_runs ADD COLUMN export_hash TEXT;
        """,
    ),
    (
        6,
        "daemon_work_queue_attempts_v1",
        # dequeue-count for dead-letter / poison-pill protection (#227 world-class G1)
        """
        ALTER TABLE daemon_work_queue ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
        """,
    ),
]


def _ser(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ── lgwks.context.packet.v1 section builders (#122) ──────────────────────────
# Each section is an independent, deterministic builder over one source.

def _active_task(events: list[dict[str, Any]], head: dict[str, Any] | None,
                 session_id: str, agent_id: str) -> dict[str, Any] | None:
    """Current task head — derived from the deterministic watermark event.

    Uses `events[0]` (the newest by the store's `ts DESC, event_id DESC` order)
    so `active_task.head_event_id` is a pure function of the scoped event set and
    matches `provenance.watermark_event_id` — never the append-recency that the
    raw session-head row records (which is ambiguous on equal timestamps). Falls
    back to the session-head row, then null."""
    if not events and not head:
        return None
    watermark = events[0] if events else None
    if watermark is not None:
        return {
            "session_id": session_id,
            "agent_id": agent_id,
            "head_event_id": watermark.get("event_id"),
            "last_kind": watermark.get("kind"),
            "last_ts": watermark.get("ts"),
        }
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "head_event_id": head.get("last_event_id") if head else None,
        "last_kind": head.get("last_kind") if head else None,
        "last_ts": head.get("last_ts") if head else None,
    }


def _known_failures(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recent failure/stuckness signals — a deterministic filter over #118 events.

    Selects events whose payload flags a failure (`test_failed`/`error`) — the
    same axes #121 triggers match on, surfaced into the briefing."""
    out = []
    for ev in events:
        payload = ev.get("payload") or {}
        if payload.get("test_failed") or payload.get("error"):
            out.append({
                "event_id": ev.get("event_id"),
                "kind": ev.get("kind"),
                "source": ev.get("source"),
                "ts": ev.get("ts"),
            })
    return out


def _derive_packet_state(events: list[dict[str, Any]]) -> dict[str, bool]:
    """Deterministic boolean state read off the scoped event slice — the inputs to
    capability preconditions. Best-effort and degrade-honest: a condition is only
    True when positively observed in the recent events, never assumed."""
    opens = closes = 0
    for ev in events:
        kind = ev.get("kind") or ""
        payload = ev.get("payload") or {}
        dk = payload.get("kind") or ""
        evt = payload.get("event") or ""
        if kind == "worktree_open" or dk == "worktree_open" or evt == "worktree_opened":
            opens += 1
        elif kind == "worktree_close" or dk == "worktree_close" or evt == "worktree_closed":
            closes += 1
    return {
        "has_active_worktree": opens > closes,
        # Runs are auto-indexed at dispatch (register_run follows build_run), so a
        # manual index step is offered only when an unindexed run is positively seen.
        "has_unindexed_run": False,
    }


# Precondition predicates over the derived state. A capability is "ready" only when
# ALL its predicates hold. Adding a precondition name here makes it available to the
# registry — one source of truth for what gates a next-step.
_CAP_PREDICATES = {
    "has_active_worktree": lambda s: s.get("has_active_worktree", False),
    "no_active_worktree": lambda s: not s.get("has_active_worktree", False),
    "has_unindexed_run": lambda s: s.get("has_unindexed_run", False),
}


def _eval_preconditions(cap: "WorkCapability", state: dict[str, bool]) -> tuple[bool, list[str]]:
    """Return (ready, unmet_predicate_names). Ready ⇔ every precondition holds."""
    unmet = [p for p in cap.preconditions if not _CAP_PREDICATES.get(p, lambda _s: True)(state)]
    return (not unmet), unmet


def next_steps(events: list[dict[str, Any]],
               allowed_capabilities: list[str] | None = None) -> list[dict[str, Any]]:
    """The smart form: the valid next actions, COMPUTED from the work registry ×
    current state — not a keyword guess.

    The full capability menu is returned (transparency for the reasoning tier), each
    annotated with its arg-schema (the form fields), whether its preconditions are
    met right now, why, and the effect/approval class so the consumer knows the gate.
    Ready steps sort first; ties break by kind, so the projection is deterministic.
    When ``allowed_capabilities`` is supplied (the #120 authorization seam) the menu
    is intersected with it; empty ⇒ no filter (advisory — execution still gates)."""
    state = _derive_packet_state(events)
    allow = set(allowed_capabilities or ())
    # Declaration order = curated priority (research_run first, the generic custom/
    # workflow escape-hatches last). Used as the deterministic secondary sort key so
    # the most useful step surfaces first instead of an alphabetical accident.
    order = {kind: i for i, kind in enumerate(WORK_REGISTRY)}
    steps: list[dict[str, Any]] = []
    for kind in WORK_REGISTRY:
        if allow and kind not in allow:
            continue
        cap = WORK_REGISTRY[kind]
        ready, unmet = _eval_preconditions(cap, state)
        # PULSE P5: a blocked affordance emits the NEXT LEGAL MOVE(s), never a dead
        # end. repair is keyed by the unmet precondition — the affordance-graph edge
        # to traverse (e.g. index_run blocked ⇒ "do research_run first").
        repair = [cap.repair[p] for p in unmet if p in cap.repair]
        steps.append({
            "kind": cap.kind,
            "mode": cap.modes[0],            # primary speech-act (PULSE: ask/do)
            "modes": list(cap.modes),
            "summary": cap.summary,
            "args_schema": cap.args_schema,
            "effect_class": cap.effect_class,
            "approval": cap.approval(),
            "risk": cap.risk,
            "requires_confirmation": cap.requires_confirmation,
            "semantics": {
                "side_effect": cap.side_effect,
                "reversible": cap.reversible,
                "idempotent": cap.idempotent,
                "retry_safe": cap.retry_safe,
            },
            "produces": list(cap.produces),
            "fallbacks": list(cap.fallbacks),
            "preconditions": list(cap.preconditions),
            "preconditions_met": ready,
            "blocked_by": unmet,
            "repair": repair,
            "why": ("ready: " + cap.summary) if ready else ("blocked: needs " + ", ".join(unmet)),
        })
    steps.sort(key=lambda s: (not s["preconditions_met"], order[s["kind"]]))
    return steps


def validate_context_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate a context packet carries the full locked section set. Returns it."""
    if not isinstance(packet, dict):
        raise ValueError("packet must be a dict")
    if packet.get("schema") != PACKET_SCHEMA:
        raise ValueError(f"schema must be {PACKET_SCHEMA}")
    missing = [s for s in CONTEXT_PACKET_SECTIONS if s not in packet]
    if missing:
        raise ValueError(f"context packet missing locked sections: {missing}")
    prov = packet.get("provenance")
    if not isinstance(prov, dict) or "watermark_event_id" not in prov:
        raise ValueError("provenance must be a dict with watermark_event_id")
    return packet


class DaemonEventStore:
    """WAL-backed daemon event store with idempotent append semantics."""

    # Per-tenant admission cap on ACTIVE work (queued + running). An unbounded
    # queue is a memory-exhaustion / DoS vector; world-class daemons apply
    # backpressure. Override per-instance for tests. (#227 world-class E1)
    MAX_QUEUE_DEPTH: int = 10_000

    # Max dequeue attempts before a work item is dead-lettered (status='failed').
    # Bounds the infinite-retry risk that recover_orphaned() otherwise creates
    # for a poison pill. Override per-instance for tests. (#227 world-class G1)
    MAX_ATTEMPTS: int = 5

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(self.path, check_same_thread=False)
        self._migrations = lgwks_sqlite.MigrationManager(self._conn)
        self._migrations.apply(_MIGRATIONS)
        self._conn.isolation_level = None

    def close(self) -> None:
        self._conn.close()

    def append(self, record: dict[str, Any]) -> bool:
        """Append a validated event. Returns False on duplicate event_id."""
        event = lgwks_daemon_event.validate_event(record)
        refs_json = _ser(event.get("refs"))
        payload_json = _ser(event["payload"])
        raw_json = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO daemon_events
                (event_id, tenant_id, agent_id, session_id, actor, client, lane, kind, scope, ts,
                 refs_json, payload_json, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["tenant_id"],
                    event["agent_id"],
                    event["session_id"],
                    event["actor"],
                    event["client"],
                    event["lane"],
                    event["kind"],
                    event["scope"],
                    event["ts"],
                    refs_json,
                    payload_json,
                    raw_json,
                ),
            )
            inserted = cur.rowcount == 1
            if inserted:
                self._touch_session_head(conn, event)
            conn.execute("COMMIT")
            return inserted
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _touch_session_head(self, conn: sqlite3.Connection, event: dict[str, Any]) -> None:
        row = conn.execute(
            """
            SELECT first_event_id, event_count
            FROM daemon_session_heads
            WHERE tenant_id=? AND agent_id=? AND session_id=?
            """,
            (event["tenant_id"], event["agent_id"], event["session_id"]),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO daemon_session_heads
                (tenant_id, agent_id, session_id, first_event_id, last_event_id, event_count,
                 last_ts, last_lane, last_kind, last_scope)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["tenant_id"],
                    event["agent_id"],
                    event["session_id"],
                    event["event_id"],
                    event["event_id"],
                    1,
                    event["ts"],
                    event["lane"],
                    event["kind"],
                    event["scope"],
                ),
            )
            return
        first_event_id, event_count = row
        conn.execute(
            """
            UPDATE daemon_session_heads
            SET first_event_id=?,
                last_event_id=?,
                event_count=?,
                last_ts=?,
                last_lane=?,
                last_kind=?,
                last_scope=?
            WHERE tenant_id=? AND agent_id=? AND session_id=?
            """,
            (
                first_event_id,
                event["event_id"],
                int(event_count) + 1,
                event["ts"],
                event["lane"],
                event["kind"],
                event["scope"],
                event["tenant_id"],
                event["agent_id"],
                event["session_id"],
            ),
        )

    def list_events(
        self,
        *,
        tenant_id: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        conn=None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [tenant_id]
        where = ["tenant_id=?"]
        if session_id is not None:
            where.append("session_id=?")
            params.append(session_id)
        if agent_id is not None:
            where.append("agent_id=?")
            params.append(agent_id)
        params.append(max(1, limit))
        rows = (conn or self._conn).execute(
            f"""
            SELECT raw_json
            FROM daemon_events
            WHERE {' AND '.join(where)}
            ORDER BY ts DESC, event_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_session_heads(self, *, tenant_id: str, conn=None) -> list[dict[str, Any]]:
        rows = (conn or self._conn).execute(
            """
            SELECT tenant_id, agent_id, session_id, first_event_id, last_event_id, event_count,
                   last_ts, last_lane, last_kind, last_scope
            FROM daemon_session_heads
            WHERE tenant_id=?
            ORDER BY last_ts DESC, agent_id, session_id
            """,
            (tenant_id,),
        ).fetchall()
        return [
            {
                "tenant_id": row[0],
                "agent_id": row[1],
                "session_id": row[2],
                "first_event_id": row[3],
                "last_event_id": row[4],
                "event_count": row[5],
                "last_ts": row[6],
                "last_lane": row[7],
                "last_kind": row[8],
                "last_scope": row[9],
            }
            for row in rows
        ]

    # ── Work queue ────────────────────────────────────────────────────────────

    def enqueue(self, item: dict[str, Any]) -> bool:
        """Idempotent enqueue. Returns False if item_id already exists."""
        item_id = str(item.get("item_id", "")).strip()
        tenant_id = str(item.get("tenant_id", "")).strip()
        session_id = str(item.get("session_id", "")).strip()
        agent_id = str(item.get("agent_id", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not all([item_id, tenant_id, session_id, agent_id, kind]):
            raise ValueError("item_id, tenant_id, session_id, agent_id, kind required")
        if kind not in WORK_KINDS:
            raise ValueError(f"kind must be one of {sorted(WORK_KINDS)}")
        priority = int(item.get("priority", 0))
        payload_json = json.dumps(item.get("payload", {}), sort_keys=True)
        enqueued_at = item.get("enqueued_at") or _now()

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Admission control: reject once active (queued+running) depth hits the
            # cap, so the queue can never grow without bound. Counted inside the
            # transaction to avoid a TOCTOU race with concurrent enqueuers.
            active = conn.execute(
                "SELECT COUNT(*) FROM daemon_work_queue "
                "WHERE tenant_id=? AND status IN ('queued','running')",
                (tenant_id,),
            ).fetchone()[0]
            if active >= self.MAX_QUEUE_DEPTH:
                conn.execute("ROLLBACK")
                raise QueueFullError(
                    f"queue full for tenant {tenant_id}: "
                    f"{active} active >= cap {self.MAX_QUEUE_DEPTH}"
                )
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO daemon_work_queue
                (item_id, tenant_id, session_id, agent_id, kind, priority,
                 status, payload_json, enqueued_at)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (item_id, tenant_id, session_id, agent_id, kind, priority,
                 payload_json, enqueued_at),
            )
            inserted = cur.rowcount == 1
            conn.execute("COMMIT")
            return inserted
        except QueueFullError:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def dequeue(self, tenant_id: str, *, limit: int = 1) -> list[dict[str, Any]]:
        """Atomically claim the next queued item(s). Only one caller wins per item."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                """
                SELECT item_id, session_id, agent_id, kind, priority, payload_json, enqueued_at
                FROM daemon_work_queue
                WHERE tenant_id=? AND status='queued'
                ORDER BY priority DESC, enqueued_at ASC
                LIMIT ?
                """,
                (tenant_id, max(1, limit)),
            ).fetchall()
            now = _now()
            items: list[dict[str, Any]] = []
            for row in rows:
                conn.execute(
                    "UPDATE daemon_work_queue "
                    "SET status='running', started_at=?, attempts=attempts+1 "
                    "WHERE item_id=?",
                    (now, row[0]),
                )
                items.append({
                    "schema": WORK_ITEM_SCHEMA,
                    "item_id": row[0],
                    "tenant_id": tenant_id,
                    "session_id": row[1],
                    "agent_id": row[2],
                    "kind": row[3],
                    "priority": row[4],
                    "payload": json.loads(row[5]),
                    "enqueued_at": row[6],
                    "started_at": now,
                    "status": "running",
                })
            conn.execute("COMMIT")
            return items
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def complete_item(self, item_id: str, *, result: dict[str, Any] | None = None) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE daemon_work_queue SET status='done', done_at=?, result_json=? WHERE item_id=?",
                (_now(), json.dumps(result or {}, sort_keys=True), item_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def fail_item(self, item_id: str, *, error: str) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE daemon_work_queue SET status='failed', done_at=?, error=? WHERE item_id=?",
                (_now(), error[:1024], item_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Read one work item's status + terminal payload, or None if unknown.

        The read side of the queue: a synchronous client (e.g. engine.dispatch_
        and_await) enqueues then polls this until status is terminal. Under WAL a
        fresh SELECT sees the daemon process's committed completion, so a separate
        connection can observe out-of-band execution finish.
        """
        row = self._conn.execute(
            "SELECT item_id, tenant_id, session_id, agent_id, kind, status, "
            "result_json, error FROM daemon_work_queue WHERE item_id=?",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "item_id": row[0], "tenant_id": row[1], "session_id": row[2],
            "agent_id": row[3], "kind": row[4], "status": row[5],
            "result": json.loads(row[6]) if row[6] else None,
            "error": row[7],
        }

    def queue_depth(self, tenant_id: str, conn=None) -> dict[str, Any]:
        rows = (conn or self._conn).execute(
            "SELECT status, COUNT(*) FROM daemon_work_queue WHERE tenant_id=? GROUP BY status",
            (tenant_id,),
        ).fetchall()
        counts: dict[str, int] = {s: 0 for s in ITEM_STATUSES}
        for status, count in rows:
            counts[status] = count
        return {
            "schema": QUEUE_SCHEMA,
            "tenant_id": tenant_id,
            "queued": counts["queued"],
            "running": counts["running"],
            "done": counts["done"],
            "failed": counts["failed"],
            "total": sum(counts.values()),
        }

    def stats(self, tenant_id: str) -> dict[str, Any]:
        """Unified per-tenant counters snapshot (`lgwks.daemon.stats.v0`).

        One structured view across events + work queue (+ runs when present),
        for observability — the metrics surface a world-class daemon exposes
        rather than forcing N separate calls. (#227 world-class D3)
        """
        conn = self._conn
        qd = self.queue_depth(tenant_id, conn)
        events = conn.execute(
            "SELECT COUNT(*) FROM daemon_events WHERE tenant_id=?", (tenant_id,)
        ).fetchone()[0]
        try:
            runs = conn.execute(
                "SELECT COUNT(*) FROM daemon_runs WHERE tenant_id=?", (tenant_id,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            runs = 0
        return {
            "schema": STATS_SCHEMA,
            "tenant_id": tenant_id,
            "events": events,
            "queued": qd["queued"],
            "running": qd["running"],
            "done": qd["done"],
            "failed": qd["failed"],
            "queue_total": qd["total"],
            "runs": runs,
        }

    def recover_orphaned(self, tenant_id: str, *, older_than_s: float = 300.0) -> int:
        """Requeue work items stuck in 'running' past a lease window.

        If a daemon dies mid-job, its claimed items would otherwise sit in
        'running' forever (silently orphaned). This reclaims any whose
        ``started_at`` is older than ``older_than_s`` back to 'queued' so a
        live daemon picks them up. Returns the count recovered.
        Called on startup and periodically. (#227 world-class F1)
        """
        import datetime as _dt

        now_dt = _dt.datetime.fromisoformat(_now())
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                "SELECT item_id, started_at, attempts FROM daemon_work_queue "
                "WHERE tenant_id=? AND status='running'",
                (tenant_id,),
            ).fetchall()
            recovered = 0
            for item_id, started_at, attempts in rows:
                try:
                    started_dt = _dt.datetime.fromisoformat(started_at) if started_at else now_dt
                except (ValueError, TypeError):
                    started_dt = now_dt
                age = (now_dt - started_dt).total_seconds()
                if age < older_than_s:
                    continue
                if (attempts or 0) >= self.MAX_ATTEMPTS:
                    # Poison pill: dead-letter instead of requeueing forever.
                    conn.execute(
                        "UPDATE daemon_work_queue "
                        "SET status='failed', done_at=?, error='max_attempts_exceeded' "
                        "WHERE item_id=?",
                        (_now(), item_id),
                    )
                else:
                    conn.execute(
                        "UPDATE daemon_work_queue SET status='queued', started_at=NULL "
                        "WHERE item_id=?",
                        (item_id,),
                    )
                    recovered += 1
            conn.execute("COMMIT")
            return recovered
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_packet(
        self,
        *,
        tenant_id: str,
        session_id: str,
        agent_id: str,
        event_limit: int = 20,
        retrieval_provider=None,
        capability_provider=None,
    ) -> dict[str, Any]:
        """Deterministic context packet (`lgwks.context.packet.v1`, #122).

        The one canonical daemon briefing read by every agent and the human
        cockpit — a derived projection, reproducible from {event log @ watermark,
        stores @ watermark} with no hidden mutation. The v0 core (session_head,
        queue, recent_events, event_count) is preserved; the v1 enrichment
        sections are each an independent builder over one source. Sections that
        depend on other contracts degrade to empty-but-shaped when no provider is
        supplied (#124 retrieval, #120 allowed_capabilities), keeping the packet
        valid and deterministic under partial availability.
        """
        # Hardening (#154 M8): the three core reads (events, session heads, queue
        # depth) must reflect ONE consistent point-in-time, or a writer committing
        # mid-build yields a briefing that mixes pre-/post-commit state. We take a
        # dedicated read connection and wrap the reads in a single deferred read
        # transaction: under WAL the first SELECT pins a snapshot the rest share,
        # without blocking writers. A snapshot connection (not self._conn) avoids a
        # "transaction within a transaction" clash with concurrent BEGIN IMMEDIATE
        # writers on the shared connection.
        snap = lgwks_sqlite.connect(self.path, check_same_thread=False)
        snap.isolation_level = None
        try:
            snap.execute("BEGIN")
            events = self.list_events(
                tenant_id=tenant_id, session_id=session_id, agent_id=agent_id,
                limit=event_limit, conn=snap,
            )
            heads = self.list_session_heads(tenant_id=tenant_id, conn=snap)
            depth = self.queue_depth(tenant_id, conn=snap)
            snap.execute("COMMIT")
        finally:
            snap.close()
        head = next(
            (h for h in heads if h["session_id"] == session_id and h["agent_id"] == agent_id),
            None,
        )

        # #124 retrieval (graph/vector hits) — provider-fed, empty when absent.
        # Pass a COPY of events: a provider must not be able to mutate the packet's
        # own event slice (determinism + integrity of recent_events/event_count).
        retrieval = list(retrieval_provider(tenant_id, session_id, list(events))) if retrieval_provider else []
        # #120 verbs the session is authorised for — provider-fed, empty when absent.
        allowed_capabilities = list(capability_provider(tenant_id, agent_id)) if capability_provider else []

        return {
            "schema": PACKET_SCHEMA,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "session_head": head,
            "queue": depth,
            "recent_events": events,
            "event_count": len(events),
            "active_task": _active_task(events, head, session_id, agent_id),
            "retrieval": retrieval,
            "known_failures": _known_failures(events),
            "commitments": [],   # transcript-cortex sourced; stubbed-but-shaped (#122 seam)
            "constraints": [],   # active governance/AUP constraints; stubbed-but-shaped (#122 seam)
            "allowed_capabilities": allowed_capabilities,
            # The smart form: valid next actions computed from the work registry ×
            # state. This is what guides the agent through the workflow — replaces
            # the keyword classifier in the agent front door (#research-dogfood).
            "next_steps": next_steps(events, allowed_capabilities),
            "provenance": {
                "watermark_event_id": events[0]["event_id"] if events else None,
                "store_versions": {},
            },
        }


    # ── Run registry ──────────────────────────────────────────────────────────

    def register_run(self, tenant_id: str, manifest: dict[str, Any]) -> bool:
        """Index a completed substrate run. Idempotent by run_id."""
        run_id = str(manifest.get("run_id", "")).strip()
        target = str(manifest.get("target", manifest.get("source", ""))).strip()
        run_dir = str((manifest.get("artifacts") or {}).get("root", "")).strip()
        if not all([run_id, target, run_dir]):
            raise ValueError("manifest missing run_id, target, or artifacts.root")
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO daemon_runs
                (run_id, tenant_id, target, run_dir, manifest_json, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, tenant_id, target, run_dir,
                 json.dumps(manifest, sort_keys=True), _now()),
            )
            inserted = cur.rowcount == 1
            conn.execute("COMMIT")
            return inserted
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def list_runs(self, tenant_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT run_id, target, run_dir, indexed_at
            FROM daemon_runs WHERE tenant_id=?
            ORDER BY indexed_at DESC, rowid DESC LIMIT ?
            """,
            (tenant_id, max(1, limit)),
        ).fetchall()
        return [
            {"run_id": r[0], "target": r[1], "run_dir": r[2], "indexed_at": r[3]}
            for r in rows
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the full registered manifest for a run, or None if not found."""
        row = self._conn.execute(
            "SELECT manifest_json FROM daemon_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, ValueError):
            return None


    def mark_run_exported(
        self, run_id: str, *, export_path: str, export_hash: str
    ) -> None:
        """Record a verified export for a research run."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE daemon_runs SET exported_at=?, export_path=?, export_hash=? WHERE run_id=?",
                (_now(), export_path, export_hash, run_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_run_export_state(self, run_id: str) -> dict[str, Any] | None:
        """Return export state fields for a run, or None if run not found."""
        row = self._conn.execute(
            "SELECT run_id, tenant_id, run_dir, exported_at, export_path, export_hash "
            "FROM daemon_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0], "tenant_id": row[1], "run_dir": row[2],
            "exported_at": row[3], "export_path": row[4], "export_hash": row[5],
        }

    # ── Worktree registry ─────────────────────────────────────────────────────

    def open_worktree(
        self,
        *,
        worktree_id: str,
        tenant_id: str,
        session_id: str,
        agent_id: str,
        repo_path: str,
        worktree_path: str,
        branch: str,
        base_sha: str,
    ) -> bool:
        """Register a newly created worktree. Idempotent by worktree_id. Returns True if new."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO daemon_worktrees
                (worktree_id, tenant_id, session_id, agent_id, repo_path,
                 worktree_path, branch, base_sha, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (worktree_id, tenant_id, session_id, agent_id, repo_path,
                 worktree_path, branch, base_sha, _now()),
            )
            inserted = cur.rowcount == 1
            conn.execute("COMMIT")
            return inserted
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close_worktree(self, worktree_id: str, *, error: str | None = None) -> None:
        """Mark a worktree as closed or errored."""
        status = "error" if error else "closed"
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE daemon_worktrees SET status=?, closed_at=? WHERE worktree_id=?",
                (status, _now(), worktree_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_worktree(self, worktree_id: str) -> dict[str, Any] | None:
        """Return a single worktree record by id, or None."""
        row = self._conn.execute(
            """
            SELECT worktree_id, tenant_id, session_id, agent_id, repo_path, worktree_path,
                   branch, base_sha, status, created_at, closed_at
            FROM daemon_worktrees WHERE worktree_id=?
            """,
            (worktree_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "schema": WORKTREE_SCHEMA,
            "worktree_id": row[0], "tenant_id": row[1], "session_id": row[2],
            "agent_id": row[3], "repo_path": row[4], "worktree_path": row[5],
            "branch": row[6], "base_sha": row[7], "status": row[8],
            "created_at": row[9], "closed_at": row[10],
        }

    def list_worktrees(
        self,
        tenant_id: str,
        *,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        where = "tenant_id=?"
        params: list[Any] = [tenant_id]
        if active_only:
            where += " AND status='active'"
        rows = self._conn.execute(
            f"""
            SELECT worktree_id, session_id, agent_id, repo_path, worktree_path,
                   branch, base_sha, status, created_at, closed_at
            FROM daemon_worktrees WHERE {where}
            ORDER BY created_at DESC, rowid DESC LIMIT ?
            """,
            params + [max(1, limit)],
        ).fetchall()
        return [
            {
                "schema": WORKTREE_SCHEMA,
                "worktree_id": r[0],
                "tenant_id": tenant_id,
                "session_id": r[1],
                "agent_id": r[2],
                "repo_path": r[3],
                "worktree_path": r[4],
                "branch": r[5],
                "base_sha": r[6],
                "status": r[7],
                "created_at": r[8],
                "closed_at": r[9],
            }
            for r in rows
        ]


def emit_inbound_message(
    repo_root: Path,
    prompt: str,
    session_id: str = "",
    *,
    agent_id: str,
    client: str | None = None,
) -> None:
    """Canonical ingress adapter: record a human prompt as a `human_message` event.

    ONE implementation for every ingress hook (codex / gemini / claude / …). The
    per-agent copies had drifted — some omitted `source`/`trust` — so this is the
    single source of truth, parameterised only by `agent_id`/`client`. Fail-silent
    by law (INV-6): any error → no-op, never blocks the hook.
    """
    try:
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        event = lgwks_daemon_event.build_event(
            tenant_id=f"repo:{repo_root.name}",
            agent_id=agent_id,
            session_id=session_id or f"{agent_id}:{repo_root.name}",
            actor="human",
            client=client or agent_id,
            lane="ingress",
            kind="human_message",
            scope="agent_local",
            payload={"prompt_len": len(prompt), "prompt_head": prompt[:120]},
            source="text",
            trust="human_confirmed",
        )
        store = DaemonEventStore(db)
        try:
            store.append(event)
        finally:
            store.close()
    except Exception:
        pass


def _append_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        record = json.load(sys.stdin)
        inserted = store.append(record)
    finally:
        store.close()
    print(json.dumps({"ok": True, "inserted": inserted}, indent=2))
    return 0


def _events_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        rows = store.list_events(
            tenant_id=args.tenant_id,
            session_id=args.session_id,
            agent_id=args.agent_id,
            limit=args.limit,
        )
    finally:
        store.close()
    print(json.dumps({"schema": EVENT_QUERY_SCHEMA, "count": len(rows), "items": rows}, indent=2))
    return 0


def _sessions_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        rows = store.list_session_heads(tenant_id=args.tenant_id)
    finally:
        store.close()
    print(json.dumps({"schema": SESSION_QUERY_SCHEMA, "count": len(rows), "items": rows}, indent=2))
    return 0


def _enqueue_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        item = json.load(sys.stdin)
        inserted = store.enqueue(item)
    finally:
        store.close()
    print(json.dumps({"ok": True, "inserted": inserted}, indent=2))
    return 0


def _queue_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        depth = store.queue_depth(args.tenant_id)
    finally:
        store.close()
    print(json.dumps(depth, indent=2))
    return 0


def _packet_command(args: argparse.Namespace) -> int:
    store = DaemonEventStore(args.db)
    try:
        packet = store.get_packet(
            tenant_id=args.tenant_id,
            session_id=args.session_id,
            agent_id=args.agent_id,
            event_limit=args.limit,
        )
    finally:
        store.close()
    print(json.dumps(packet, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgwks_daemon_store")
    parser.add_argument("--db", default=".lgwks/daemon-events.db", help="sqlite path")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="append a daemon event from stdin JSON")
    append.set_defaults(func=_append_command)

    events = sub.add_parser("events", help="list stored daemon events")
    events.add_argument("--tenant-id", required=True)
    events.add_argument("--session-id")
    events.add_argument("--agent-id")
    events.add_argument("--limit", type=int, default=50)
    events.set_defaults(func=_events_command)

    sessions = sub.add_parser("sessions", help="list tenant session heads")
    sessions.add_argument("--tenant-id", required=True)
    sessions.set_defaults(func=_sessions_command)

    enqueue = sub.add_parser("enqueue", help="enqueue a work item from stdin JSON")
    enqueue.set_defaults(func=_enqueue_command)

    queue = sub.add_parser("queue", help="show queue depth for a tenant")
    queue.add_argument("--tenant-id", required=True)
    queue.set_defaults(func=_queue_command)

    packet = sub.add_parser("packet", help="fetch deterministic session packet")
    packet.add_argument("--tenant-id", required=True)
    packet.add_argument("--session-id", required=True)
    packet.add_argument("--agent-id", required=True)
    packet.add_argument("--limit", type=int, default=20)
    packet.set_defaults(func=_packet_command)

    runs = sub.add_parser("runs", help="list indexed research runs for a tenant")
    runs.add_argument("--tenant-id", required=True)
    runs.add_argument("--limit", type=int, default=20)
    runs.set_defaults(func=lambda a: (
        print(json.dumps({"runs": DaemonEventStore(a.db).list_runs(a.tenant_id, limit=a.limit)}, indent=2))
        or 0
    ))

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
