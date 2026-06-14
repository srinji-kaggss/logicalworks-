"""lgwks_daemon — minimal background lifecycle shell for the referee runtime.

This is the first real daemon process surface:

- `start` spawns a background worker and refuses double-start
- `status` reports lock / heartbeat / transcript / store state
- `stop` terminates the worker cleanly
- `doctor` validates the local daemon substrate

The worker is intentionally small. It owns the single lock/heartbeat path and
persists lifecycle events into `lgwks_daemon_store.DaemonEventStore`.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_daemon_event
from lgwks_daemon_store import DaemonEventStore

STATUS_SCHEMA = "lgwks.daemon.status.v0"
DOCTOR_SCHEMA = "lgwks.daemon.doctor.v0"
HEARTBEAT_INTERVAL_S = 1.0
POLL_INTERVAL_S = 0.5
START_TIMEOUT_S = 5.0
STOP_TIMEOUT_S = 5.0


from lgwks_clock import now_iso as _now  # one source of truth for timestamps


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class DaemonPaths:
    repo_root: Path
    root: Path
    lock: Path
    state: Path
    db: Path


def _paths(repo_root: Path) -> DaemonPaths:
    root = repo_root / "store" / "daemon"
    return DaemonPaths(
        repo_root=repo_root,
        root=root,
        lock=root / "daemon.lock.json",
        state=root / "daemon.state.json",
        db=root / "daemon-events.db",
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rm_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _lock_payload(*, pid: int, repo_root: Path, transcript_path: str) -> dict[str, Any]:
    return {
        "pid": pid,
        "started_at": _now(),
        "repo_root": str(repo_root),
        "transcript_path": transcript_path,
    }


def _state_payload(*, pid: int, repo_root: Path, transcript_path: str, db_path: Path, status: str) -> dict[str, Any]:
    return {
        "schema": STATUS_SCHEMA,
        "pid": pid,
        "repo_root": str(repo_root),
        "db_path": str(db_path),
        "transcript_path": transcript_path,
        "status": status,
        "heartbeat_at": _now(),
    }


def _cleanup_stale_lock(paths: DaemonPaths) -> bool:
    lock = _read_json(paths.lock)
    if lock is None:
        return False
    pid = int(lock.get("pid", 0) or 0)
    if _pid_alive(pid):
        return False
    _rm_if_exists(paths.lock)
    return True


def _build_event(
    *,
    repo_root: Path,
    transcript_path: str,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    tenant_id = f"repo:{repo_root.name}"
    return lgwks_daemon_event.build_event(
        tenant_id=tenant_id,
        agent_id="daemon.referee",
        session_id=f"daemon:{repo_root.name}",
        actor="daemon",
        client="daemon",
        lane="control",
        kind=kind,
        scope="shared_referee",
        payload={"repo_root": str(repo_root), "transcript_path": transcript_path, **payload},
    )


def _make_substrate_args(payload: dict[str, Any]) -> "argparse.Namespace":
    import argparse as _ap
    return _ap.Namespace(
        target=payload["target"],
        project=payload.get("project", ""),
        source_type=payload.get("source_type", "auto"),
        max_pages=int(payload.get("max_pages", 25)),
        max_depth=int(payload.get("max_depth", 2)),
        max_files=int(payload.get("max_files", 250)),
        max_chars=int(payload.get("max_chars", 120_000)),
        chunk_words=int(payload.get("chunk_words", 320)),
        chunk_overlap=int(payload.get("chunk_overlap", 48)),
        fact_threshold=float(payload.get("fact_threshold", 0.6)),
        embed_provider=payload.get("embed_provider", "auto"),
        embed_model=payload.get("embed_model", ""),
        login_if_needed=bool(payload.get("login_if_needed", True)),
        login_url=payload.get("login_url", ""),
        success_selector=payload.get("success_selector", None),
        max_auto_bypass_attempts=int(payload.get("max_auto_bypass_attempts", 3)),
        max_auth_handoffs=int(payload.get("max_auth_handoffs", 3)),
        browser_engine=payload.get("browser_engine", "webkit"),
        click_discovery=bool(payload.get("click_discovery", False)),
        max_clicks_per_page=int(payload.get("max_clicks_per_page", 20)),
        crawl_mode=payload.get("crawl_mode", "link-then-click"),
        embed_screenshots=bool(payload.get("embed_screenshots", False)),
        json=True,
    )


WORKTREE_SCHEMA = "lgwks.daemon.worktree.v0"


class WorktreeManager:
    """Daemon-owned git worktree lifecycle with CRDT-backed audit trail.

    Referee contract: one active worktree per (tenant, session). A second
    create for the same session returns the existing record without touching git.
    All git and store mutations are serialized through the daemon queue.
    """

    def __init__(self, store: "DaemonEventStore", repo_root: Path):
        self.store = store
        self.repo_root = repo_root.resolve()

    def _worktree_base(self) -> Path:
        base = self.repo_root / "store" / "daemon" / "worktrees"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _git(self, *args: str, cwd: Path | None = None) -> tuple[int, str]:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd or self.repo_root),
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    def _head_sha(self) -> str:
        rc, out = self._git("rev-parse", "HEAD")
        return out.strip() if rc == 0 else "unknown"

    def _crdt_path(self, tenant_id: str) -> Path:
        crdt_dir = self.repo_root / "store" / "daemon" / "crdt"
        crdt_dir.mkdir(parents=True, exist_ok=True)
        return crdt_dir / f"{tenant_id.replace(':', '_')}.json"

    def _crdt_add(self, tenant_id: str, worktree_id: str) -> None:
        try:
            import lgwks_crdt as _crdt
            sink = _crdt.JsonFileSink(self._crdt_path(tenant_id))
            with sink.locked():
                state = sink.load()
                active = state.get("active_worktrees") or _crdt.ORSet()
                if not isinstance(active, _crdt.ORSet):
                    active = _crdt.ORSet()
                state["active_worktrees"] = active.add(worktree_id)
                sink.commit(state)
        except Exception:
            pass

    def _crdt_remove(self, tenant_id: str, worktree_id: str) -> None:
        try:
            import lgwks_crdt as _crdt
            sink = _crdt.JsonFileSink(self._crdt_path(tenant_id))
            with sink.locked():
                state = sink.load()
                active = state.get("active_worktrees") or _crdt.ORSet()
                if not isinstance(active, _crdt.ORSet):
                    active = _crdt.ORSet()
                state["active_worktrees"] = active.remove(worktree_id, None)
                sink.commit(state)
        except Exception:
            pass

    def _crdt_reconverge_entity_graph(self, worktree_path: Path) -> None:
        """Merge entity-graph CRDT sidecars from worktree into the main repo.

        Must be called BEFORE git worktree remove so the worktree files are
        still readable. FAIL-SILENT on any error (same pattern as _crdt_add).
        """
        try:
            import lgwks_crdt as _crdt
            wt = worktree_path.resolve()
            if not wt.exists():
                return
            for sidecar in wt.rglob("*.crdt.json"):
                try:
                    wt_sink = _crdt.JsonFileSink(sidecar)
                    wt_state = wt_sink.load()
                    if not wt_state:
                        continue
                    rel = sidecar.relative_to(wt)
                    canonical = self.repo_root / rel
                    _crdt.reconverge(_crdt.JsonFileSink(canonical), wt_state)
                except Exception:
                    pass
        except Exception:
            pass

    def create(self, tenant_id: str, session_id: str, agent_id: str) -> dict[str, Any]:
        """Create a new worktree for a session, or return the existing one."""
        active = self.store.list_worktrees(tenant_id, active_only=True)
        existing = next((w for w in active if w["session_id"] == session_id), None)
        if existing:
            return {**existing, "created": False, "reason": "session_already_has_active_worktree"}

        worktree_id = f"wt-{session_id[:8]}-{agent_id[:6]}-{int(time.time())}"
        branch = f"daemon/{worktree_id}"
        worktree_path = self._worktree_base() / worktree_id
        base_sha = self._head_sha()

        rc, out = self._git("worktree", "add", "-b", branch, str(worktree_path))
        if rc != 0:
            raise RuntimeError(f"git worktree add failed: {out}")

        self.store.open_worktree(
            worktree_id=worktree_id, tenant_id=tenant_id, session_id=session_id,
            agent_id=agent_id, repo_path=str(self.repo_root),
            worktree_path=str(worktree_path), branch=branch, base_sha=base_sha,
        )
        self._crdt_add(tenant_id, worktree_id)
        return {
            "schema": WORKTREE_SCHEMA,
            "worktree_id": worktree_id, "tenant_id": tenant_id,
            "session_id": session_id, "agent_id": agent_id,
            "worktree_path": str(worktree_path), "branch": branch,
            "base_sha": base_sha, "status": "active", "created": True,
        }

    def close(self, worktree_id: str) -> dict[str, Any]:
        """Remove a worktree and mark it closed. Safe to call on already-closed."""
        rec = self.store.get_worktree(worktree_id)
        if rec is None:
            raise ValueError(f"worktree not found: {worktree_id}")
        if rec["status"] != "active":
            return {**rec, "closed": False, "reason": "already_closed"}

        error: str | None = None
        wt_path = Path(rec["worktree_path"])

        # Reconverge entity-graph CRDT sidecars BEFORE git removes the worktree files
        self._crdt_reconverge_entity_graph(wt_path)

        rc, out = self._git("worktree", "remove", "--force", str(wt_path))
        if rc != 0:
            error = f"git worktree remove failed: {out}"
        else:
            # Delete the daemon branch; ignore if already gone
            self._git("branch", "-D", rec["branch"])

        self.store.close_worktree(worktree_id, error=error)
        self._crdt_remove(rec["tenant_id"], worktree_id)
        return {**rec, "status": "error" if error else "closed", "closed": True, "error": error}

    def list(self, tenant_id: str, *, all_: bool = False) -> list[dict[str, Any]]:
        return self.store.list_worktrees(tenant_id, active_only=not all_)


def _dispatch_item(store: "DaemonEventStore", item: dict[str, Any], repo_root: Path | None = None) -> None:
    """Route a dequeued work item to the appropriate handler."""
    try:
        store.append(lgwks_daemon_event.build_event(
            tenant_id=item["tenant_id"], agent_id=item["agent_id"],
            session_id=item["session_id"], actor="daemon", client="daemon",
            lane="workflow", kind="workflow_event", scope="shared_referee",
            payload={"event": "item_dispatched", "item_id": item["item_id"], "kind": item["kind"]},
        ))
        if item["kind"] == "research_run":
            import lgwks_substrate_run as _substrate
            manifest = _substrate.build_run(_make_substrate_args(item["payload"]))
            store.register_run(item["tenant_id"], manifest)
            store.complete_item(item["item_id"], result={"run_dir": manifest["artifacts"]["root"]})
        elif item["kind"] in ("worktree_open", "worktree_close"):
            root = repo_root or Path(".")
            mgr = WorktreeManager(store, root)
            if item["kind"] == "worktree_open":
                result = mgr.create(item["tenant_id"], item["session_id"], item["agent_id"])
            else:
                result = mgr.close(item["payload"].get("worktree_id", ""))
            store.complete_item(item["item_id"], result=result)
        else:
            store.complete_item(item["item_id"], result={"dispatched": True})
    except Exception as exc:
        store.fail_item(item["item_id"], error=str(exc))


class SessionDaemon:
    def __init__(self, repo_root: Path):
        self.paths = _paths(repo_root.resolve())
        self._proc: subprocess.Popen[str] | None = None

    def status(self) -> dict[str, Any]:
        lock = _read_json(self.paths.lock)
        state = _read_json(self.paths.state)
        pid = int((lock or {}).get("pid", 0) or 0)
        alive = _pid_alive(pid)
        return {
            "schema": STATUS_SCHEMA,
            "repo_root": str(self.paths.repo_root),
            "daemon_root": str(self.paths.root),
            "db_path": str(self.paths.db),
            "lock_present": self.paths.lock.exists(),
            "state_present": self.paths.state.exists(),
            "pid": pid or None,
            "alive": alive,
            "transcript_path": (state or lock or {}).get("transcript_path", ""),
            "heartbeat_at": (state or {}).get("heartbeat_at", ""),
            "status": "running" if alive else "stopped",
            "stale_lock_reaped": False,
        }

    def doctor(self) -> dict[str, Any]:
        stale_reaped = _cleanup_stale_lock(self.paths)
        self.paths.root.mkdir(parents=True, exist_ok=True)
        checks = [
            {"name": "daemon_root", "ok": self.paths.root.exists(), "detail": str(self.paths.root)},
            {"name": "event_store_parent", "ok": self.paths.db.parent.exists(), "detail": str(self.paths.db.parent)},
            {
                "name": "transcript_env",
                "ok": bool(os.environ.get("LGWKS_TRANSCRIPT_PATH", "").strip()),
                "detail": os.environ.get("LGWKS_TRANSCRIPT_PATH", ""),
            },
        ]
        return {
            "schema": DOCTOR_SCHEMA,
            "repo_root": str(self.paths.repo_root),
            "checks": checks,
            "stale_lock_reaped": stale_reaped,
            "ok": all(check["ok"] or check["name"] == "transcript_env" for check in checks),
        }

    def start(self, *, transcript_path: str | None = None) -> dict[str, Any]:
        stale_reaped = _cleanup_stale_lock(self.paths)
        current = self.status()
        if current["alive"]:
            raise RuntimeError(f"daemon already running with pid {current['pid']}")

        transcript = (transcript_path or os.environ.get("LGWKS_TRANSCRIPT_PATH", "")).strip()
        cmd = [sys.executable, str(Path(__file__).resolve()), "--repo", str(self.paths.repo_root), "_serve"]
        if transcript:
            cmd.extend(["--transcript-path", transcript])
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.paths.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._proc = proc

        deadline = time.time() + START_TIMEOUT_S
        while time.time() < deadline:
            status = self.status()
            if status["alive"]:
                status["stale_lock_reaped"] = stale_reaped
                return status
            time.sleep(0.1)
        raise RuntimeError(f"daemon failed to start (spawned pid {proc.pid})")

    def stop(self) -> dict[str, Any]:
        stale_reaped = _cleanup_stale_lock(self.paths)
        current = self.status()
        pid = current["pid"]
        if not pid or not current["alive"]:
            _rm_if_exists(self.paths.lock)
            return {**current, "stale_lock_reaped": stale_reaped, "status": "stopped"}

        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + STOP_TIMEOUT_S
        while time.time() < deadline:
            if self._proc is not None and self._proc.pid == pid:
                try:
                    self._proc.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            if not _pid_alive(pid) or not self.paths.lock.exists():
                _rm_if_exists(self.paths.lock)
                stopped = self.status()
                stopped["stale_lock_reaped"] = stale_reaped
                if self._proc is not None and self._proc.pid == pid:
                    try:
                        self._proc.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        pass
                    self._proc = None
                return stopped
            time.sleep(0.1)
        raise RuntimeError(f"daemon pid {pid} did not stop within {STOP_TIMEOUT_S}s")

    def run_forever(self, *, transcript_path: str | None = None) -> int:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        _cleanup_stale_lock(self.paths)
        existing = _read_json(self.paths.lock)
        if existing and _pid_alive(int(existing.get("pid", 0) or 0)):
            raise RuntimeError(f"daemon already running with pid {existing['pid']}")

        transcript = (transcript_path or os.environ.get("LGWKS_TRANSCRIPT_PATH", "")).strip()
        pid = os.getpid()
        _write_json(self.paths.lock, _lock_payload(pid=pid, repo_root=self.paths.repo_root, transcript_path=transcript))

        running = True
        tenant_id = f"repo:{self.paths.repo_root.name}"

        def _stop(_signum, _frame) -> None:
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        store = DaemonEventStore(self.paths.db)
        try:
            store.append(
                _build_event(
                    repo_root=self.paths.repo_root,
                    transcript_path=transcript,
                    kind="workflow_event",
                    payload={"event": "daemon_started", "pid": pid},
                )
            )
            heartbeat_due = time.time()
            while running:
                now = time.time()
                if now >= heartbeat_due:
                    _write_json(
                        self.paths.state,
                        _state_payload(
                            pid=pid,
                            repo_root=self.paths.repo_root,
                            transcript_path=transcript,
                            db_path=self.paths.db,
                            status="running",
                        ),
                    )
                    heartbeat_due = now + HEARTBEAT_INTERVAL_S

                items = store.dequeue(tenant_id, limit=1)
                for item in items:
                    _dispatch_item(store, item, repo_root=self.paths.repo_root)

                time.sleep(POLL_INTERVAL_S)
            store.append(
                _build_event(
                    repo_root=self.paths.repo_root,
                    transcript_path=transcript,
                    kind="workflow_event",
                    payload={"event": "daemon_stopped", "pid": pid},
                )
            )
            _write_json(
                self.paths.state,
                _state_payload(
                    pid=pid,
                    repo_root=self.paths.repo_root,
                    transcript_path=transcript,
                    db_path=self.paths.db,
                    status="stopped",
                ),
            )
            return 0
        finally:
            store.close()
            _rm_if_exists(self.paths.lock)


def _status_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    print(json.dumps(daemon.status(), indent=2))
    return 0


def _doctor_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    print(json.dumps(daemon.doctor(), indent=2))
    return 0


def _start_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    print(json.dumps(daemon.start(transcript_path=args.transcript_path), indent=2))
    return 0


def _stop_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    print(json.dumps(daemon.stop(), indent=2))
    return 0


def _serve_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    return daemon.run_forever(transcript_path=args.transcript_path)


def _research_command(args: argparse.Namespace) -> int:
    """Run a substrate research session and index it into the daemon store."""
    import sys as _sys
    import lgwks_substrate_run as _substrate
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"

    target = args.target
    is_url = "://" in target
    is_path = Path(target).exists()
    if not is_url and not is_path:
        import lgwks_search as _search
        results = _search.search(target, k=5)
        if not results:
            print(json.dumps({"error": f"web search for {target!r} returned no results"}), file=_sys.stderr)
            return 1
        target = results[0]["url"]

    payload: dict[str, Any] = {
        "target": target,
        "project": args.project,
        "max_pages": args.max_pages,
        "max_depth": args.max_depth,
        "embed_provider": args.embed_provider,
        "login_if_needed": args.login_if_needed,
    }
    sub_args = _make_substrate_args(payload)
    manifest = _substrate.build_run(sub_args)
    store = DaemonEventStore(paths.db)
    try:
        store.register_run(tenant_id, manifest)
    finally:
        store.close()
    print(json.dumps({
        "ok": True,
        "run_id": manifest.get("run_id"),
        "run_dir": manifest["artifacts"]["root"],
        "tenant_id": tenant_id,
        "resolved_target": target,
    }, indent=2))
    return 0


def _runs_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore as _Store
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = _Store(paths.db)
    try:
        runs = store.list_runs(tenant_id)
    finally:
        store.close()
    print(json.dumps({"tenant_id": tenant_id, "runs": runs}, indent=2))
    return 0


def _runs_get_command(args: argparse.Namespace) -> int:
    """Return the full manifest for an indexed research run."""
    import sys as _sys
    from lgwks_daemon_store import DaemonEventStore as _Store
    paths = _paths(Path(args.repo).resolve())
    store = _Store(paths.db)
    try:
        manifest = store.get_run(args.run_id)
    finally:
        store.close()
    if manifest is None:
        print(json.dumps({"error": "run not found", "run_id": args.run_id}), file=_sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


def _enqueue_command(args: argparse.Namespace) -> int:
    import sys as _sys
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        item = json.load(_sys.stdin)
        inserted = store.enqueue(item)
    finally:
        store.close()
    print(json.dumps({"ok": True, "inserted": inserted}, indent=2))
    return 0


def _queue_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = DaemonEventStore(paths.db)
    try:
        depth = store.queue_depth(tenant_id)
    finally:
        store.close()
    print(json.dumps(depth, indent=2))
    return 0


def _emit_command(args: argparse.Namespace) -> int:
    """Inject an event into the daemon store without a live hook (for end-to-end testing)."""
    import sys as _sys
    from lgwks_daemon_store import DaemonEventStore

    paths = _paths(Path(args.repo).resolve())
    tenant_id = getattr(args, "tenant", None) or f"repo:{paths.repo_root.name}"

    payload: dict[str, Any] = {}
    if not _sys.stdin.isatty():
        try:
            payload = json.loads(_sys.stdin.read())
        except (json.JSONDecodeError, ValueError):
            payload = {}

    event = lgwks_daemon_event.build_event(
        tenant_id=tenant_id,
        agent_id=args.agent_id,
        session_id=args.session_id,
        actor=args.actor,
        client=args.client,
        lane=args.lane,
        kind=args.kind,
        scope=args.scope,
        payload=payload,
    )

    store = DaemonEventStore(paths.db)
    try:
        inserted = store.append(event)
    finally:
        store.close()

    print(json.dumps({"ok": True, "inserted": inserted, "event_id": event.get("event_id")}, indent=2))
    return 0


def _packet_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = DaemonEventStore(paths.db)
    try:
        packet = store.get_packet(
            tenant_id=tenant_id,
            session_id=args.session_id,
            agent_id=args.agent_id,
        )
    finally:
        store.close()
    print(json.dumps(packet, indent=2))
    return 0


def _worktree_create_command(args: argparse.Namespace) -> int:
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = DaemonEventStore(paths.db)
    try:
        mgr = WorktreeManager(store, paths.repo_root)
        result = mgr.create(tenant_id, args.session_id, args.agent_id)
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0


def _worktree_close_command(args: argparse.Namespace) -> int:
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        mgr = WorktreeManager(store, paths.repo_root)
        result = mgr.close(args.worktree_id)
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0


def _worktree_list_command(args: argparse.Namespace) -> int:
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = DaemonEventStore(paths.db)
    try:
        mgr = WorktreeManager(store, paths.repo_root)
        items = mgr.list(tenant_id, all_=args.all)
    finally:
        store.close()
    print(json.dumps({"tenant_id": tenant_id, "worktrees": items}, indent=2))
    return 0


def _export_run_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_export import ExportManager
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        dest = Path(args.dest) if args.dest else None
        result = ExportManager(store, paths.repo_root).export_run(args.run_id, dest_dir=dest)
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0


def _export_verify_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_export import ExportManager
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        result = ExportManager(store, paths.repo_root).verify_export(args.run_id)
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return int(not result["verified"])


def _cleanup_run_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_export import ExportManager
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        result = ExportManager(store, paths.repo_root).cleanup_run(args.run_id, force=args.force)
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0 if result["cleaned"] else 1


def _export_session_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_export import ExportManager
    paths = _paths(Path(args.repo).resolve())
    tenant_id = f"repo:{paths.repo_root.name}"
    store = DaemonEventStore(paths.db)
    try:
        dest = Path(args.dest) if args.dest else None
        result = ExportManager(store, paths.repo_root).export_session(
            tenant_id, args.session_id, dest_dir=dest
        )
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0


def _register_export_subcommands(ps: Any) -> None:
    exp = ps.add_parser("export", help="content-addressed archive export for runs and sessions")
    exp_sub = exp.add_subparsers(dest="export_command", required=True)

    exp_run = exp_sub.add_parser("run", help="export a research run to a .tar.gz archive")
    exp_run.add_argument("run_id")
    exp_run.add_argument("--dest", default="", help="destination directory (default: store/daemon/exports/)")
    exp_run.set_defaults(func=_export_run_command)

    exp_verify = exp_sub.add_parser("verify", help="verify export archive hash matches stored hash")
    exp_verify.add_argument("run_id")
    exp_verify.set_defaults(func=_export_verify_command)

    exp_session = exp_sub.add_parser("session", help="export all session events to JSONL")
    exp_session.add_argument("session_id")
    exp_session.add_argument("--dest", default="")
    exp_session.set_defaults(func=_export_session_command)

    cleanup = ps.add_parser("cleanup", help="safely delete local run data after verified export")
    cleanup.add_argument("run_id")
    cleanup.add_argument("--force", action="store_true", default=False,
                         help="delete even without verified export (logs override)")
    cleanup.set_defaults(func=_cleanup_run_command)


def _register_worktree_subcommands(ps: Any) -> None:
    wt = ps.add_parser("worktree", help="manage daemon-owned git worktrees")
    wt_sub = wt.add_subparsers(dest="worktree_command", required=True)

    wt_create = wt_sub.add_parser("create", help="create a new worktree for a session")
    wt_create.add_argument("--session-id", required=True)
    wt_create.add_argument("--agent-id", required=True)
    wt_create.set_defaults(func=_worktree_create_command)

    wt_close = wt_sub.add_parser("close", help="remove an active worktree")
    wt_close.add_argument("worktree_id")
    wt_close.set_defaults(func=_worktree_close_command)

    wt_list = wt_sub.add_parser("list", help="list worktrees for this repo")
    wt_list.add_argument("--all", dest="all", action="store_true", default=False,
                         help="include closed/errored worktrees")
    wt_list.set_defaults(func=_worktree_list_command)


def add_parser(sub) -> None:
    p = sub.add_parser("daemon", help="background daemon lifecycle shell for the shared referee runtime")
    p.add_argument("--repo", default=".", help="repo root")
    ps = p.add_subparsers(dest="daemon_command", required=True)

    start = ps.add_parser("start", help="spawn the daemon in the background")
    start.add_argument("--transcript-path", default="", help="optional transcript path override")
    start.set_defaults(func=_start_command)

    stop = ps.add_parser("stop", help="stop the background daemon")
    stop.set_defaults(func=_stop_command)

    status = ps.add_parser("status", help="report daemon lock, heartbeat, and event store state")
    status.set_defaults(func=_status_command)

    doctor = ps.add_parser("doctor", help="verify daemon runtime prerequisites")
    doctor.set_defaults(func=_doctor_command)

    enqueue = ps.add_parser("enqueue", help="enqueue a work item from stdin JSON")
    enqueue.set_defaults(func=_enqueue_command)

    emit = ps.add_parser(
        "emit",
        help="inject an event into the daemon store without a live hook (end-to-end testing)",
    )
    emit.add_argument("--kind", required=True, choices=sorted(lgwks_daemon_event.KINDS))
    emit.add_argument("--session-id", dest="session_id", required=True)
    emit.add_argument("--agent-id", dest="agent_id", required=True)
    emit.add_argument("--tenant")
    emit.add_argument("--actor", default="human", choices=sorted(lgwks_daemon_event.ACTORS))
    emit.add_argument("--client", default="human", choices=sorted(lgwks_daemon_event.CLIENTS))
    emit.add_argument("--lane", default="ingress", choices=sorted(lgwks_daemon_event.LANES))
    emit.add_argument("--scope", default="agent_local", choices=sorted(lgwks_daemon_event.SCOPES))
    emit.set_defaults(func=_emit_command)

    queue = ps.add_parser("queue", help="show queue depth for this repo")
    queue.set_defaults(func=_queue_command)

    packet = ps.add_parser("packet", help="fetch deterministic session packet")
    packet.add_argument("--session-id", required=True)
    packet.add_argument("--agent-id", required=True)
    packet.set_defaults(func=_packet_command)

    research = ps.add_parser("research", help="run substrate crawl and index into daemon store")
    research.add_argument("target", help="URL or local path to research")
    research.add_argument("--project", default="")
    research.add_argument("--max-pages", type=int, default=25)
    research.add_argument("--max-depth", type=int, default=2)
    research.add_argument("--embed-provider", default="auto")
    research.add_argument("--login-if-needed", action=argparse.BooleanOptionalAction, default=True)
    research.set_defaults(func=_research_command)

    runs_p = ps.add_parser("runs", help="list or retrieve indexed research runs")
    runs_sub = runs_p.add_subparsers(dest="runs_cmd", required=True)
    runs_list = runs_sub.add_parser("list", help="list indexed runs for this repo")
    runs_list.set_defaults(func=_runs_command)
    runs_get = runs_sub.add_parser("get", help="retrieve full manifest for a run")
    runs_get.add_argument("run_id", help="run ID (from 'runs list')")
    runs_get.set_defaults(func=_runs_get_command)

    _register_export_subcommands(ps)
    _register_worktree_subcommands(ps)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgwks_daemon")
    parser.add_argument("--repo", default=".", help="repo root")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="spawn the daemon in the background")
    start.add_argument("--transcript-path", default="")
    start.set_defaults(func=_start_command)

    stop = sub.add_parser("stop", help="stop the background daemon")
    stop.set_defaults(func=_stop_command)

    status = sub.add_parser("status", help="report daemon state")
    status.set_defaults(func=_status_command)

    doctor = sub.add_parser("doctor", help="verify daemon runtime prerequisites")
    doctor.set_defaults(func=_doctor_command)

    serve = sub.add_parser("_serve", help=argparse.SUPPRESS)
    serve.add_argument("--transcript-path", default="")
    serve.set_defaults(func=_serve_command)

    enqueue = sub.add_parser("enqueue", help="enqueue a work item from stdin JSON")
    enqueue.set_defaults(func=_enqueue_command)

    queue = sub.add_parser("queue", help="show queue depth for this repo")
    queue.set_defaults(func=_queue_command)

    packet = sub.add_parser("packet", help="fetch deterministic session packet")
    packet.add_argument("--session-id", required=True)
    packet.add_argument("--agent-id", required=True)
    packet.set_defaults(func=_packet_command)

    research = sub.add_parser("research", help="run substrate crawl and index into daemon store")
    research.add_argument("target")
    research.add_argument("--project", default="")
    research.add_argument("--max-pages", type=int, default=25)
    research.add_argument("--max-depth", type=int, default=2)
    research.add_argument("--embed-provider", default="auto")
    research.add_argument("--login-if-needed", action=argparse.BooleanOptionalAction, default=True)
    research.set_defaults(func=_research_command)

    runs_p = sub.add_parser("runs", help="list or retrieve indexed research runs")
    runs_sub = runs_p.add_subparsers(dest="runs_cmd", required=True)
    runs_list = runs_sub.add_parser("list", help="list indexed runs for this repo")
    runs_list.set_defaults(func=_runs_command)
    runs_get = runs_sub.add_parser("get", help="retrieve full manifest for a run")
    runs_get.add_argument("run_id", help="run ID (from 'runs list')")
    runs_get.set_defaults(func=_runs_get_command)

    _register_export_subcommands(sub)
    _register_worktree_subcommands(sub)

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
