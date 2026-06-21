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
        # Skip transcript metadata (mode, attachment, ai-title, pr-link,
        # file-history-snapshot, …). These are not conversational turns; left
        # in, they became empty `unknown` rows — pure noise in the training
        # corpus (56% of captured turns before this fix).
        if not _is_turn(record):
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


def _block_text(b: Any) -> str:
    """Render one Claude content block to text.

    Covers the high-signal block types the old extractor silently dropped:
    `thinking` (the agent's reasoning — the core of a reasoning trajectory),
    `tool_use` (the action taken + its arguments), and `tool_result` (the
    outcome). Previously only `text` blocks were read, so 96% of turns came
    out empty and unlabelled.
    """
    if not isinstance(b, dict):
        return str(b)
    bt = b.get("type")
    if bt == "text":
        return b.get("text", "")
    if bt == "thinking":
        return b.get("thinking", "")
    if bt == "tool_use":
        inp = b.get("input", {})
        try:
            inp_s = json.dumps(inp, ensure_ascii=False)
        except (TypeError, ValueError):
            inp_s = str(inp)
        return f"[tool_use {b.get('name', '?')}] {inp_s[:2000]}"
    if bt == "tool_result":
        c = b.get("content", "")
        if isinstance(c, list):
            return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
        return c if isinstance(c, str) else str(c)
    # Unknown block shape: best-effort text field.
    return b.get("text", "")


def _is_turn(record: dict[str, Any]) -> bool:
    """True for actual conversational turns; False for transcript metadata.

    A Claude transcript interleaves real turns (`type` user/assistant) with
    bookkeeping lines (mode, permission-mode, file-history-snapshot, attachment,
    last-prompt, ai-title, queue-operation, system, pr-link). Only the former
    belong in the cortex/training corpus.
    """
    t = record.get("type", "")
    if t in ("user", "human", "assistant"):
        return True
    msg = record.get("message")
    if isinstance(msg, dict) and msg.get("role") in ("user", "human", "assistant"):
        return True
    if record.get("source", "").upper() in ("USER_EXPLICIT", "MODEL"):
        return True
    payload = record.get("payload")
    if isinstance(payload, dict) and payload.get("role"):
        return True
    # Flat/normalized turn shape ({role, content, turn_id}) used by adapters.
    if isinstance(record.get("role"), str) and record.get("role"):
        return True
    return False


def _extract_content(record: dict[str, Any]) -> str:
    """Extract raw text content from a turn across multiple formats."""
    # 1. Claude Code
    msg = record.get("message", {})
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(_block_text(b) for b in content).strip()

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
    # 1. Claude Code — authoritative top-level `type` + `message.role`.
    #    (The old code only matched "human"/"assistant", so every `type:user`
    #    turn fell through to "unknown" — 56% of captured turns.)
    t = record.get("type", "")
    msg = record.get("message", {})
    msg_role = msg.get("role", "") if isinstance(msg, dict) else ""
    if t == "assistant" or msg_role == "assistant":
        return "assistant"
    if t in ("user", "human") or msg_role in ("user", "human"):
        # A user line carrying only tool_result blocks is a tool turn, not a
        # human message — label it as such so the corpus distinguishes them.
        if isinstance(msg, dict):
            c = msg.get("content")
            if (
                isinstance(c, list)
                and c
                and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
            ):
                return "tool_result"
        return "human"

    # 1b. Flat/normalized shape (top-level `role`) used by adapters/tests.
    flat = record.get("role", "")
    if isinstance(flat, str) and flat:
        fl = flat.lower()
        if fl in ("user", "human"):
            return "human"
        if fl in ("assistant", "model", "developer"):
            return "assistant"
        if fl == "tool_result":
            return "tool_result"

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

