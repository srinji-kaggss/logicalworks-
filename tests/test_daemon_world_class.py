"""World-class-daemon falsification harness.

H0 (null hypothesis): "the lgwks daemon lacks world-class daemon properties."
This suite encodes the properties production-grade daemons (systemd, kubelet,
postgres, redis, consul) are expected to hold, as executable invariants. The
daemon *exceeds H0* — we reject the null — only when this entire suite is green.

Properties are grouped by category. Each test asserts ONE falsifiable invariant
against the real store / SessionDaemon (no mocks of the unit under test). Multi-
writer tests use SEPARATE store connections to the same DB file — the genuine
multi-process daemon scenario WAL is designed for.

Tracked by the daemon hardening loop. Do not weaken an assertion to go green;
fix the daemon (see CLAUDE.md no-gate-weakening).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import lgwks_daemon as daemon_mod
import lgwks_daemon_event as evt
from lgwks_daemon_store import DaemonEventStore


def _event(tenant: str, session: str, agent: str, *, kind: str = "human_message",
           text: str = "x") -> dict:
    return evt.build_event(
        tenant_id=tenant, agent_id=agent, session_id=session,
        actor="human", client="claude", lane="ingress", kind=kind,
        scope="agent_local", payload={"text": text},
    )


def _work_item(item_id: str, tenant: str, *, kind: str = "custom", priority: int = 0) -> dict:
    return {
        "item_id": item_id, "tenant_id": tenant, "session_id": "s1",
        "agent_id": "a1", "kind": kind, "priority": priority, "payload": {},
    }


class _StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "store" / "daemon" / "daemon-events.db"
        self.store = DaemonEventStore(self.db)
        self.tenant = "repo:wc-test"

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass


# ── Category A — Lifecycle & supervision ───────────────────────────────────
class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir(exist_ok=True)
        self.daemon = daemon_mod.SessionDaemon(self.tmp)

    def tearDown(self):
        try:
            self.daemon.stop()
        except Exception:
            pass

    def test_A1_idempotent_start_is_structured(self):
        """Starting an already-running daemon yields structured JSON, never a traceback."""
        import argparse
        import contextlib
        import io
        self.daemon.start()
        args = argparse.Namespace(repo=str(self.tmp), transcript_path=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = daemon_mod._start_command(args)
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "already_running")
        self.assertFalse(out["started"])

    def test_A2_clean_stop_is_structured(self):
        self.daemon.start()
        stopped = self.daemon.stop()
        self.assertEqual(stopped["status"], "stopped")

    def test_A3_restart_safe(self):
        self.daemon.start()
        self.daemon.stop()
        again = self.daemon.start()  # must not raise; lock must have been released
        self.assertTrue(again["alive"])

    def test_A4_stale_lock_reaped(self):
        """A lock file from a dead pid must be reaped, not block startup forever."""
        self.daemon.paths.root.mkdir(parents=True, exist_ok=True)
        daemon_mod._write_json(self.daemon.paths.lock, {"pid": 999999, "repo_root": str(self.tmp)})
        status = self.daemon.start()  # dead-pid lock should be reaped
        self.assertTrue(status["alive"])


# ── Category B — Durability & crash-safety ─────────────────────────────────
class TestDurability(_StoreCase):
    def test_B1_events_durable_across_reopen(self):
        """Committed events survive a process restart (reopen of the DB file)."""
        self.store.append(_event(self.tenant, "s1", "a1", text="durable"))
        self.store.close()
        reopened = DaemonEventStore(self.db)
        try:
            rows = reopened.list_events(tenant_id=self.tenant, limit=10)
        finally:
            reopened.close()
        self.assertTrue(any(r["payload"]["text"] == "durable" for r in rows))

    def test_B2_append_idempotent_on_duplicate(self):
        e = _event(self.tenant, "s1", "a1")
        self.assertTrue(self.store.append(e))
        self.assertFalse(self.store.append(e))  # same event_id -> no duplicate
        rows = self.store.list_events(tenant_id=self.tenant, limit=10)
        self.assertEqual(len([r for r in rows if r["event_id"] == e["event_id"]]), 1)

    def test_B3_wal_journal_mode(self):
        """WAL is required for safe concurrent multi-process read/write."""
        mode = sqlite3.connect(self.db).execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(str(mode).lower(), "wal")


# ── Category C — Concurrency & correctness ─────────────────────────────────
class TestConcurrency(_StoreCase):
    def test_C1_concurrent_appends_no_lost_updates(self):
        """N separate writers (own connections) append distinct events; none lost."""
        n = 40
        errors: list[Exception] = []

        def worker(i: int):
            try:
                s = DaemonEventStore(self.db)
                s.append(_event(self.tenant, "s1", f"a{i}", text=f"e{i}"))
                s.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        rows = self.store.list_events(tenant_id=self.tenant, limit=n + 10)
        self.assertEqual(len(rows), n)

    def test_C2_dequeue_no_double_claim(self):
        """Concurrent dequeuers must never claim the same item twice."""
        n = 30
        for i in range(n):
            self.store.enqueue(_work_item(f"item-{i}", self.tenant))
        claimed: list[str] = []
        lock = threading.Lock()

        def drainer():
            s = DaemonEventStore(self.db)
            try:
                while True:
                    got = s.dequeue(self.tenant, limit=1)
                    if not got:
                        break
                    with lock:
                        claimed.append(got[0]["item_id"])
            finally:
                s.close()

        threads = [threading.Thread(target=drainer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(claimed), n)
        self.assertEqual(len(set(claimed)), n)  # no item claimed twice

    def test_C3_packet_isolation_between_sessions(self):
        """INV-1: each session's packet reflects only its own events."""
        self.store.append(_event(self.tenant, "sA", "aA", text="for-A"))
        self.store.append(_event(self.tenant, "sB", "aB", text="for-B"))
        pa = self.store.get_packet(tenant_id=self.tenant, session_id="sA", agent_id="aA")
        texts = [e.get("payload", {}).get("text") for e in pa.get("recent_events", [])]
        self.assertIn("for-A", texts)
        self.assertNotIn("for-B", texts)

    def test_C4_tenant_isolation(self):
        """Events in tenant X are invisible to tenant Y (the #227 F1 invariant)."""
        self.store.append(_event("repo:X", "s1", "a1", text="x-only"))
        rows_y = self.store.list_events(tenant_id="repo:Y", limit=10)
        self.assertEqual(rows_y, [])


# ── Category D — Health & observability ────────────────────────────────────
class TestObservability(_StoreCase):
    def test_D1_queue_depth_observable(self):
        self.store.enqueue(_work_item("q1", self.tenant))
        depth = self.store.queue_depth(self.tenant)
        self.assertEqual(depth["queued"], 1)

    def test_D2_doctor_structured_and_binding_aware(self):
        d = daemon_mod.SessionDaemon(self.tmp)
        report = d.doctor()
        self.assertEqual(report["schema"], daemon_mod.DOCTOR_SCHEMA)
        names = {c["name"] for c in report["checks"]}
        self.assertIn("transcript_binding", names)  # #227 F3

    def test_D3_metrics_surface(self):
        """World-class daemons expose a unified metrics/stats snapshot.

        HARDENING TARGET: a single structured counters view across events +
        queue + runs, not just per-call queue_depth.
        """
        self.assertTrue(
            hasattr(self.store, "stats"),
            "store should expose a stats()/metrics snapshot",
        )
        snap = self.store.stats(self.tenant)  # type: ignore[attr-defined]
        for key in ("events", "queued", "running", "done", "failed"):
            self.assertIn(key, snap)


# ── Category E — Resource safety & backpressure ────────────────────────────
class TestBackpressure(_StoreCase):
    def test_E1_bounded_queue_admission_control(self):
        """An unbounded queue is a DoS / memory-exhaustion vector.

        HARDENING TARGET: enqueue must reject (backpressure) once a per-tenant
        max depth is exceeded, instead of growing without limit.
        """
        cap = getattr(DaemonEventStore, "MAX_QUEUE_DEPTH", None)
        self.assertIsNotNone(cap, "store must define a per-tenant MAX_QUEUE_DEPTH")
        # exercise the mechanism with a small instance cap (the class default is a
        # production number; the invariant under test is that the cap is enforced)
        cap = 25
        self.store.MAX_QUEUE_DEPTH = cap
        accepted = 0
        rejected = False
        for i in range(int(cap) + 5):  # type: ignore[arg-type]
            try:
                if self.store.enqueue(_work_item(f"bp-{i}", self.tenant)):
                    accepted += 1
            except Exception:
                rejected = True
                break
        self.assertTrue(rejected, "enqueue should apply backpressure past the cap")
        self.assertLessEqual(accepted, int(cap))  # type: ignore[arg-type]

    def test_E2_list_events_bounded_by_limit(self):
        for i in range(20):
            self.store.append(_event(self.tenant, "s1", f"a{i}"))
        rows = self.store.list_events(tenant_id=self.tenant, limit=5)
        self.assertLessEqual(len(rows), 5)


# ── Category F — Fault recovery ────────────────────────────────────────────
class TestFaultRecovery(_StoreCase):
    def test_F1_orphaned_running_work_recovered(self):
        """If a daemon dies mid-job, items stuck in 'running' must be reclaimable.

        HARDENING TARGET: a lease/visibility-timeout recovery that requeues
        stale 'running' items so work is never silently orphaned forever.
        """
        self.store.enqueue(_work_item("orphan-1", self.tenant))
        got = self.store.dequeue(self.tenant, limit=1)
        self.assertEqual(len(got), 1)  # now 'running'
        self.assertTrue(
            hasattr(self.store, "recover_orphaned"),
            "store should expose recover_orphaned() for stuck 'running' items",
        )
        # force the lease to look expired, then recover
        recovered = self.store.recover_orphaned(self.tenant, older_than_s=0)  # type: ignore[attr-defined]
        self.assertGreaterEqual(recovered, 1)
        again = self.store.dequeue(self.tenant, limit=1)
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0]["item_id"], "orphan-1")


# ── Category G — Advanced resilience & operability (iteration-2 bar-raise) ──
class TestAdvancedResilience(_StoreCase):
    def test_G1_poison_pill_dead_lettered(self):
        """A repeatedly-crashing item must dead-letter, not requeue forever.

        Recovery without an attempt cap is an infinite-retry vulnerability:
        a poison pill that crashes the worker every time would be reclaimed
        and re-dispatched endlessly. World-class queues cap attempts and move
        the item to a dead-letter (failed) state.
        """
        self.assertTrue(
            hasattr(DaemonEventStore, "MAX_ATTEMPTS"),
            "store must cap work-item attempts (dead-letter on poison pill)",
        )
        self.store.MAX_ATTEMPTS = 3  # type: ignore[attr-defined]
        self.store.enqueue(_work_item("poison", self.tenant))
        # simulate crash-recover cycles: each dequeue is one attempt, each
        # recover reclaims the orphaned 'running' item.
        for _ in range(int(self.store.MAX_ATTEMPTS) + 2):  # type: ignore[attr-defined]
            self.store.dequeue(self.tenant, limit=1)
            self.store.recover_orphaned(self.tenant, older_than_s=0)
        depth = self.store.queue_depth(self.tenant)
        self.assertEqual(depth["queued"], 0, "poison pill must not stay requeueable")
        self.assertEqual(depth["failed"], 1, "poison pill must be dead-lettered")


class TestOperability(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir(exist_ok=True)
        self.daemon = daemon_mod.SessionDaemon(self.tmp)

    def tearDown(self):
        try:
            self.daemon.stop()
        except Exception:
            pass

    def test_G3_readiness_distinct_from_liveness(self):
        """Readiness (can serve) must be reported separately from liveness (alive)."""
        self.assertTrue(hasattr(self.daemon, "readiness"), "daemon must expose readiness()")
        r = self.daemon.readiness()
        self.assertIn("ready", r)
        self.assertTrue(r["ready"], "store reachable + migrations applied => ready")
        # liveness is orthogonal: a not-yet-started daemon is ready but not alive
        self.assertFalse(self.daemon.status()["alive"])

    def test_G4_stale_heartbeat_detected(self):
        """A hung daemon (live pid, frozen heartbeat) must be flagged stale."""
        self.daemon.paths.root.mkdir(parents=True, exist_ok=True)
        daemon_mod._write_json(self.daemon.paths.state, {
            "pid": 999999, "heartbeat_at": "2000-01-01T00:00:00+00:00",
            "transcript_path": "", "status": "running",
        })
        daemon_mod._write_json(self.daemon.paths.lock, {"pid": 999999})
        status = self.daemon.status()
        self.assertIn("heartbeat_stale", status)
        self.assertTrue(status["heartbeat_stale"])


# ── Category H — Saturation probes (iteration-3 bar-raise) ─────────────────
# These raise the bar into areas often missing in homegrown daemons. If they
# pass WITHOUT new code, the daemon already clears the bar there — the loop's
# convergence signal (no remaining gap to close).
class TestSaturation(_StoreCase):
    def test_H1_busy_timeout_set(self):
        """Under write-lock contention the store must wait, not error immediately."""
        bt = self.store._conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertGreaterEqual(bt, 1000, "store connection needs a busy_timeout >= 1s")

    def test_H2_synchronous_durability(self):
        """synchronous must be NORMAL(1) or FULL(2) — never OFF(0) (data-loss risk)."""
        sync = self.store._conn.execute("PRAGMA synchronous").fetchone()[0]
        self.assertGreaterEqual(int(sync), 1)

    def test_H3_unknown_event_kind_rejected(self):
        """Schema integrity: an event with an unknown kind must be rejected at append."""
        bad = _event(self.tenant, "s1", "a1")
        bad["kind"] = "not_a_real_kind"
        with self.assertRaises(Exception):
            self.store.append(bad)


if __name__ == "__main__":
    unittest.main()
