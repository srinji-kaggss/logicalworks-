#!/usr/bin/env python3
"""Codex ingress adapter — thin daemon event emitter for OpenAI Codex CLI hooks.

Accepts a JSON payload on stdin (keys: prompt/content/message/text).
Emits a human_message event to the daemon store (client="codex").
FAIL-SILENT by law: any error -> exit 0 (INV-6).
No subconscious engine — the daemon does the heavy lifting.
"""
import json
import os
import sys
from pathlib import Path


def _emit_daemon_event(repo_root: Path, prompt: str, session_id: str) -> None:
    try:
        import lgwks_daemon_event
        from lgwks_daemon_store import DaemonEventStore
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        tenant_id = f"repo:{repo_root.name}"
        event = lgwks_daemon_event.build_event(
            tenant_id=tenant_id,
            agent_id="codex",
            session_id=session_id or f"codex:{repo_root.name}",
            actor="human",
            client="codex",
            lane="ingress",
            kind="human_message",
            scope="agent_local",
            payload={"prompt_len": len(prompt), "prompt_head": prompt[:120]},
            source="text",
            trust="human_confirmed",
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
        # Codex may use content/message/text depending on hook type
        prompt = (
            payload.get("prompt")
            or payload.get("content")
            or payload.get("message")
            or payload.get("text")
            or ""
        ).strip()
        if not prompt:
            return 0
        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))
        transcript = os.environ.get("CODEX_SESSION_ID", "")
        session_id = transcript or os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
        if session_id and Path(session_id).suffix:
            session_id = Path(session_id).stem
        _emit_daemon_event(repo_root, prompt, session_id)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
