"""Tests for lgwks_daemon — lifecycle shell over the durable event store."""

from __future__ import annotations

import json
import argparse
import contextlib
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import lgwks_daemon as daemon_mod


class TestSessionDaemon(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir(exist_ok=True)
        # Hermetic capture: point transcript discovery at an EMPTY dir so a
        # daemon started without an explicit transcript can't reach into the
        # developer's real ~/.claude live session (which would both pollute the
        # temp store and slow shutdown while it tokenizes hundreds of turns).
        self._empty_projects = self.tmp / "claude-projects"
        self._empty_projects.mkdir(exist_ok=True)
        self._prev_projects = os.environ.get("LGWKS_CLAUDE_PROJECTS_DIR")
        os.environ["LGWKS_CLAUDE_PROJECTS_DIR"] = str(self._empty_projects)
        self.daemon = daemon_mod.SessionDaemon(self.tmp)

    def tearDown(self):
        try:
            self.daemon.stop()
        except Exception:
            pass
        if self._prev_projects is None:
            os.environ.pop("LGWKS_CLAUDE_PROJECTS_DIR", None)
        else:
            os.environ["LGWKS_CLAUDE_PROJECTS_DIR"] = self._prev_projects

    def test_doctor_reports_root(self):
        report = self.daemon.doctor()
        self.assertEqual(report["schema"], daemon_mod.DOCTOR_SCHEMA)
        self.assertTrue(any(check["name"] == "daemon_root" for check in report["checks"]))

    def test_start_status_stop(self):
        status = self.daemon.start()
        self.assertEqual(status["status"], "running")
        self.assertTrue(status["alive"])

        deadline = time.time() + 5.0
        heartbeat_seen = False
        while time.time() < deadline:
            current = self.daemon.status()
            if current["heartbeat_at"]:
                heartbeat_seen = True
                break
            time.sleep(0.1)
        self.assertTrue(heartbeat_seen, "daemon should write a heartbeat")

        stopped = self.daemon.stop()
        self.assertEqual(stopped["status"], "stopped")

    def test_double_start_refused(self):
        self.daemon.start()
        with self.assertRaises(RuntimeError):
            self.daemon.start()

    def test_start_with_transcript_path_persists(self):
        transcript = str(self.tmp / "transcript.jsonl")
        status = self.daemon.start(transcript_path=transcript)
        self.assertEqual(status["transcript_path"], transcript)

        # start() spawns the worker and returns; state.json is persisted ASYNCHRONOUSLY by
        # the worker loop (_state_payload). Reading it immediately races the write — a flake
        # that surfaces under load. Poll for it, mirroring test_start_status_stop's heartbeat
        # wait, instead of assuming a synchronous write.
        deadline = time.time() + 5.0
        state = None
        while time.time() < deadline:
            if self.daemon.paths.state.exists():
                state = json.loads(self.daemon.paths.state.read_text(encoding="utf-8"))
                break
            time.sleep(0.05)
        assert state is not None, "daemon should persist state.json shortly after start()"
        self.assertEqual(state["transcript_path"], transcript)

    def test_start_writes_lifecycle_events(self):
        self.daemon.start()
        self.daemon.stop()
        from lgwks_daemon_store import DaemonEventStore

        store = DaemonEventStore(self.daemon.paths.db)
        try:
            rows = store.list_events(tenant_id=f"repo:{self.tmp.name}", limit=10)
        finally:
            store.close()
        self.assertTrue(any(row["payload"]["event"] == "daemon_started" for row in rows))
        self.assertTrue(any(row["payload"]["event"] == "daemon_stopped" for row in rows))

    # --- #227 F1: canonical tenant resolution (emit/packet symmetry) ---
    def test_tenant_for_default_and_override(self):
        paths = self.daemon.paths
        self.assertEqual(daemon_mod._tenant_for(paths), f"repo:{self.tmp.name}")
        self.assertEqual(daemon_mod._tenant_for(paths, "demo"), "demo")
        # blank/whitespace override falls back to the canonical repo tenant
        self.assertEqual(daemon_mod._tenant_for(paths, "   "), f"repo:{self.tmp.name}")

    # --- #227 F2: already-running start is structured, not a traceback ---
    def test_start_command_already_running_is_structured(self):
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
        self.assertEqual(out["schema"], "lgwks.daemon.start.v0")
        self.assertEqual(out["status"], "already_running")
        self.assertTrue(out["ok"])
        self.assertFalse(out["started"])

    # --- #227 F3: doctor flags the live transcript binding ---
    def test_transcript_binding_flags_subagent(self):
        sub = self.tmp / "projects" / "slug" / "subagents"
        sub.mkdir(parents=True)
        tpath = sub / "agent-abc.jsonl"
        tpath.write_text("", encoding="utf-8")
        self.daemon.start(transcript_path=str(tpath))
        check = next(c for c in self.daemon.doctor()["checks"] if c["name"] == "transcript_binding")
        self.assertFalse(check["ok"])
        self.assertIn("subagent", check["detail"])

    def test_transcript_binding_flags_missing(self):
        self.daemon.start(transcript_path=str(self.tmp / "nope.jsonl"))
        check = next(c for c in self.daemon.doctor()["checks"] if c["name"] == "transcript_binding")
        self.assertFalse(check["ok"])
        self.assertIn("missing", check["detail"])

    def test_transcript_binding_ok_for_real_transcript_and_non_fatal(self):
        tpath = self.tmp / "transcript.jsonl"
        tpath.write_text("", encoding="utf-8")
        self.daemon.start(transcript_path=str(tpath))
        report = self.daemon.doctor()
        check = next(c for c in report["checks"] if c["name"] == "transcript_binding")
        self.assertTrue(check["ok"])
        # transcript binding is degraded-but-non-fatal: overall doctor stays ok
        self.assertTrue(report["ok"])

    def _research_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            repo=str(self.tmp),
            target="https://example.invalid/",
            project="daemon-test",
            max_pages=1,
            max_depth=0,
            embed_provider="deterministic",
            login_if_needed=False,
        )

    def _research_manifest(self, *, docs: int, chunks: int) -> dict:
        run_dir = self.tmp / "research-runs" / f"docs-{docs}-chunks-{chunks}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "frontier.jsonl").write_text(
            json.dumps({
                "url": "https://example.invalid/",
                "status": "error",
                "reason": "render failed: Error: dns unavailable",
            }) + "\n",
            encoding="utf-8",
        )
        return {
            "run_id": f"run-docs-{docs}-chunks-{chunks}",
            "target": "https://example.invalid/",
            "artifacts": {"root": str(run_dir)},
            "counts": {
                "documents": docs,
                "chunks": chunks,
                "facts": 0,
                "vectors": 0,
                "graph_nodes": 0,
            },
        }

    def test_research_command_fails_closed_on_empty_crawl(self):
        args = self._research_args()
        manifest = self._research_manifest(docs=0, chunks=0)

        buf = io.StringIO()
        with mock.patch("lgwks_substrate_run.build_run", return_value=manifest):
            with contextlib.redirect_stdout(buf):
                rc = daemon_mod._research_command(args)

        self.assertEqual(rc, 2)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "research run produced no documents/chunks")
        self.assertEqual(payload["frontier_status_counts"], {"error": 1})
        self.assertEqual(payload["frontier_tail"][0]["reason"], "render failed: Error: dns unavailable")

        from lgwks_daemon_store import DaemonEventStore

        store = DaemonEventStore(self.daemon.paths.db)
        try:
            runs = store.list_runs(f"repo:{self.tmp.name}")
        finally:
            store.close()
        self.assertTrue(any(run["run_id"] == manifest["run_id"] for run in runs))

    def test_research_command_reports_success_only_for_materialized_content(self):
        args = self._research_args()
        manifest = self._research_manifest(docs=1, chunks=2)

        buf = io.StringIO()
        with mock.patch("lgwks_substrate_run.build_run", return_value=manifest):
            with contextlib.redirect_stdout(buf):
                rc = daemon_mod._research_command(args)

        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["documents"], 1)
        self.assertEqual(payload["counts"]["chunks"], 2)
        self.assertNotIn("frontier_tail", payload)


class TestDaemonExecutorClosesG10(unittest.TestCase):
    """The daemon executor (_dispatch_item) must EXECUTE every non-escape-hatch
    work kind it advertises in WORK_REGISTRY — not silently drop it to the
    `{"dispatched": True}` no-op. This is the gap-analysis G10 fix that makes the
    daemon a genuine single executor (the orchestration SoT) rather than a queue
    that advertises capabilities it can't run. See engine/DAEMON-ABSORPTION-LOG.md.
    """

    def setUp(self):
        from lgwks_daemon_store import DaemonEventStore
        self.tmp = Path(tempfile.mkdtemp())
        self.store = DaemonEventStore(self.tmp / "events.db")
        self.tenant = "repo:executor-test"

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass

    def _item(self, kind: str, payload: dict) -> dict:
        item = {
            "item_id": f"{kind}-1", "tenant_id": self.tenant,
            "session_id": "s", "agent_id": "a", "kind": kind, "payload": payload,
        }
        self.store.enqueue(item)
        return item

    def _row(self, item_id: str) -> tuple[str, dict]:
        status, result_json = self.store._conn.execute(
            "SELECT status, result_json FROM daemon_work_queue WHERE item_id=?",
            (item_id,),
        ).fetchone()
        return status, json.loads(result_json or "{}")

    def _manifest(self, run_dir: Path) -> dict:
        return {
            "run_id": "run-exec-1", "target": "https://example.invalid/",
            "artifacts": {"root": str(run_dir)},
            "counts": {"documents": 1, "chunks": 2},
        }

    def test_ingest_file_executes_via_substrate_primitive(self):
        run_dir = self.tmp / "ingest-run"
        run_dir.mkdir()
        manifest = self._manifest(run_dir)
        item = self._item("ingest_file", {"target": str(self.tmp / "some.txt")})
        with mock.patch("lgwks_substrate_run.build_run", return_value=manifest):
            daemon_mod._dispatch_item(self.store, item, self.tmp)
        status, result = self._row(item["item_id"])
        self.assertEqual(status, "done")
        self.assertNotEqual(result, {"dispatched": True})  # not the no-op orphan
        self.assertEqual(result["run_id"], "run-exec-1")
        # register_run actually ran — the run is now in shared state.
        self.assertTrue(any(r["run_id"] == "run-exec-1"
                            for r in self.store.list_runs(self.tenant)))

    def test_index_run_registers_on_disk_run(self):
        run_dir = self.tmp / "ondisk-run"
        run_dir.mkdir()
        manifest = self._manifest(run_dir)
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        item = self._item("index_run", {"run_id": "run-exec-1"})
        with mock.patch("lgwks_substrate_io._resolve_run_dir", return_value=run_dir):
            daemon_mod._dispatch_item(self.store, item, self.tmp)
        status, result = self._row(item["item_id"])
        self.assertEqual(status, "done")
        self.assertNotEqual(result, {"dispatched": True})
        self.assertTrue(result["newly_indexed"])
        self.assertTrue(any(r["run_id"] == "run-exec-1"
                            for r in self.store.list_runs(self.tenant)))

    def test_workflow_executes_through_the_one_composer(self):
        item = self._item("workflow", {"plan": {"steps": [{"verb": "review"}]}})
        fake_phases = [{"name": "review", "ok": True, "exit_code": 0}]
        with mock.patch("lgwks_agent.compose", return_value=(0, fake_phases)) as mc:
            daemon_mod._dispatch_item(self.store, item, self.tmp)
        mc.assert_called_once()  # routed through THE composer, not reimplemented
        status, result = self._row(item["item_id"])
        self.assertEqual(status, "done")
        self.assertNotEqual(result, {"dispatched": True})
        self.assertEqual(result["rc"], 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["phases"], fake_phases)

    def test_no_advertised_kind_silently_noops(self):
        """Guard: every WORK_REGISTRY kind except the `custom` escape-hatch has a
        real executor branch (so re-adding a kind without a handler trips this)."""
        import lgwks_daemon_store as ds
        handled = {"research_run", "ingest_file", "index_run", "workflow",
                   "worktree_open", "worktree_close"}
        advertised = set(ds.WORK_KINDS) - {"custom"}
        self.assertEqual(advertised, handled,
                         "a work kind is advertised but has no _dispatch_item branch")
