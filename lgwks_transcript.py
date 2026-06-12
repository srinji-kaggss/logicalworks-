"""lgwks_transcript — tail-reader utility for Claude Code JSONL transcript files.

Stateless: always reads the last N turns from the transcript JSONL. Callers
(Stop hooks, telemetry adapters) decide what to emit to the daemon store.

No CLI surface — this is a library module only. Hooks import it directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def tail(path: str | Path | None, n: int = 20) -> list[dict[str, Any]]:
    """Return normalized payloads for the last N transcript turns.

    Each payload: {"role": ..., "content_len": int, "turn_index": int, "turn_id": str}

    - role: "human" | "assistant" | "tool_result" | "unknown"
    - content_len: byte length of the content field (no raw content stored)
    - turn_index: 0-based index within the returned window (not the global position)
    - turn_id: the uuid from the JSONL line, or a fallback index-based id

    Handles: missing file, empty file, malformed JSONL — all return [].
    """
    if not path:
        return []
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return []

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    # Tail the last n raw lines before parsing (cheap for large files)
    tail_lines = lines[-n:] if len(lines) > n else lines

    results: list[dict[str, Any]] = []
    for idx, raw in enumerate(tail_lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(record, dict):
            continue

        role = _extract_role(record)
        content_len = _content_len(record)
        turn_id = _turn_id(record, idx)

        results.append({
            "role": role,
            "content_len": content_len,
            "turn_index": idx,
            "turn_id": turn_id,
        })

    return results


def _extract_role(record: dict[str, Any]) -> str:
    """Infer role from Claude Code JSONL record shape."""
    # Claude Code format: {"type": "human"|"assistant", "message": {...}}
    t = record.get("type", "")
    if t in ("human", "assistant"):
        return t
    # Fallback: look inside message.role
    msg = record.get("message", {})
    if isinstance(msg, dict):
        r = msg.get("role", "")
        if r in ("user", "human"):
            return "human"
        if r == "assistant":
            return "assistant"
    # Tool-result or other structured content
    if "tool_use_id" in record or record.get("type") == "tool_result":
        return "tool_result"
    return "unknown"


def _content_len(record: dict[str, Any]) -> int:
    """Return byte length of content without storing it."""
    # Try message.content first (Claude Code standard shape)
    msg = record.get("message", {})
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return len(content.encode("utf-8", errors="replace"))
        if isinstance(content, list):
            total = 0
            for block in content:
                if isinstance(block, dict):
                    total += len(json.dumps(block, ensure_ascii=True))
                elif isinstance(block, str):
                    total += len(block.encode("utf-8", errors="replace"))
            return total
    # Fallback: raw record minus metadata keys
    raw = json.dumps(record, ensure_ascii=True)
    return len(raw)


def _turn_id(record: dict[str, Any], fallback_idx: int) -> str:
    """Extract or synthesize a stable turn identifier."""
    for key in ("uuid", "id", "message_id", "event_id"):
        val = record.get(key, "")
        if isinstance(val, str) and val:
            return val[:64]
    return f"turn-{fallback_idx}"
