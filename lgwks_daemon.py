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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lgwks_daemon_event
from lgwks_daemon_store import DaemonEventStore

STATUS_SCHEMA = "lgwks.daemon.status.v0"
DOCTOR_SCHEMA = "lgwks.daemon.doctor.v0"
HEARTBEAT_INTERVAL_S = 1.0
START_TIMEOUT_S = 5.0
STOP_TIMEOUT_S = 5.0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
            while running:
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
                time.sleep(HEARTBEAT_INTERVAL_S)
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

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
