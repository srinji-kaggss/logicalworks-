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
import math
import re
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent
_LGWKS = _REPO / "lgwks"
_ENTITY_GRAPH_DB = _REPO / ".lgwks" / "entity_graph.db"
# I8 demand-weight table (frozen, optional). Built offline by
# scripts/build_capability_idf.py from the capability vocabulary; absent -> the
# weights are recomputed from the live verb catalog (graceful, never a hard dep).
_CAP_IDF_ARTIFACT = _REPO / ".lgwks" / "capability_idf.json"
# U6.2 frozen Qwen verb-embedding matrix (optional). Built offline by
# scripts/build_capability_embeddings.py; absent OR embed port unavailable ->
# coverage falls back to the lexical floor below.
_CAP_VEC_ARTIFACT = _REPO / ".lgwks" / "capability_vectors.json"
# INV-7 guard: a real Director prompt is never multi-KB. Cap the attacker-
# controlled input so tokenization/mapping over a pathological prompt can't blow
# the latency budget.
_MAX_PROMPT_CHARS = 16_000

_SCHEMA = "lgwks.engine.schema.v1"

# Tokens that carry no grounding signal
_STOP = frozenset(
    "the a an of to for and or with in on it this that is are be run get show "
    "lgwks create make build do use via from into your you my our please can "
    "how what when where why which will should would could".split()
)
from lgwks_substrate_config import WORD_RE as _TOKEN  # one source of truth

# Prompt patterns that flag structural slop / intent drift
_HEDGE_RE = re.compile(
    r"\b(should work|probably|i think|maybe|i guess|might|perhaps|not sure|ideally)\b",
    re.I,
)
_MULTI_INTENT_RE = re.compile(r"\b(and also|and then|but also|plus|additionally)\b", re.I)


def _tokens(text: object) -> list[str]:
    s = text if isinstance(text, str) else ("" if text is None else str(text))
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP and len(t) > 1]


def _compute_capability_idf(verbs: list[dict]) -> dict[str, float]:
    """Demand weight per token = smoothed IDF over the capability vocabulary.

    Each verb's (name + intent) text is one "document"; df(t) = how many verbs
    mention t; idf(t) = log((N+1)/(df+1)) + 1. Pure counting over human-authored
    capability specs — no AI, hand-derivable (feedback_calculator_test). A token
    common across many capabilities (e.g. "lgwks", "file") carries little
    discrimination -> low weight; a token specific to few -> high weight.
    """
    docs: list[set[str]] = []
    for v in verbs:
        toks = set(_tokens(v.get("verb", ""))) | set(_tokens(v.get("intent", "")))
        if toks:
            docs.append(toks)
    n = len(docs)
    if n == 0:
        return {}
    df: dict[str, int] = {}
    for toks in docs:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    return {t: round(math.log((n + 1) / (c + 1)) + 1.0, 6) for t, c in df.items()}


def _load_demand_weights(verbs: list[dict]) -> dict[str, float]:
    """Frozen IDF artifact if present (declared provenance), else recompute from
    the live verb catalog. Never a hard dependency on the artifact."""
    try:
        if _CAP_IDF_ARTIFACT.exists():
            data = json.loads(_CAP_IDF_ARTIFACT.read_text())
            idf = data.get("idf")
            if isinstance(idf, dict) and idf:
                # The artifact is an untrusted input surface (tamper/corruption):
                # keep only finite, non-negative weights. A bad weight is dropped,
                # not trusted — a negative/inf/nan weight must never reach coverage.
                clean = {}
                for k, val in idf.items():
                    try:
                        w = float(val)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(w) and w >= 0.0:
                        clean[str(k)] = w
                if clean:
                    return clean
    except Exception:
        pass
    return _compute_capability_idf(verbs)


def _capability_coverage(
    query_tokens: list[str], verbs: list[dict], demand: dict[str, float] | None = None
) -> tuple[float, list[dict]]:
    """Return (coverage_fraction, matched_verb_records) using U1 capability map.

    I8 padding/verbosity-invariance: when `demand` weights are supplied, coverage
    is `Σ idf(covered) / Σ idf(recognized)` where "recognized" = query tokens
    present in the demand table. Filler tokens that no capability mentions carry
    zero demand, so padding a prompt with them cannot dilute C. Without weights it
    degrades to the plain token fraction (uniform demand).
    """
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
    if demand:
        denom = sum(demand.get(t, 0.0) for t in qt_set)
        numer = sum(demand.get(t, 0.0) for t in verb_tokens_covered)
        coverage = (numer / denom) if denom > 0.0 else 0.0
    else:
        coverage = len(verb_tokens_covered) / len(qt_set)
    # Range backstop: coverage is a [0,1] axis. Even with sanitized weights, clamp
    # so no downstream (tampered artifact, float drift) can push C out of range.
    if not math.isfinite(coverage):
        coverage = 0.0
    coverage = max(0.0, min(1.0, coverage))
    return round(coverage, 3), [v for _, v in matched[:8]]


from lgwks_vecmath import cosine as _cosine  # one source of truth for cosine similarity


def _load_capability_vectors() -> dict | None:
    """The frozen Qwen verb-embedding matrix, or None when absent/unreadable
    (caller degrades to the lexical floor — never a hard dependency)."""
    try:
        if _CAP_VEC_ARTIFACT.exists():
            data = json.loads(_CAP_VEC_ARTIFACT.read_text())
            if isinstance(data, dict) and data.get("verbs"):
                return data
    except Exception:
        pass
    return None


def _embedding_coverage(prompt: str, artifact: dict, top: int = 8) -> tuple[float, list[dict]] | None:
    """Qwen-cosine coverage: C = top capability cosine; selections scored by cosine.

    One live model call (the prompt); verb vectors are frozen offline. Returns
    None when the embed port is unavailable OR errors (EmbedUnavailableError, model
    not downloaded, worker crash, latency) so the caller falls back to lexical —
    INV-6/INV-7 preserved (the model path runs only when present + warm).
    """
    # The frozen artifact is an untrusted input surface (tamper/corruption/flaky
    # embed worker): the ENTIRE body — port call AND the cosine/selection loop —
    # is guarded, so any malformed record (str vec, non-dict, lying dim) degrades
    # to the lexical floor (return None) rather than raising out (INV-6).
    try:
        import lgwks_embed_port as ep
        raw_dim = artifact.get("dim")
        dim = int(raw_dim) if isinstance(raw_dim, int) and raw_dim > 0 else 0
        port = ep.EmbedPort(dim=dim) if dim else ep.EmbedPort()
        try:
            q = port.embed_text(prompt)
        finally:
            port.close()
        verbs = artifact.get("verbs")
        if not isinstance(verbs, list):
            return None
        sims: list[tuple[float, dict]] = []
        for rec in verbs:
            if not isinstance(rec, dict):
                continue
            vec = rec.get("vec")
            if isinstance(vec, list) and vec and all(
                isinstance(x, (int, float)) and math.isfinite(x) for x in vec
            ):
                sims.append((_cosine(q, vec), rec))
        if not sims:
            return None
        sims.sort(key=lambda x: x[0], reverse=True)
        coverage = max(0.0, min(1.0, sims[0][0]))  # best capability match strength
        selections = [{"verb": str(r.get("verb", "")), "intent": str(r.get("intent", "")),
                       "score": round(max(0.0, s), 6)} for s, r in sims[:top]]
        return round(coverage, 3), selections
    except Exception:
        return None


def _graph_retrieval(query_tokens: list[str], db_path: Path) -> tuple[list[dict], int, bool]:
    """Query entity graph. Returns (hits, grounded_token_count, available).

    `available` is False when the graph is absent OR the query errored (corrupt/
    unreadable DB) — so the caller can treat "couldn't ground" (grounding unknown)
    distinctly from "queried, resolved nothing" (a real grounding gap). Conflating
    them silently zeroes confidence on a corrupt DB.
    """
    if not db_path.exists() or not query_tokens:
        return [], 0, False
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
        return hits[:20], len(grounded), True
    except Exception:
        return [], 0, False


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
    scores = [s for s in match_scores if s > 0.0 and math.isfinite(s)]
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
    vals = [max(0.0, min(1.0, a)) for a in axes if a is not None and math.isfinite(a)]
    if not vals:
        return 0.0
    prod = 1.0
    for v in vals:
        prod *= v
    return round(prod ** (1.0 / len(vals)), 3)


def _denied_envelope(risk: dict[str, Any]) -> dict[str, Any]:
    """Complete §6 envelope for a blocked entrypoint — never run, fully audited.

    Keeps the same shape as a normal result (so consumers need no special case)
    while redacting the prompt and carrying the system-generated receipt."""
    return {
        "schema": _SCHEMA,
        "prompt": "[REDACTED: INJECTION_DETECTED]",
        "attention": None,
        "retrieval": [],
        "last_state": {},
        "insights": {
            "scores": {"confidence_P": 0.0, "injection_risk": risk["injection_risk"],
                       "risk_score": risk.get("risk_score", risk["injection_risk"])},
            "selections": [],
            "flags": ["llm_injection_attempt"],
            "actions_taken": [],
        },
        "pathways": [],
        "meta": {
            "status": "denied",
            "injection": risk.get("injection", {
                "verdict": "block", "signals": risk["signals"], "receipt": risk["receipt"]}),
            "risk": {
                "verdict": "block",
                "risk_score": risk.get("risk_score", risk["injection_risk"]),
                "components": risk.get("components", []),
            },
        },
    }


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
    # ── Layer 1: unified risk + abstention gate (#143; graceful) ──────────────
    # ONE gate composes every risk signal — injection (attacker) · assumption
    # (accidental self-injection / ambiguity) · anomaly (fraud/drift seam) — into a
    # single graded verdict (proceed|attenuate|confirm|block). Only `block` short-
    # circuits; attenuate/confirm sanitize-and-continue but ride a flag + transparency
    # receipt downstream so the gate can require confirmation. Graceful degradation
    # (clean & run), not a hard wall. The assumption signal degrades to absent when
    # the classifier is unavailable, so this stays an exact injection-only regression
    # in headless/no-model contexts (INV-6 — never block the conscious channel).
    # INV-7: cap attacker-controlled input FIRST, so detection scans bounded text
    # (anything past the cap is discarded for all processing — no evasion gap).
    import lgwks_had
    import lgwks_jailbreak
    # Coerce non-str FIRST so the envelope guarantee holds for any input (INV-6): sanitize()
    # downstream assumes a string. A non-str prompt becomes empty rather than crashing.
    if not isinstance(prompt, str):
        prompt = ""
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS]
    risk = lgwks_had.assess(prompt)
    if risk["verdict"] == "block":
        return _denied_envelope(risk)
    prompt = lgwks_jailbreak.sanitize(prompt)
    # ─────────────────────────────────────────────────────────────────────────

    try:
        sys.path.insert(0, str(_REPO))
        import lgwks_map
        map_result = lgwks_map.map_intent(prompt, top=20)
        verbs = map_result.get("matches", [])
        verb_count = map_result.get("verb_count", 0)
    except Exception:
        verbs, verb_count = [], 0

    qt = _tokens(prompt)
    # Coverage C — two paths, same axis. PREFERRED: Qwen-cosine over the frozen
    # verb matrix (semantic; needs the model + artifact). FLOOR: lexical token
    # overlap with I8 demand weighting (always available). The model path is an
    # availability-gated enhancement and silently degrades to the floor.
    demand = _load_demand_weights(verbs)
    emb = None
    if qt:
        cap_vectors = _load_capability_vectors()
        if cap_vectors:
            emb = _embedding_coverage(prompt, cap_vectors)
    if emb is not None:
        cap_coverage, selections = emb
        coverage_mode = "qwen"
    else:
        cap_coverage, selections = _capability_coverage(qt, verbs, demand=demand)
        coverage_mode = "lexical+demand" if demand else "lexical"

    _db = db_path or _ENTITY_GRAPH_DB
    graph_hits, graph_grounded, graph_available = _graph_retrieval(qt, _db)

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
    # attenuate/confirm verdicts ride as additive flags so downstream gates can
    # require confirmation; `proceed` adds nothing (clean path stays clean).
    if risk["verdict"] in ("attenuate", "confirm"):
        flags = flags + [f"injection_{risk['verdict']}"]
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
                "injection_risk": risk["injection_risk"],
                "risk_score": risk.get("risk_score", risk["injection_risk"]),
                "grounding_status": grounding_status,
                "coverage_mode": coverage_mode,
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
            "injection": risk.get("injection", {
                "verdict": risk["verdict"], "signals": risk["signals"], "receipt": risk["receipt"]}),
            "risk": {
                "verdict": risk["verdict"],
                "risk_score": risk.get("risk_score", risk["injection_risk"]),
                "components": risk.get("components", []),
            },
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
