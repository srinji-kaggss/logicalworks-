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
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_daemon_event
from lgwks_daemon_store import DaemonEventStore

STATUS_SCHEMA = "lgwks.daemon.status.v0"
DOCTOR_SCHEMA = "lgwks.daemon.doctor.v0"
HEARTBEAT_INTERVAL_S = 1.0
# A live pid with no heartbeat for this long is a hung daemon, not a healthy one.
HEARTBEAT_STALE_S = 10.0
POLL_INTERVAL_S = 0.5
# Cortex trajectory build cadence (heavier than the 0.5s queue poll — tokenizes
# transcript turns). mtime-guarded so a quiet transcript costs nothing.
CORTEX_INTERVAL_S = 5.0
# #247: cap NEW turns tokenized per cortex tick so the first pass over a long
# backlog (~900+ turns) cannot block the loop — and SIGTERM/stop — for >5s.
# Idempotency (#239) drains the remainder across subsequent ticks.
CORTEX_MAX_TURNS_PER_TICK = 200
# A transcript not written within this window is a closed/idle session, not a
# live one — discovery ignores it so the daemon never pins itself to a corpse.
CAPTURE_MAX_AGE_S = 3600.0
START_TIMEOUT_S = 5.0
STOP_TIMEOUT_S = 5.0


from lgwks_clock import now_iso as _now  # one source of truth for timestamps


def _claude_projects_dir() -> Path:
    """Root that holds Claude Code session transcripts (env-overridable so the
    discovery path can be pointed at a fixture in tests)."""
    override = os.environ.get("LGWKS_CLAUDE_PROJECTS_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".claude" / "projects"


def discover_live_transcript(
    projects_dir: Path,
    *,
    now: float,
    max_age_s: float = CAPTURE_MAX_AGE_S,
    repo_root: Path | None = None,
) -> str | None:
    """Find the freshest live transcript to capture — no hook, no env binding.

    This is what makes the daemon the autonomous core of capture: rather than
    waiting to be told which session to tail (the prior failure mode — pinned to
    a dead subagent transcript, capturing nothing forever), it finds the session
    in flight on its own.

    A candidate is a `*.jsonl` directly under a project dir (subagent transcripts
    live one level deeper, under `<session>/subagents/`, so the shallow glob
    excludes them by construction) that was modified within `max_age_s` of `now`.
    The freshest wins; the daemon's own repo project dir is only a final tiebreak.
    Returns the path string, or None when no session is live.
    """
    if not projects_dir.exists():
        return None
    repo_tag = str(repo_root).replace("/", "-") if repo_root is not None else None
    best: tuple[float, int, str] | None = None  # (mtime, repo_pref, path)
    try:
        for proj in projects_dir.iterdir():
            if not proj.is_dir():
                continue
            pref = 1 if (repo_tag and proj.name == repo_tag) else 0
            for tx in proj.glob("*.jsonl"):
                try:
                    mtime = tx.stat().st_mtime
                except OSError:
                    continue
                if now - mtime > max_age_s:
                    continue
                key = (mtime, pref, str(tx))
                if best is None or key > best:
                    best = key
    except OSError:
        return None
    return best[2] if best else None


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
    bus: Path


def _paths(repo_root: Path) -> DaemonPaths:
    root = repo_root / "store" / "daemon"
    return DaemonPaths(
        repo_root=repo_root,
        root=root,
        lock=root / "daemon.lock.json",
        state=root / "daemon.state.json",
        db=root / "daemon-events.db",
        bus=root / "daemon-bus.jsonl",
    )


def _tenant_for(paths: DaemonPaths, override: str | None = None) -> str:
    """Canonical tenant resolution. One source of truth for every command.

    Default is the repo-derived tenant `repo:<name>`. An explicit override
    (e.g. ``emit --tenant``) is honored so emit/packet stay symmetric — both
    route through this helper, which closes the "emit writes a tenant packet
    can never read" silent-loss gap (#227 F1).
    """
    return (override or "").strip() or f"repo:{paths.repo_root.name}"


def _heartbeat_age_s(heartbeat_at: str) -> float | None:
    """Seconds since an ISO heartbeat, via the canonical clock. None if unparseable."""
    if not heartbeat_at:
        return None
    import datetime as _dt

    from lgwks_clock import now_iso
    try:
        hb = _dt.datetime.fromisoformat(heartbeat_at)
        now = _dt.datetime.fromisoformat(now_iso())
    except (ValueError, TypeError):
        return None
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=now.tzinfo)
    return (now - hb).total_seconds()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


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
        # Hardening (#154 M11): serialize the check-and-create (and close)
        # sequence so two concurrent requests for the same session cannot both
        # pass the "no active worktree" check and create duplicate worktrees.
        self._create_lock = threading.RLock()

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
        # Hardening (#154 M11): the check (no active worktree) and the create
        # must be atomic, else concurrent requests for the same session race.
        with self._create_lock:
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
        kind = item["kind"]
        # research_run (network crawl) and ingest_file (local-only) share the ONE
        # canonical substrate primitive: build_run auto-detects url vs path, so a
        # local target simply never crawls. (G10: ingest_file was a no-op orphan.)
        if kind in ("research_run", "ingest_file"):
            import lgwks_substrate_run as _substrate
            manifest = _substrate.build_run(_make_substrate_args(item["payload"]))
            store.register_run(item["tenant_id"], manifest)
            store.complete_item(item["item_id"], result={
                "run_id": manifest.get("run_id", ""),
                "run_dir": manifest["artifacts"]["root"],
                "counts": manifest.get("counts", {}),
            })
        elif kind == "index_run":
            # Register a substrate run that exists on disk but isn't in shared
            # state yet (e.g. produced by `lgwks research` outside the daemon).
            # Canonical resolver + idempotent register_run — no reinvention.
            import lgwks_substrate_io as _sio
            run_id = str(item["payload"].get("run_id", "")).strip()
            if not run_id:
                raise ValueError("index_run requires payload.run_id")
            run_dir = _sio._resolve_run_dir(run_id)
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError(f"no manifest.json for run {run_id!r} at {run_dir}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            newly = store.register_run(item["tenant_id"], manifest)
            store.complete_item(item["item_id"], result={
                "run_id": manifest.get("run_id", run_id),
                "run_dir": str(run_dir), "newly_indexed": newly,
            })
        elif kind == "workflow":
            # A typed multi-phase plan runs through the ONE composer
            # (lgwks_agent.compose) — the same phase runner the request-lane front
            # door uses, so there is a single execution implementation, not two.
            import lgwks_agent
            plan = item["payload"].get("plan") or {}
            wf_repo = Path(item["payload"].get("repo") or (repo_root or "."))
            rc, phases = lgwks_agent.compose(plan, wf_repo)
            store.complete_item(item["item_id"], result={
                "rc": rc, "ok": rc == 0, "phases": phases,
            })
        elif kind in ("worktree_open", "worktree_close"):
            root = repo_root or Path(".")
            mgr = WorktreeManager(store, root)
            if kind == "worktree_open":
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
        heartbeat_at = (state or {}).get("heartbeat_at", "")
        age = _heartbeat_age_s(heartbeat_at)
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
            "heartbeat_at": heartbeat_at,
            "heartbeat_age_s": age,
            # A hung daemon keeps its pid (alive) but stops writing heartbeats.
            # Flag that distinct failure mode rather than reporting healthy.
            "heartbeat_stale": (age is not None and age > HEARTBEAT_STALE_S),
            "status": "running" if alive else "stopped",
            "stale_lock_reaped": False,
        }

    def readiness(self) -> dict[str, Any]:
        """Readiness (can the daemon serve?) — distinct from liveness (process alive).

        A world-class daemon separates "the process exists" from "it can do its
        job". Readiness here = the event store is reachable and its migrations
        are applied, so packets/queue ops will succeed. (#227 world-class G3)
        """
        store_ok = False
        detail = ""
        try:
            store = DaemonEventStore(self.paths.db)
            try:
                store.queue_depth(_tenant_for(self.paths))  # touches the migrated schema
                store_ok = True
            finally:
                store.close()
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        return {
            "schema": "lgwks.daemon.readiness.v0",
            "ready": store_ok,
            "checks": [{"name": "event_store", "ok": store_ok, "detail": detail}],
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
            # The transcript the *running* daemon is actually tailing — distinct from
            # the env var above. A daemon pinned to a non-existent or subagent
            # transcript silently tails a dead session (#227 F3): surface it as
            # degraded instead of letting it look healthy.
            self._transcript_binding_check(),
        ]
        # transcript_* checks are degraded-but-non-fatal (the daemon still serves
        # the emit/packet contract without a live transcript tail).
        soft = {"transcript_env", "transcript_binding"}
        return {
            "schema": DOCTOR_SCHEMA,
            "repo_root": str(self.paths.repo_root),
            "checks": checks,
            "stale_lock_reaped": stale_reaped,
            "ok": all(check["ok"] or check["name"] in soft for check in checks),
        }

    def _transcript_binding_check(self) -> dict[str, Any]:
        """Inspect the transcript the running daemon is actually bound to (#227 F3)."""
        state = _read_json(self.paths.state) or {}
        lock = _read_json(self.paths.lock) or {}
        bound = (state.get("transcript_path") or lock.get("transcript_path") or "").strip()
        if not bound:
            return {"name": "transcript_binding", "ok": False, "detail": "no transcript bound"}
        path = Path(bound)
        if not path.exists():
            return {"name": "transcript_binding", "ok": False,
                    "detail": f"bound transcript missing: {bound}"}
        if "/subagents/" in bound:
            return {"name": "transcript_binding", "ok": False,
                    "detail": f"bound to subagent transcript (stale session likely): {bound}"}
        return {"name": "transcript_binding", "ok": True, "detail": bound}

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

    def _resolve_capture_target(self, bound: str, *, now: float) -> str | None:
        """Decide which transcript to capture this tick.

        The bound transcript (from `--transcript-path`/`LGWKS_TRANSCRIPT_PATH`)
        wins only when it is itself a live, real, non-subagent session — i.e. an
        explicit pin is honoured while it stays valid. Otherwise the daemon
        DISCOVERS the freshest live transcript on its own. This is the fix for
        the zero-capture failure: a daemon pinned at startup to a dead subagent
        transcript now falls through to discovery instead of tailing a corpse.
        """
        if bound and "/subagents/" not in bound:
            p = Path(bound)
            try:
                if p.exists() and (now - p.stat().st_mtime) <= CAPTURE_MAX_AGE_S:
                    return bound
            except OSError:
                pass
        return discover_live_transcript(
            _claude_projects_dir(), now=now, repo_root=self.paths.repo_root
        )

    def _maybe_process_cortex(self, transcript: str, last_mtime: float) -> float:
        """Tail the bound transcript into cortex trajectories — best-effort.

        Returns the transcript mtime last processed (the new watermark). Skips
        when: no transcript bound, file missing, a subagent transcript (stale
        session, #227 F3), or the file is unchanged since last pass. Idempotent
        at the cortex layer, so a redundant pass is harmless. NEVER raises — a
        capture failure must not take down the daemon (PRD-08).

        #247: work is bounded to CORTEX_MAX_TURNS_PER_TICK new turns per call.
        When a pass hits that cap the backlog is not yet drained, so the
        watermark is HELD below mtime (return last_mtime) — the next tick
        continues from where idempotency left off instead of skipping the
        unchanged file. The advance to mtime happens only once a pass clears
        the whole backlog.
        """
        if not transcript or "/subagents/" in transcript:
            return last_mtime
        try:
            p = Path(transcript)
            if not p.exists():
                return last_mtime
            mtime = p.stat().st_mtime
            if mtime <= last_mtime:
                return last_mtime
            session_id = p.stem or f"claude:{self.paths.repo_root.name}"
            import lgwks_cortex
            cortex = lgwks_cortex.TranscriptCortex(self.paths.repo_root)
            processed = cortex.process_transcript(
                p, session_id, n=0, limit=CORTEX_MAX_TURNS_PER_TICK
            )
            if len(processed) >= CORTEX_MAX_TURNS_PER_TICK:
                # Cap hit → backlog likely remains. Hold the watermark so the
                # next tick resumes draining rather than seeing an unchanged
                # mtime and skipping.
                return last_mtime
            return mtime
        except Exception:
            return last_mtime

    def run_forever(self, *, transcript_path: str | None = None) -> int:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        _cleanup_stale_lock(self.paths)
        
        # HARDEN: Atomic lock creation (O_CREAT | O_EXCL) to prevent TOCTOU race (H8)
        transcript = (transcript_path or os.environ.get("LGWKS_TRANSCRIPT_PATH", "")).strip()
        pid = os.getpid()
        payload = _lock_payload(pid=pid, repo_root=self.paths.repo_root, transcript_path=transcript)
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        
        try:
            fd = os.open(self.paths.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            existing = _read_json(self.paths.lock)
            if existing and _pid_alive(int(existing.get("pid", 0) or 0)):
                raise RuntimeError(f"daemon already running with pid {existing['pid']}")
            # If not alive, something is weird (stale lock wasn't reaped)
            _rm_if_exists(self.paths.lock)
            raise RuntimeError("daemon lock exists but process is dead; try again (stale lock cleared)")

        running = True
        tenant_id = _tenant_for(self.paths)

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
            # Startup fault recovery: we hold the exclusive lock, so any item
            # left in 'running' was orphaned by a dead predecessor — reclaim it
            # so work is never silently lost across a crash. (#227 world-class F1)
            recovered = store.recover_orphaned(tenant_id, older_than_s=0)
            if recovered:
                store.append(
                    _build_event(
                        repo_root=self.paths.repo_root,
                        transcript_path=transcript,
                        kind="workflow_event",
                        payload={"event": "orphaned_work_recovered", "count": recovered},
                    )
                )
            heartbeat_due = time.time()
            cortex_due = time.time()
            # Per-transcript watermarks: discovery may switch the capture target
            # (sessions open and close), and each target has its own mtime
            # progress. A single scalar would lose progress on every switch.
            cortex_watermarks: dict[str, float] = {}
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

                # Autonomous capture: the daemon (not a hook) is the core. It
                # tails its bound transcript into cortex trajectories on its own;
                # a harness hook is only an optional low-latency push-trigger.
                if now >= cortex_due:
                    target = self._resolve_capture_target(transcript, now=now)
                    if target:
                        wm = cortex_watermarks.get(target, 0.0)
                        cortex_watermarks[target] = self._maybe_process_cortex(target, wm)
                    cortex_due = now + CORTEX_INTERVAL_S

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
    res = daemon.doctor()
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


def _start_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    try:
        print(json.dumps(daemon.start(transcript_path=args.transcript_path), indent=2))
        return 0
    except RuntimeError as exc:
        # Machine-first contract: never leak a Python traceback to a parsing
        # agent. An already-running daemon is a benign, structured outcome.
        current = daemon.status()
        print(json.dumps(
            {
                "schema": "lgwks.daemon.start.v0",
                "ok": True,  # post-condition (daemon running) is satisfied
                "status": "already_running",
                "started": False,
                "pid": current.get("pid"),
                "detail": str(exc),
            },
            indent=2,
        ))
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
    counts = manifest.get("counts", {})
    ok = bool(counts.get("documents")) and bool(counts.get("chunks"))
    response = {
        "ok": ok,
        "run_id": manifest.get("run_id"),
        "run_dir": manifest["artifacts"]["root"],
        "tenant_id": tenant_id,
        "resolved_target": target,
        "counts": counts,
    }
    if not ok:
        response["error"] = "research run produced no documents/chunks"
        frontier_path = Path(manifest["artifacts"]["root"]) / "frontier.jsonl"
        if frontier_path.exists():
            frontier_rows = [
                json.loads(line)
                for line in frontier_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            status_counts: dict[str, int] = {}
            for row in frontier_rows:
                status = str(row.get("status", "unknown"))
                status_counts[status] = status_counts.get(status, 0) + 1
            response["frontier_status_counts"] = status_counts
            response["frontier_tail"] = frontier_rows[-5:]
    print(json.dumps({
        **response,
    }, indent=2))
    return 0 if ok else 2


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
    from lgwks_daemon_store import DaemonEventStore, QueueFullError
    paths = _paths(Path(args.repo).resolve())
    store = DaemonEventStore(paths.db)
    try:
        item = json.load(_sys.stdin)
        inserted = store.enqueue(item)
    except QueueFullError as exc:
        # Backpressure is a normal, structured outcome — never a traceback.
        print(json.dumps({"ok": False, "status": "queue_full", "detail": str(exc)}, indent=2))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": "invalid_item", "detail": str(exc)}, indent=2))
        return 1
    finally:
        store.close()
    print(json.dumps({"ok": True, "inserted": inserted}, indent=2))
    return 0


def _queue_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    tenant_id = _tenant_for(paths, getattr(args, "tenant", None))
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
    tenant_id = _tenant_for(paths, getattr(args, "tenant", None))

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


def _ready_command(args: argparse.Namespace) -> int:
    daemon = SessionDaemon(Path(args.repo))
    res = daemon.readiness()
    print(json.dumps(res, indent=2))
    return 0 if res.get("ready") else 1


def _stats_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    tenant_id = _tenant_for(paths, getattr(args, "tenant", None))
    store = DaemonEventStore(paths.db)
    try:
        snapshot = store.stats(tenant_id)
    finally:
        store.close()
    print(json.dumps(snapshot, indent=2))
    return 0


def _packet_command(args: argparse.Namespace) -> int:
    from lgwks_daemon_store import DaemonEventStore
    paths = _paths(Path(args.repo).resolve())
    tenant_id = _tenant_for(paths, getattr(args, "tenant", None))
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
    p.add_argument("--repo", default=".", help="repo root (legacy placement)")
    ps = p.add_subparsers(dest="daemon_command", required=True)

    start = ps.add_parser("start", help="spawn the daemon in the background")
    start.add_argument("--repo", default=".", help="repo root")
    start.add_argument("--transcript-path", default="", help="optional transcript path override")
    start.set_defaults(func=_start_command)

    stop = ps.add_parser("stop", help="stop the background daemon")
    stop.add_argument("--repo", default=".", help="repo root")
    stop.set_defaults(func=_stop_command)

    status = ps.add_parser("status", help="report daemon lock, heartbeat, and event store state")
    status.add_argument("--repo", default=".", help="repo root")
    status.set_defaults(func=_status_command)

    doctor = ps.add_parser("doctor", help="verify daemon runtime prerequisites")
    doctor.add_argument("--repo", default=".", help="repo root")
    doctor.set_defaults(func=_doctor_command)

    ready = ps.add_parser("ready", help="readiness probe — can the daemon serve? (exit 0/1)")
    ready.add_argument("--repo", default=".", help="repo root")
    ready.set_defaults(func=_ready_command)

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
    queue.add_argument("--tenant", help="tenant id (default: repo:<name>); must match emit")
    queue.set_defaults(func=_queue_command)

    stats = ps.add_parser("stats", help="unified per-tenant counters (events + queue + runs)")
    stats.add_argument("--tenant", help="tenant id (default: repo:<name>)")
    stats.set_defaults(func=_stats_command)

    packet = ps.add_parser("packet", help="fetch deterministic session packet")
    packet.add_argument("--session-id", required=True)
    packet.add_argument("--agent-id", required=True)
    packet.add_argument("--tenant", help="tenant id (default: repo:<name>); must match emit")
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

    stream = ps.add_parser("stream", help="live JSON stream of daemon events (AI entrypoint)")
    stream.set_defaults(func=_stream_command)


def _stream_command(args: argparse.Namespace) -> int:
    import time
    from lgwks_daemon_store import DaemonEventStore
    from lgwks_sqlite import get_db
    
    db = get_db(args.repo / "store" / "daemon" / "daemon-events.db")
    store = DaemonEventStore(db)
    
    print("--- START STREAM ---")
    last_event_id = None
    try:
        while True:
            # Fetch events for this tenant (repo)
            events = store.list_events(tenant_id=f"repo:{args.repo.name}", limit=10)
            
            # Identify new events (those after last_event_id)
            new_events = []
            for e in events:
                if e["event_id"] == last_event_id:
                    break
                new_events.append(e)
            
            # Print new events in chronological order (list_events returns DESC)
            for e in reversed(new_events):
                print(json.dumps(e))
                last_event_id = e["event_id"]
            
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    return 0


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

    ready = sub.add_parser("ready", help="readiness probe — can the daemon serve? (exit 0/1)")
    ready.set_defaults(func=_ready_command)

    serve = sub.add_parser("_serve", help=argparse.SUPPRESS)
    serve.add_argument("--transcript-path", default="")
    serve.set_defaults(func=_serve_command)

    enqueue = sub.add_parser("enqueue", help="enqueue a work item from stdin JSON")
    enqueue.set_defaults(func=_enqueue_command)

    queue = sub.add_parser("queue", help="show queue depth for this repo")
    queue.add_argument("--tenant", help="tenant id (default: repo:<name>); must match emit")
    queue.set_defaults(func=_queue_command)

    stats = sub.add_parser("stats", help="unified per-tenant counters (events + queue + runs)")
    stats.add_argument("--tenant", help="tenant id (default: repo:<name>)")
    stats.set_defaults(func=_stats_command)

    packet = sub.add_parser("packet", help="fetch deterministic session packet")
    packet.add_argument("--session-id", required=True)
    packet.add_argument("--agent-id", required=True)
    packet.add_argument("--tenant", help="tenant id (default: repo:<name>); must match emit")
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
