#!/usr/bin/env python3
"""Claude PostToolUse hook — emits tool_call events to the daemon store.

Reads Claude Code's PostToolUse JSON payload on stdin:
  {"tool_name": "...", "tool_input": {...}, "tool_response": {...}}

Emits one tool_call event to the daemon store (lane=telemetry, actor=agent,
scope=agent_local). Payload contains only metadata — no raw content (§1-INV).

FAIL-SILENT by law: any error -> exit 0 (INV-6). A hook must never block.
"""
import json
import os
import sys
from pathlib import Path


def _emit(repo_root: Path, tool_name: str, input_keys: list[str], response_size: int, session_id: str) -> None:
    try:
        import lgwks_daemon_event
        from lgwks_daemon_store import DaemonEventStore
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        if not db.parent.exists():
            return
        tenant_id = f"repo:{repo_root.name}"
        event = lgwks_daemon_event.build_event(
            tenant_id=tenant_id,
            agent_id="claude",
            session_id=session_id or f"claude:{repo_root.name}",
            actor="agent",
            client="claude",
            lane="telemetry",
            kind="tool_call",
            scope="agent_local",
            payload={
                "tool_name": tool_name,
                "input_keys": input_keys,
                "response_size": response_size,
            },
        )
        store = DaemonEventStore(db)
        try:
            store.append(event)
        finally:
            store.close()
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
        if not tool_name:
            return 0
        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))
        transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
        session_id = Path(transcript).stem if transcript else ""

        tool_input = payload.get("tool_input") or {}
        input_keys = sorted(tool_input.keys()) if isinstance(tool_input, dict) else []

        resp = payload.get("tool_response") or payload.get("response") or {}
        response_size = len(json.dumps(resp, ensure_ascii=True)) if isinstance(resp, (dict, list)) else 0

        _emit(repo_root, tool_name, input_keys, response_size, session_id)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
