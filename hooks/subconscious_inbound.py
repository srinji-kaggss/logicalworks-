#!/usr/bin/env python3
"""Second-harness U7 — subconscious inbound tap (UserPromptSubmit hook).

Reads the Director's prompt, runs the deterministic capability map (U1), and injects
a compact non-generative read into Opus's context. The first real subconscious loop:
prompt -> daemon -> in-context, with zero extra Opus action.

FAIL-SILENT by law: any error -> exit 0, emit nothing. A subconscious must never
block consciousness (INV-6). Convergence target: this evolves into the BERT-backed
grounding check that supersedes the static verify-before-assert floor (see BUILDLOG).
"""
import json
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return 0
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import lgwks_map
        result = lgwks_map.map_intent(prompt, top=5)
        matches = result.get("matches", [])
        if not matches:
            return 0
        lines = [f'[subconscious · capability map] for: "{prompt[:80]}"',
                 "relevant lgwks verbs (deterministic lexical match):"]
        for m in matches:
            lines.append(f"  • {m['verb']} ({m['score']}) — {(m['intent'] or '')[:60]}")
        lines.append(f"({result['matched']}/{result['verb_count']} verbs; "
                     "semantic ranking + grounding scores pending U4/U6)")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }}))
        return 0
    except Exception:
        return 0   # fail-silent — never block the prompt


if __name__ == "__main__":
    sys.exit(main())
