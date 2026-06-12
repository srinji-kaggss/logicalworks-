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


def _decisiveness(match_scores: list[float]) -> float:
    """Top-1 minus top-2 over the normalized match distribution. [0,1], no constants.

    High only when one capability clearly dominates. A zero-score (non-matching)
    capability drops out, so adding irrelevant capabilities cannot change it
    (cardinality-invariance). Depends only on scores, not labels (relabel-invariant).
    """
    scores = [s for s in match_scores if s > 0.0]
    total = sum(scores)
    if total <= 0.0:
        return 0.0
    probs = sorted((s / total for s in scores), reverse=True)
    p2 = probs[1] if len(probs) > 1 else 0.0
    return round(probs[0] - p2, 3)


def _aggregate(*axes: float | None) -> float:
    """Geometric mean over the available (non-None) axes. Constant-free.

    Null-collapse: any zero axis -> 0 (no confidence if any faculty is empty).
    None axes (e.g. grounding unavailable) drop out rather than forcing P to 0.
    """
    vals = [max(0.0, min(1.0, a)) for a in axes if a is not None]
    if not vals:
        return 0.0
    prod = 1.0
    for v in vals:
        prod *= v
    return round(prod ** (1.0 / len(vals)), 3)


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
    graph_available = _db.exists()
    graph_hits, graph_grounded = _graph_retrieval(qt, _db)

    # Independent, constant-free, calculator-derivable axes (no AI in this layer;
    # see feedback_calculator_test). The Qwen embedding layer is separate/upstream.
    #
    # C — coverage: capability coverage ONLY (no graph blend), so C stays independent
    #     of grounding. Upgrade seam (separate Qwen layer, NOT here): match -> cosine.
    C = round(cap_coverage, 3) if qt else 0.0

    # G — grounding gap: from the world graph, an INDEPENDENT source/denominator.
    #     None when the graph is absent: grounding *unavailable* != grounding *failed*.
    if qt and graph_available:
        grounding_rate = round(graph_grounded / len(qt), 3)
        gap_G = round(1.0 - grounding_rate, 3)
        grounding_status = "grounded" if graph_grounded > 0 else "unresolved"
    else:
        grounding_rate = None
        gap_G = None
        grounding_status = "unavailable"

    # d — decisiveness: p1 - p2 over the match distribution. Constant-free.
    decisiveness = _decisiveness([v.get("score", 0.0) for v in selections])

    # P — confidence index: geometric mean over the AVAILABLE axes (None drops out).
    #     No magic constants; null-collapse. An index, not a probability (calibration
    #     is a future packet).
    P = _aggregate(C, grounding_rate, decisiveness)

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
                "gap_G": gap_G,
                "decisiveness_d": decisiveness,
                "confidence_P": P,
                "grounding_status": grounding_status,
                "note": "independent axes (capability / graph / margin); P = geometric "
                        "mean over available axes — constant-free index, not a "
                        "probability; Qwen-cosine + novelty + calibration pending",
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
