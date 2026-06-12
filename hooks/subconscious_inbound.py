#!/usr/bin/env python3
"""Second-harness U7 — subconscious inbound tap (UserPromptSubmit hook).

Reads the Director's prompt, runs the U6 subconscious engine
(`lgwks_engine.run_engine`), and injects a compact non-generative §6 read into
Opus's context. The first real subconscious loop closed end-to-end:
prompt -> engine -> §6 schema in-context, with zero extra Opus action.

FAIL-SILENT by law: any error -> exit 0, emit nothing. A subconscious must never
block consciousness (INV-6). Non-generative by construction (INV-3): only scores,
labels, and paths are surfaced — never prose. 30s hard cap (INV-7); run_engine is
<1s and its only I/O (entity-graph query) is graceful-absent.
"""
import json
import os
import sys
from pathlib import Path


def _clean(text: object, limit: int = 60) -> str:
    """Collapse whitespace and drop non-printable chars, then truncate.

    Any interpolated free text (the prompt, verb names, graph labels) is untrusted
    and could carry newlines / ANSI / control chars. Left raw, a newline splits
    additionalContext into a line that isn't a labelled score/path — i.e. injects
    arbitrary (even instruction-shaped) prose into Opus's context. INV-3 demands
    every line be a header; this keeps it so.
    """
    collapsed = " ".join(str(text).split())
    return "".join(ch for ch in collapsed if ch.isprintable())[:limit]


def _format_context(schema: dict) -> str:
    """Render the §6 engine schema into a terse, non-generative read (INV-3)."""
    insights = schema.get("insights", {})
    scores = insights.get("scores", {})
    flags = insights.get("flags", [])
    selections = insights.get("selections", [])
    pathways = schema.get("pathways", [])
    retrieval = schema.get("retrieval", [])

    c = scores.get("coverage_C", 0.0)
    g = scores.get("gap_G")
    g_disp = g if g is not None else "n/a"  # gap_G is None when grounding unavailable
    p = scores.get("confidence_P", 0.0)

    lines = [
        f'[subconscious · §6] for: "{_clean(schema.get("prompt", ""))}"',
        f"C={c} G={g_disp} P={p}  flags: {flags}",
    ]
    if selections:
        lines.append("top verbs: " + " | ".join(_clean(s.get("verb", ""), 40) for s in selections))
    if pathways:
        lines.append("pathways: " + " → ".join(_clean(v, 40) for v in pathways))
    if retrieval:
        labels = " | ".join(_clean(h.get("label", ""), 40) for h in retrieval[:5])
        lines.append(f"graph ({len(retrieval)}): {labels}")
    lines.append("(deterministic — BERT attention pending U5)")
    return "\n".join(lines)


def _emit_daemon_event(repo_root: Path, prompt: str, session_id: str) -> None:
    """Best-effort: index this prompt as a human_message into the daemon store."""
    try:
        import lgwks_daemon_event
        from lgwks_daemon_store import DaemonEventStore
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        tenant_id = f"repo:{repo_root.name}"
        event = lgwks_daemon_event.build_event(
            tenant_id=tenant_id,
            agent_id="claude",
            session_id=session_id or f"claude:{repo_root.name}",
            actor="human",
            client="claude",
            lane="ingress",
            kind="human_message",
            scope="agent_local",
            payload={"prompt_len": len(prompt), "prompt_head": prompt[:120]},
        )
        store = DaemonEventStore(db)
        try:
            store.append(event)
        finally:
            store.close()
    except Exception:
        pass  # fail-silent — adapter must never block


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return 0
        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))
        transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
        session_id = Path(transcript).stem if transcript else ""
        import lgwks_engine
        schema = lgwks_engine.run_engine(prompt, top=3)
        _emit_daemon_event(repo_root, prompt, session_id)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _format_context(schema),
        }}))
        return 0
    except Exception:
        return 0   # fail-silent — never block the prompt


if __name__ == "__main__":
    sys.exit(main())
