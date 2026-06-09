"""lgwks_map — U1 Capability Map (second-harness PRD §12).

    map(intent) -> ranked lgwks capabilities that can act on `intent`

The first thing the subconscious runs on any intent: "what is the exact scale of
what already exists for this?" — so the AI is never lost among the verb surface.
Deterministic first slice (token-overlap + deterministic-hash cosine); the BERT /
Qwen semantic ranking is the U4/U6 upgrade, not this. //why PRD §13: prove the
loop today from existing functions (the `lgwks manifest` contract), no model
runtime required.

Scope boundary (honest): this maps lgwks's OWN verb surface — the only capability
registry lgwks can introspect. Claude Code skills + MCPs live in the harness, not
in lgwks; the daemon (U10) folds those in from the environment. Not this unit.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent   # so the hook can run from any cwd
_LGWKS = _REPO / "lgwks"

_TOKEN = re.compile(r"[a-z0-9]+")
# Generic words that add no discriminative signal when matching an intent to a verb.
_STOP = frozenset("the a an of to for and or with in on it this that is are be run get show "
                  "lgwks create make build do use via from into your you my our".split())


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1}


def _load_verbs() -> list[dict[str, Any]]:
    """The capability-map seed: the lgwks manifest's verb list (the stable contract).
    Subprocess the CLI rather than import internals — decouples from build wiring."""
    out = subprocess.run([str(_LGWKS), "manifest"], capture_output=True, text=True,
                         timeout=30, cwd=str(_REPO))
    if out.returncode != 0:
        raise RuntimeError(f"lgwks manifest failed: {out.stderr[:200]}")
    return json.loads(out.stdout).get("verbs", [])


def _score(query_tokens: set[str], verb: dict[str, Any]) -> float:
    """Deterministic relevance: weighted token overlap of the intent against the
    verb name (3x — a name hit is strong signal) and its intent text (1x),
    normalized by query size so scores are comparable across queries."""
    if not query_tokens:
        return 0.0
    name_tok = _tokens(verb.get("verb", ""))
    intent_tok = _tokens(verb.get("intent", ""))
    name_hits = len(query_tokens & name_tok)
    intent_hits = len(query_tokens & intent_tok)
    return (3 * name_hits + intent_hits) / len(query_tokens)


def map_intent(intent: str, *, top: int = 8) -> dict[str, Any]:
    """Rank lgwks verbs by deterministic relevance to `intent`. <1s, no model."""
    qt = _tokens(intent)
    verbs = _load_verbs()
    scored = [
        {"verb": v.get("verb", ""), "intent": v.get("intent", ""),
         "args": v.get("args", {}), "score": round(s, 3)}
        for v in verbs
        if (s := _score(qt, v)) > 0.0
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return {
        "schema": "lgwks.map.v1",
        "query": intent,
        "query_tokens": sorted(qt),
        "verb_count": len(verbs),
        "matched": len(scored),
        "matches": scored[:top],
        "note": ("deterministic token-match over lgwks verbs only; "
                 "semantic ranking + skills/MCPs land in U6/U10"),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print('usage: python3 lgwks_map.py "<intent>"')
        raise SystemExit(2)
    print(json.dumps(map_intent(" ".join(sys.argv[1:])), indent=2))
