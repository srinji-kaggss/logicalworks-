"""lgwks_daemon_store — durable event log for the daemon referee runtime.

This is the first executable state surface behind `lgwks.daemon.event.v1`.
It gives the daemon one WAL-backed append/read store with idempotent event
ingest and session-head maintenance across concurrent agent workloads.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import lgwks_daemon_event
import lgwks_sqlite

EVENT_QUERY_SCHEMA = "lgwks.daemon.events.query.v0"
SESSION_QUERY_SCHEMA = "lgwks.daemon.sessions.query.v0"

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
    )
]


def _ser(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class DaemonEventStore:
    """WAL-backed daemon event store with idempotent append semantics."""

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
        rows = self._conn.execute(
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

    def list_session_heads(self, *, tenant_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
