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
import sys
from pathlib import Path


def _format_context(schema: dict) -> str:
    """Render the §6 engine schema into a terse, non-generative read (INV-3)."""
    prompt = schema.get("prompt", "")
    insights = schema.get("insights", {})
    scores = insights.get("scores", {})
    flags = insights.get("flags", [])
    selections = insights.get("selections", [])
    pathways = schema.get("pathways", [])
    retrieval = schema.get("retrieval", [])

    c = scores.get("coverage_C", 0.0)
    g = scores.get("gap_G", 0.0)
    p = scores.get("confidence_P", 0.0)

    lines = [
        f'[subconscious · §6] for: "{prompt[:60]}"',
        f"C={c} G={g} P={p}  flags: {flags}",
    ]
    if selections:
        lines.append("top verbs: " + " | ".join(s["verb"] for s in selections))
    if pathways:
        lines.append("pathways: " + " → ".join(pathways))
    if retrieval:
        labels = " | ".join(h.get("label", "") for h in retrieval[:5])
        lines.append(f"graph ({len(retrieval)}): {labels}")
    lines.append("(deterministic — BERT attention pending U5)")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return 0
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import lgwks_engine
        schema = lgwks_engine.run_engine(prompt, top=3)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _format_context(schema),
        }}))
        return 0
    except Exception:
        return 0   # fail-silent — never block the prompt


if __name__ == "__main__":
    sys.exit(main())
