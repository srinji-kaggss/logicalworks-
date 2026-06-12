#!/usr/bin/env python3
"""Claude Stop hook — reads JSONL transcript tail and emits transcript_turn events.

Fires when Claude finishes responding. Reads the last N turns from the JSONL
transcript at LGWKS_TRANSCRIPT_PATH, then emits one transcript_turn event per
turn to the daemon store.

Dedup: daemon_events PRIMARY KEY (event_id) — optimistic inserts; the store
ignores duplicates on conflict (insert-or-ignore).

FAIL-SILENT by law: any error -> exit 0 (INV-6). Bounded read (last N turns).
"""
import json
import os
import sys
from pathlib import Path

_TAIL_N = 20


def _emit_turn(store, event_module, tenant_id: str, session_id: str, turn: dict) -> None:
    event = event_module.build_event(
        tenant_id=tenant_id,
        agent_id="claude",
        session_id=session_id,
        actor="agent" if turn["role"] == "assistant" else "human",
        client="claude",
        lane="telemetry",
        kind="transcript_turn",
        scope="agent_local",
        payload={
            "role": turn["role"],
            "content_len": turn["content_len"],
            "turn_index": turn["turn_index"],
            "turn_id": turn["turn_id"],
        },
    )
    # Idempotent: the store ignores duplicate event_ids silently
    try:
        store.append(event)
    except Exception:
        pass


def main() -> int:
    try:
        # Consume stdin (Stop hook may send JSON payload — ignore content)
        try:
            json.load(sys.stdin)
        except Exception:
            pass

        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))

        transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
        if not transcript:
            return 0

        session_id = Path(transcript).stem or f"claude:{repo_root.name}"
        tenant_id = f"repo:{repo_root.name}"

        import lgwks_transcript as _transcript
        import lgwks_daemon_event as _event
        from lgwks_daemon_store import DaemonEventStore

        db = repo_root / "store" / "daemon" / "daemon-events.db"
        if not db.parent.exists():
            return 0

        turns = _transcript.tail(transcript, n=_TAIL_N)
        if not turns:
            return 0

        store = DaemonEventStore(db)
        try:
            for turn in turns:
                _emit_turn(store, _event, tenant_id, session_id, turn)
        finally:
            store.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
