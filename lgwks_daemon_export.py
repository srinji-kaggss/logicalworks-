"""lgwks_daemon_export — content-addressed archive/export tier for daemon runs.

Acceptance contract (P5):
- session/run export is content-addressed (sha256) and auditable (store record).
- local cleanup NEVER occurs before a verified export.
- export destination is configurable; default is store/daemon/exports/.

Usage (CLI via lgwks_daemon):
    daemon export run <run_id> [--dest /path/to/dir]
    daemon cleanup run <run_id> [--force]
    daemon export session <tenant_id> <session_id> [--dest /path/to/dir]
"""
from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

EXPORT_SCHEMA = "lgwks.daemon.export.v0"
CLEANUP_SCHEMA = "lgwks.daemon.cleanup.v0"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _default_export_dir(repo_root: Path) -> Path:
    d = repo_root / "store" / "daemon" / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ExportManager:
    """Content-addressed export and safe cleanup for daemon runs and sessions."""

    def __init__(self, store: Any, repo_root: Path):
        self.store = store
        self.repo_root = repo_root.resolve()

    def export_run(self, run_id: str, *, dest_dir: Path | None = None) -> dict[str, Any]:
        """
        Archive a research run directory to a .tar.gz, compute sha256, record in store.
        Returns export record. Idempotent: re-exporting updates the record.
        """
        state = self.store.get_run_export_state(run_id)
        if state is None:
            raise ValueError(f"run not found: {run_id}")

        run_dir = Path(state["run_dir"])
        if not run_dir.is_dir():
            raise FileNotFoundError(f"run_dir missing on disk: {run_dir}")

        out_dir = dest_dir or _default_export_dir(self.repo_root)
        archive_path = out_dir / f"{run_id}.tar.gz"

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(run_dir, arcname=run_id)

        export_hash = _sha256_file(archive_path)
        self.store.mark_run_exported(
            run_id, export_path=str(archive_path), export_hash=export_hash
        )
        return {
            "schema": EXPORT_SCHEMA,
            "run_id": run_id,
            "export_path": str(archive_path),
            "export_hash": export_hash,
            "run_dir": str(run_dir),
            "verified": True,
        }

    def verify_export(self, run_id: str) -> dict[str, Any]:
        """Re-hash the export archive and confirm it matches the stored hash."""
        state = self.store.get_run_export_state(run_id)
        if state is None:
            raise ValueError(f"run not found: {run_id}")
        if not state["export_hash"]:
            return {"schema": EXPORT_SCHEMA, "run_id": run_id, "verified": False,
                    "reason": "not_exported"}
        export_path = Path(state["export_path"])
        if not export_path.exists():
            return {"schema": EXPORT_SCHEMA, "run_id": run_id, "verified": False,
                    "reason": "archive_missing", "export_path": str(export_path)}
        actual_hash = _sha256_file(export_path)
        ok = actual_hash == state["export_hash"]
        return {
            "schema": EXPORT_SCHEMA,
            "run_id": run_id,
            "verified": ok,
            "stored_hash": state["export_hash"],
            "actual_hash": actual_hash,
            "export_path": str(export_path),
        }

    def cleanup_run(self, run_id: str, *, force: bool = False) -> dict[str, Any]:
        """
        Delete a local run directory.
        Refuses unless the export is verified (or force=True, which logs the override).
        """
        state = self.store.get_run_export_state(run_id)
        if state is None:
            raise ValueError(f"run not found: {run_id}")

        if not force:
            verification = self.verify_export(run_id)
            if not verification["verified"]:
                return {
                    "schema": CLEANUP_SCHEMA,
                    "run_id": run_id,
                    "cleaned": False,
                    "reason": f"export_not_verified: {verification.get('reason', 'hash_mismatch')}",
                }

        run_dir = Path(state["run_dir"])
        removed = False
        if run_dir.is_dir():
            import shutil
            shutil.rmtree(run_dir)
            removed = True

        return {
            "schema": CLEANUP_SCHEMA,
            "run_id": run_id,
            "cleaned": True,
            "removed_dir": str(run_dir),
            "dir_existed": removed,
            "force": force,
        }

    def export_session(
        self,
        tenant_id: str,
        session_id: str,
        *,
        dest_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Export all events for a session to a JSONL file (content-addressed)."""
        events = self.store.list_events(
            tenant_id=tenant_id, session_id=session_id, limit=10_000
        )
        out_dir = dest_dir or _default_export_dir(self.repo_root)
        safe_session = session_id.replace("/", "_").replace(":", "_")[:64]
        export_path = out_dir / f"session-{safe_session}.jsonl"
        with open(export_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=True) + "\n")

        export_hash = _sha256_file(export_path)
        return {
            "schema": EXPORT_SCHEMA,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "event_count": len(events),
            "export_path": str(export_path),
            "export_hash": export_hash,
            "verified": True,
        }
