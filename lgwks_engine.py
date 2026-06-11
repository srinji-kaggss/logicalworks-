"""lgwks_engine — U6: Subconscious Engine (deterministic first slice).

Produces the §6 schema (lgwks.engine.schema.v1) for a given prompt:
  - capability map (U1 via lgwks_map)
  - world-graph retrieval (entity_graph.resolve_nodes; graceful if DB absent)
  - last_state from session markers
  - deterministic C/G/P scores (no BERT — BERT upgrades these in U4/U5)
  - slop / intent-drift flags (pattern detection, no model)

Non-generative by construction (INV-3). Fails silently on any sub-component
error (INV-6 — never block the conscious channel).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent
_LGWKS = _REPO / "lgwks"
_ENTITY_GRAPH_DB = _REPO / ".lgwks" / "entity_graph.db"

_SCHEMA = "lgwks.engine.schema.v1"

# Tokens that carry no grounding signal
_STOP = frozenset(
    "the a an of to for and or with in on it this that is are be run get show "
    "lgwks create make build do use via from into your you my our please can "
    "how what when where why which will should would could".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")

# Prompt patterns that flag structural slop / intent drift
_HEDGE_RE = re.compile(
    r"\b(should work|probably|i think|maybe|i guess|might|perhaps|not sure|ideally)\b",
    re.I,
)
_MULTI_INTENT_RE = re.compile(r"\b(and also|and then|but also|plus|additionally)\b", re.I)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def _capability_coverage(query_tokens: list[str], verbs: list[dict]) -> tuple[float, list[dict]]:
    """Return (coverage_fraction, matched_verb_records) using U1 capability map."""
    if not query_tokens:
        return 0.0, []
    qt_set = set(query_tokens)
    matched: list[tuple[float, dict]] = []
    verb_tokens_covered: set[str] = set()
    for v in verbs:
        name_tok = set(_tokens(v.get("verb", "")))
        intent_tok = set(_tokens(v.get("intent", "")))
        overlap = qt_set & (name_tok | intent_tok)
        if overlap:
            verb_tokens_covered |= overlap
            score = v.get("score", 0.0)
            if score > 0.0:
                matched.append((score, v))
    matched.sort(key=lambda x: x[0], reverse=True)
    coverage = len(verb_tokens_covered) / len(qt_set)
    return round(coverage, 3), [v for _, v in matched[:8]]


def _graph_retrieval(query_tokens: list[str], db_path: Path) -> tuple[list[dict], int]:
    """Query entity graph for query tokens. Returns (hits, grounded_token_count)."""
    if not db_path.exists() or not query_tokens:
        return [], 0
    try:
        sys.path.insert(0, str(_REPO))
        import lgwks_entity_graph as eg
        db = eg.GraphDB(db_path)
        hits: list[dict] = []
        grounded: set[str] = set()
        for tok in query_tokens[:12]:
            nodes = db.resolve_nodes(tok, limit=3)
            for n in nodes:
                hits.append({"node_id": n["node_id"], "label": n["label"], "type": n["type"]})
                grounded.add(tok)
        db.close()
        return hits[:20], len(grounded)
    except Exception:
        return [], 0


def _last_state(repo: Path | None) -> dict[str, Any]:
    """Read the most recent session marker for this repo."""
    try:
        marker_file = Path.home() / ".config" / "lgwks" / "session-markers.jsonl"
        if not marker_file.exists():
            return {}
        lines = marker_file.read_text().splitlines()
        for line in reversed(lines):
            entry = json.loads(line)
            if repo is None or entry.get("repo") == str(repo):
                return {"last_session": entry.get("t"), "kind": entry.get("kind"),
                        "note": entry.get("note", "")}
        return {}
    except Exception:
        return {}


def _detect_flags(prompt: str) -> list[str]:
    """Deterministic prompt-pattern flags (no model)."""
    flags: list[str] = []
    if _HEDGE_RE.search(prompt):
        flags.append("unverified_claim")
    if _MULTI_INTENT_RE.search(prompt) or prompt.count(".") > 4:
        flags.append("intent_drift")
    return flags


def run_engine(
    prompt: str,
    *,
    repo: Path | None = None,
    top: int = 5,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Produce the §6 schema for `prompt`. Non-generative, deterministic, <1s.

    Fails silently on any sub-component error — always returns a valid envelope.
    """
    try:
        sys.path.insert(0, str(_REPO))
        import lgwks_map
        map_result = lgwks_map.map_intent(prompt, top=20)
        verbs = map_result.get("matches", [])
        verb_count = map_result.get("verb_count", 0)
    except Exception:
        verbs, verb_count = [], 0

    qt = _tokens(prompt)
    cap_coverage, selections = _capability_coverage(qt, verbs)

    _db = db_path or _ENTITY_GRAPH_DB
    graph_hits, graph_grounded = _graph_retrieval(qt, _db)

    # Deterministic C/G/P
    # C: fraction of query tokens covered by capabilities OR graph
    if qt:
        graph_token_coverage = graph_grounded / len(qt)
        # blend capability coverage with graph coverage (graph adds at most 0.3)
        C = round(min(1.0, cap_coverage + 0.3 * graph_token_coverage), 3)
    else:
        C = 0.0

    # G: simple inverse heuristic (BERT replaces this in U5)
    G = round(max(0.0, 1.0 - C), 3)

    # P: conservative estimate; bounded [0.30, 0.88] so we're never overconfident
    P = round(0.30 + 0.58 * C * (1.0 - 0.2 * G), 3)

    flags = _detect_flags(prompt)
    state = _last_state(repo)

    return {
        "schema": _SCHEMA,
        "prompt": prompt,
        "attention": None,  # BERT pending U4/U5
        "retrieval": graph_hits,
        "last_state": state,
        "insights": {
            "scores": {
                "coverage_C": C,
                "gap_G": G,
                "confidence_P": P,
                "note": "deterministic token/graph coverage — BERT replaces in U5",
            },
            "selections": [{"verb": v["verb"], "intent": v["intent"], "score": v["score"]}
                           for v in selections[:top]],
            "flags": flags,
            "actions_taken": [],
        },
        "pathways": [v["verb"] for v in selections[:3]],
        "meta": {
            "verb_count": verb_count,
            "query_tokens": qt,
            "graph_hits": len(graph_hits),
        },
    }


def _cmd_engine(args: Any) -> int:
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else None
    result = run_engine(args.prompt, repo=repo, top=getattr(args, "top", 5))
    print(json.dumps(result, indent=2))
    return 0


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "engine",
        help="U6 subconscious engine: produce §6 schema for a prompt (deterministic, <1s)",
    )
    p.add_argument("prompt", help="director prompt text")
    p.add_argument("--top", type=int, default=5, help="max capability selections (default 5)")
    p.add_argument("--repo", metavar="PATH", help="repo path for last_state lookup")
    p.set_defaults(func=_cmd_engine)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python3 lgwks_engine.py "<prompt>"')
        raise SystemExit(2)
    print(json.dumps(run_engine(" ".join(sys.argv[1:])), indent=2))
