"""Tests for lgwks_daemon_store — durable daemon event log and work queue."""

from __future__ import annotations

import tempfile
import threading
import uuid
import unittest
from pathlib import Path

import lgwks_daemon_event as daemon_event
from lgwks_daemon_store import DaemonEventStore, PACKET_SCHEMA, WORK_ITEM_SCHEMA


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


def _item(*, tenant: str, session: str = "sess-1", agent: str = "claude", kind: str = "workflow", priority: int = 0) -> dict:
    return {
        "item_id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "session_id": session,
        "agent_id": agent,
        "kind": kind,
        "priority": priority,
        "payload": {"task": "test"},
    }


class TestWorkQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "daemon-events.db"
        self.store = DaemonEventStore(self.db)

    def tearDown(self):
        self.store.close()

    def test_enqueue_and_dequeue(self):
        item = _item(tenant="t1")
        self.assertTrue(self.store.enqueue(item))
        depth = self.store.queue_depth("t1")
        self.assertEqual(depth["queued"], 1)

        claimed = self.store.dequeue("t1", limit=1)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["schema"], WORK_ITEM_SCHEMA)
        self.assertEqual(claimed[0]["status"], "running")
        self.assertEqual(claimed[0]["item_id"], item["item_id"])

        depth = self.store.queue_depth("t1")
        self.assertEqual(depth["queued"], 0)
        self.assertEqual(depth["running"], 1)

    def test_enqueue_idempotent(self):
        item = _item(tenant="t1")
        self.assertTrue(self.store.enqueue(item))
        self.assertFalse(self.store.enqueue(item))
        self.assertEqual(self.store.queue_depth("t1")["queued"], 1)

    def test_complete_item(self):
        item = _item(tenant="t1")
        self.store.enqueue(item)
        self.store.dequeue("t1")
        self.store.complete_item(item["item_id"], result={"ok": True})
        depth = self.store.queue_depth("t1")
        self.assertEqual(depth["running"], 0)
        self.assertEqual(depth["done"], 1)

    def test_fail_item(self):
        item = _item(tenant="t1")
        self.store.enqueue(item)
        self.store.dequeue("t1")
        self.store.fail_item(item["item_id"], error="boom")
        depth = self.store.queue_depth("t1")
        self.assertEqual(depth["failed"], 1)

    def test_priority_ordering(self):
        lo = _item(tenant="t1", priority=0)
        hi = _item(tenant="t1", priority=10)
        self.store.enqueue(lo)
        self.store.enqueue(hi)
        claimed = self.store.dequeue("t1", limit=1)
        self.assertEqual(claimed[0]["item_id"], hi["item_id"])

    def test_tenant_isolation(self):
        self.store.enqueue(_item(tenant="t1"))
        self.store.enqueue(_item(tenant="t2"))
        self.assertEqual(self.store.queue_depth("t1")["queued"], 1)
        self.assertEqual(self.store.queue_depth("t2")["queued"], 1)
        claimed = self.store.dequeue("t1")
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["tenant_id"], "t1")
        self.assertEqual(self.store.queue_depth("t2")["queued"], 1)

    def test_concurrent_dequeue_no_double_claim(self):
        for _ in range(10):
            self.store.enqueue(_item(tenant="t1"))

        claimed_ids: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                store = DaemonEventStore(self.db)
                try:
                    items = store.dequeue("t1", limit=3)
                    claimed_ids.extend(item["item_id"] for item in items)
                finally:
                    store.close()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)), "no item double-claimed")
        self.assertLessEqual(len(claimed_ids), 10)

    def test_get_packet_deterministic(self):
        store = self.store
        ev = _event(tenant="t1", agent="claude", session="s1", ts="2026-06-12T01:00:00+00:00")
        store.append(ev)
        store.enqueue(_item(tenant="t1", session="s1"))

        p1 = store.get_packet(tenant_id="t1", session_id="s1", agent_id="claude")
        p2 = store.get_packet(tenant_id="t1", session_id="s1", agent_id="claude")
        self.assertEqual(p1["schema"], PACKET_SCHEMA)
        self.assertEqual(p1["event_count"], 1)
        self.assertIsNotNone(p1["session_head"])
        self.assertEqual(p1["queue"]["queued"], 1)
        self.assertEqual(p1, p2)
