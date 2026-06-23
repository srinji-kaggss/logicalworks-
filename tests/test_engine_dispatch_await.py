"""Engine option-(b) semantics: execution happens out-of-band under the daemon
control plane, with a synchronous client wrapper (dispatch_and_await).

The security contract under test: the request lane may only PROPOSE work
(enqueue, subject to the daemon's admission control + gates). It must NOT execute
in its own process. So when the daemon is down we fail CLOSED (work stays queued,
nothing runs) rather than silently draining in-process. When the daemon is up the
client blocks until the daemon completes each item, keeping the surface sync.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import engine.engine as eng
import lgwks_daemon
import lgwks_daemon_store as ds


def _canon_store(root: Path) -> ds.DaemonEventStore:
    return ds.DaemonEventStore(eng._canonical_db(root))


def _review_plan() -> dict:
    # `review` → WORK_KIND `workflow` (see engine._step_to_kind)
    return {"steps": [{"verb": "review", "args": {}}]}


# ── store read side (get_item) ──────────────────────────────────────────────
def test_get_item_reads_status_and_terminal_result(tmp_path):
    store = ds.DaemonEventStore(tmp_path / "events.db")
    try:
        item = {"item_id": "x:0:workflow", "tenant_id": "repo:t", "session_id": "s",
                "agent_id": "a", "kind": "workflow", "payload": {}}
        store.enqueue(item)
        assert store.get_item("x:0:workflow")["status"] == "queued"
        store.complete_item("x:0:workflow", result={"rc": 0, "ok": True})
        done = store.get_item("x:0:workflow")
        assert done["status"] == "done"
        assert done["result"] == {"rc": 0, "ok": True}
        assert store.get_item("nope") is None
    finally:
        store.close()


# ── fail-closed: no daemon → propose-not-execute ────────────────────────────
def test_dispatch_and_await_fails_closed_when_daemon_down(tmp_path):
    res = eng.dispatch_and_await(_review_plan(), repo_root=tmp_path, autostart=False)
    assert res["executed"] is False
    assert res["downgrade"] == "fail_closed"
    assert "daemon not running" in res["reason"]
    # but the work WAS enqueued — the request lane proposed; it did not run.
    store = _canon_store(tmp_path)
    try:
        tenant = eng._canonical_tenant(tmp_path)
        depth = store.queue_depth(tenant)
        assert depth.get("queued", 0) == 1
        assert depth.get("done", 0) == 0  # nothing executed in-process
    finally:
        store.close()


# ── happy path: daemon up → poll to terminal, surface stays synchronous ─────
def test_dispatch_and_await_blocks_until_daemon_completes(tmp_path, monkeypatch):
    # The control plane is "alive" (we don't spawn a real subprocess in a unit
    # test); a fake drain tick stands in for the daemon completing queued work.
    monkeypatch.setattr(lgwks_daemon.SessionDaemon, "status",
                        lambda self: {"alive": True}, raising=True)

    def fake_drain_tick(_seconds):
        store = _canon_store(tmp_path)
        try:
            rows = store._conn.execute(
                "SELECT item_id FROM daemon_work_queue WHERE status='queued'"
            ).fetchall()
            for (iid,) in rows:
                store.complete_item(iid, result={"rc": 0, "ok": True})
        finally:
            store.close()

    monkeypatch.setattr(eng.time, "sleep", fake_drain_tick, raising=True)

    res = eng.dispatch_and_await(_review_plan(), repo_root=tmp_path,
                                 poll_s=0.01, timeout_s=5.0)
    assert res["executed"] is True
    assert res["rc"] == 0
    assert res["timed_out"] == []
    (only,) = res["items"].values()
    assert only["status"] == "done"
    assert only["result"] == {"rc": 0, "ok": True}


# ── timeout: daemon up but never completes → rc!=0, items reported timed_out ─
def test_dispatch_and_await_times_out_without_hanging(tmp_path, monkeypatch):
    monkeypatch.setattr(lgwks_daemon.SessionDaemon, "status",
                        lambda self: {"alive": True}, raising=True)
    monkeypatch.setattr(eng.time, "sleep", lambda _s: None, raising=True)  # no real wait
    res = eng.dispatch_and_await(_review_plan(), repo_root=tmp_path,
                                 poll_s=0.0, timeout_s=0.05)
    assert res["executed"] is True
    assert res["rc"] == 1
    assert len(res["timed_out"]) == 1


# ── tenant correctness: engine enqueues under the tenant the daemon drains ──
def test_canonical_tenant_matches_daemon_drain_tenant(tmp_path):
    paths = lgwks_daemon._paths(tmp_path.resolve())
    assert eng._canonical_tenant(tmp_path) == lgwks_daemon._tenant_for(paths)
    # and the engine's enqueue db is exactly the db the daemon drains
    assert eng._canonical_db(tmp_path) == paths.db
