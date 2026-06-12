"""Tests for lgwks_daemon_store — durable daemon event log."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import lgwks_daemon_event as daemon_event
from lgwks_daemon_store import DaemonEventStore


def _event(*, tenant: str, agent: str, session: str, ts: str, kind: str = "tool_call") -> dict:
    return daemon_event.build_event(
        tenant_id=tenant,
        agent_id=agent,
        session_id=session,
        actor="agent",
        client=agent if agent in daemon_event.CLIENTS else "unknown",
        lane="telemetry",
        kind=kind,
        scope="agent_local",
        ts=ts,
        payload={"cid": f"{agent}-{session}-{ts}"},
    )


class TestDaemonEventStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "daemon-events.db"

    def test_append_and_roundtrip(self):
        store = DaemonEventStore(self.db)
        try:
            record = _event(tenant="tenant-a", agent="claude", session="sess-1", ts="2026-06-12T00:00:00+00:00")
            inserted = store.append(record)
            self.assertTrue(inserted)
            rows = store.list_events(tenant_id="tenant-a")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event_id"], record["event_id"])
        finally:
            store.close()

    def test_duplicate_event_id_is_idempotent(self):
        store = DaemonEventStore(self.db)
        try:
            record = _event(tenant="tenant-a", agent="claude", session="sess-1", ts="2026-06-12T00:00:00+00:00")
            self.assertTrue(store.append(record))
            self.assertFalse(store.append(record))
            heads = store.list_session_heads(tenant_id="tenant-a")
            self.assertEqual(heads[0]["event_count"], 1)
        finally:
            store.close()

    def test_session_heads_track_latest_event(self):
        store = DaemonEventStore(self.db)
        try:
            first = _event(tenant="tenant-a", agent="codex", session="sess-2", ts="2026-06-12T00:00:00+00:00")
            second = _event(
                tenant="tenant-a",
                agent="codex",
                session="sess-2",
                ts="2026-06-12T00:00:01+00:00",
                kind="workflow_event",
            )
            store.append(first)
            store.append(second)
            heads = store.list_session_heads(tenant_id="tenant-a")
            self.assertEqual(len(heads), 1)
            self.assertEqual(heads[0]["first_event_id"], first["event_id"])
            self.assertEqual(heads[0]["last_event_id"], second["event_id"])
            self.assertEqual(heads[0]["event_count"], 2)
            self.assertEqual(heads[0]["last_kind"], "workflow_event")
        finally:
            store.close()

    def test_tenant_filter_isolation(self):
        store = DaemonEventStore(self.db)
        try:
            store.append(_event(tenant="tenant-a", agent="claude", session="sess-1", ts="2026-06-12T00:00:00+00:00"))
            store.append(_event(tenant="tenant-b", agent="gemini", session="sess-2", ts="2026-06-12T00:00:01+00:00"))
            rows_a = store.list_events(tenant_id="tenant-a")
            rows_b = store.list_events(tenant_id="tenant-b")
            self.assertEqual(len(rows_a), 1)
            self.assertEqual(len(rows_b), 1)
            self.assertEqual(rows_a[0]["tenant_id"], "tenant-a")
            self.assertEqual(rows_b[0]["tenant_id"], "tenant-b")
        finally:
            store.close()

    def test_concurrent_appends_across_agents(self):
        errors: list[Exception] = []

        def worker(agent: str, index: int) -> None:
            try:
                store = DaemonEventStore(self.db)
                try:
                    record = _event(
                        tenant="tenant-a",
                        agent=agent,
                        session=f"sess-{index}",
                        ts=f"2026-06-12T00:00:{index:02d}+00:00",
                    )
                    store.append(record)
                finally:
                    store.close()
            except Exception as exc:  # pragma: no cover - exercised only on failure
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(agent, idx))
            for idx, agent in enumerate(("claude", "codex", "gemini"), start=1)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        store = DaemonEventStore(self.db)
        try:
            heads = store.list_session_heads(tenant_id="tenant-a")
            self.assertEqual(len(heads), 3)
            self.assertEqual(sum(head["event_count"] for head in heads), 3)
        finally:
            store.close()
