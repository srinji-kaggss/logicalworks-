"""lgwks_transcript — tail-reader utility for Claude Code JSONL transcript files.

Stateless: always reads the last N turns from the transcript JSONL. Callers
(Stop hooks, telemetry adapters) decide what to emit to the daemon store.

No CLI surface — this is a library module only. Hooks import it directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def tail(path: str | Path | None, n: int = 20, include_content: bool = False) -> list[dict[str, Any]]:
    """Return normalized payloads for the last N transcript turns.
    If n is 0 or -1, returns the full file content.
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

    if n > 0:
        tail_lines = lines[-n:] if len(lines) > n else lines
    else:
        tail_lines = lines

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

        entry = {
            "role": role,
            "content_len": content_len,
            "turn_index": idx,
            "turn_id": turn_id,
        }
        
        if include_content:
            entry["content"] = _extract_content(record)

        results.append(entry)

    return results


def _extract_content(record: dict[str, Any]) -> str:
    """Extract raw text content from a turn across multiple formats."""
    # 1. Claude Code
    msg = record.get("message", {})
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)

    # 2. Gemini
    if "content" in record and isinstance(record["content"], str):
        return record["content"]

    # 3. Codex (Payload/Content list)
    payload = record.get("payload", {})
    if isinstance(payload, dict):
        content_list = payload.get("content", [])
        if isinstance(content_list, list):
            return "\n".join(c.get("text", c.get("input_text", "")) if isinstance(c, dict) else str(c) for c in content_list)
        if isinstance(payload.get("content"), str):
            return payload["content"]

    return ""


def _extract_role(record: dict[str, Any]) -> str:
    """Infer role across multiple formats."""
    # 1. Claude Code
    t = record.get("type", "")
    if t in ("human", "assistant"):
        return t

    # 2. Gemini
    source = record.get("source", "").upper()
    if source == "USER_EXPLICIT": return "human"
    if source == "MODEL": return "assistant"

    # 3. Codex
    payload = record.get("payload", {})
    if isinstance(payload, dict):
        role = payload.get("role", "").lower()
        if role in ("user", "human"): return "human"
        if role in ("assistant", "model", "developer"): return "assistant"
        
    # Tool-result or other structured content
    if "tool_use_id" in record or record.get("type") == "tool_result":
        return "tool_result"

    return "unknown"


def _content_len(record: dict[str, Any]) -> int:
    """Return byte length of content without storing it."""
    # We use extract_content to get the raw text, then count its bytes.
    # This is more accurate across formats than raw JSON length.
    content = _extract_content(record)
    return len(content.encode("utf-8", errors="replace"))


def _turn_id(record: dict[str, Any], fallback_idx: int) -> str:
    """Extract or synthesize a stable turn identifier across formats."""
    # 1. Direct IDs
    for key in ("uuid", "id", "message_id", "event_id", "turn_id"):
        val = record.get(key, "")
        if isinstance(val, str) and val: return val[:64]
    
    # 2. Nested Payload IDs (Codex/Gemini)
    payload = record.get("payload", {})
    if isinstance(payload, dict):
        for key in ("id", "turn_id"):
            val = payload.get(key, "")
            if isinstance(val, str) and val: return val[:64]
            
    return f"turn-{fallback_idx}"

