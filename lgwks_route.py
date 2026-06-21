"""lgwks_route — unified intent routing.
Consolidates map, engine, route, and refine.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import json
from pathlib import Path
from typing import Any

SCHEMA_ACT = "lgwks.route.act.v1"


def _tokens(text: str) -> set[str]:
    import lgwks_lexicon as _lex
    return set(_lex.tokens(text, min_len=2, stop=_lex.STOP_CLI, unique=True))


def _extract_url(text: str) -> str:
    import re
    m = re.search(r"https?://[^\s\"'<>]+", text or "")
    return m.group(0).rstrip(".,);]") if m else ""


def _phase(name: str, ok: bool, message: str = "", artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "message": message,
        "artifact": artifact or {},
    }


def _choose_action(intent: str, engine: dict[str, Any]) -> dict[str, Any]:
    toks = _tokens(intent)
    pathways = list(engine.get("pathways") or [])
    selections = list((engine.get("insights") or {}).get("selections") or [])
    selected = str(pathways[0] if pathways else (selections[0].get("verb") if selections else ""))

    if toks & {"delete", "remove", "publish", "ship", "merge", "push", "cleanup", "fix", "write"}:
        return {
            "verb": selected or "unknown",
            "kind": "blocked_mutation",
            "effect_class": "write",
            "reason": "mutation/destructive intent requires an explicit typed workflow, not natural-language auto-exec",
        }

    url = _extract_url(intent)
    if url or toks & {"research", "scrape", "crawl", "ingest", "source", "sources", "web"}:
        return {
            "verb": "do research",
            "kind": "research",
            "effect_class": "network",
            "target": url or intent,
            "reason": "intent asks for external/source ingestion; use the research ingestion spine",
        }

    code_terms = {
        "code", "codebase", "function", "class", "method", "symbol", "implementation",
        "implement", "entrypoint", "entry", "call", "calls", "where", "find", "grep",
        "greptile", "orchestrator", "harness", "dependency", "dependencies",
    }
    if selected.startswith("codebase ") or toks & code_terms:
        return {
            "verb": "codebase search",
            "kind": "codebase_search",
            "effect_class": "read",
            "query": intent,
            "reason": "intent asks for implementation/code understanding; search the AI-native codebase index",
        }

    if selected.startswith("route ") or selected:
        return {
            "verb": selected,
            "kind": "planned_only",
            "effect_class": "read",
            "reason": "no executable one-shot adapter exists yet for the selected capability",
        }

    return {
        "verb": "",
        "kind": "blocked_unresolved",
        "effect_class": "read",
        "reason": "intent did not map to an executable lgwks capability",
    }


def _execute_codebase_search(action: dict[str, Any], repo: Path | None = None, top_k: int = 5) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    import lgwks_codebase

    phases: list[dict[str, Any]] = []
    st = lgwks_codebase.status()
    # index_stale is an optional freshness optimization; treat its absence as
    # "not stale" so the front door does not hard-depend on it being present.
    _stale = getattr(lgwks_codebase, "index_stale", lambda *_a, **_k: False)
    if (not st.get("indexed", True) and "entity_count" not in st) or _stale(repo):
        meta = lgwks_codebase.build_index(repo)
        phases.append(_phase("codebase:index", True, "built index", {
            "schema": meta.schema,
            "file_count": meta.file_count,
            "entity_count": meta.entity_count,
            "relation_count": meta.relation_count,
        }))
    results = lgwks_codebase.search(str(action.get("query") or ""), top_k=top_k)
    phases.append(_phase("codebase:search", True, f"{len(results)} results", {
        "query": action.get("query", ""),
        "results": results,
    }))
    return 0, phases, {"results": results}


def _execute_research(action: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    import lgwks_do

    ns = argparse.Namespace(query=str(action.get("target") or ""), depth=1, model="", json=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = lgwks_do._do_research(ns)
    raw = buf.getvalue()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw}
    phases = [_phase("do:research", rc == 0, "executed research ingestion", payload)]
    return rc, phases, payload


def act_intent(
    intent: str,
    *,
    repo: Path | None = None,
    top: int = 5,
    execute: bool = True,
) -> dict[str, Any]:
    import lgwks_engine

    engine = lgwks_engine.run_engine(intent, repo=repo, top=top)
    action = _choose_action(intent, engine)
    phases = [_phase("route:engine", bool(engine.get("schema")), "mapped intent", {
        "pathways": engine.get("pathways", []),
        "selections": (engine.get("insights") or {}).get("selections", []),
        "scores": (engine.get("insights") or {}).get("scores", {}),
    })]

    risk = ((engine.get("meta") or {}).get("risk") or {}).get("verdict")
    if risk == "block":
        return {
            "schema": SCHEMA_ACT,
            "intent": intent,
            "ok": False,
            "executed": False,
            "blocked": True,
            "block_reason": "risk gate blocked the intent",
            "action": action,
            "phases": phases,
            "engine": engine,
        }

    if action["kind"].startswith("blocked_"):
        return {
            "schema": SCHEMA_ACT,
            "intent": intent,
            "ok": False,
            "executed": False,
            "blocked": True,
            "block_reason": action["reason"],
            "action": action,
            "phases": phases,
            "engine": engine,
        }

    if not execute or action["kind"] == "planned_only":
        return {
            "schema": SCHEMA_ACT,
            "intent": intent,
            "ok": action["kind"] != "planned_only",
            "executed": False,
            "blocked": action["kind"] == "planned_only",
            "block_reason": action["reason"] if action["kind"] == "planned_only" else "",
            "action": action,
            "phases": phases,
            "engine": engine,
        }

    if action["kind"] == "codebase_search":
        rc, exec_phases, result = _execute_codebase_search(action, repo=repo, top_k=top)
    elif action["kind"] == "research":
        rc, exec_phases, result = _execute_research(action)
    else:
        rc, exec_phases, result = 2, [], {}

    phases.extend(exec_phases)
    return {
        "schema": SCHEMA_ACT,
        "intent": intent,
        "ok": rc == 0,
        "executed": True,
        "blocked": False,
        "block_reason": "",
        "action": action,
        "phases": phases,
        "result": result,
        "engine": engine,
    }

def route_command(args: argparse.Namespace) -> int:
    cmd = getattr(args, "route_cmd", "")
    
    if cmd == "map":
        import lgwks_map
        return lgwks_map._cmd_map(args)
    
    if cmd == "engine":
        import lgwks_engine
        return lgwks_engine._cmd_engine(args)

    if cmd == "act":
        repo = Path(args.repo).resolve() if getattr(args, "repo", None) else None
        result = act_intent(args.intent, repo=repo, top=getattr(args, "top", 5), execute=not getattr(args, "dry_run", False))
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 2
        
    if cmd == "refine":
        import lgwks_machine
        return lgwks_machine.refine_command(args)

    print(f"error: unknown route command {cmd}", file=sys.stderr)
    return 1


def add_parser(sub) -> None:
    p = sub.add_parser("route", help="T3: intent routing and refinement")
    rs = p.add_subparsers(dest="route_cmd", required=True)
    
    # map
    m = rs.add_parser("map", help="rank verbs by relevance")
    m.add_argument("intent")
    m.add_argument("--top", type=int, default=8, help="number of results (default 8)")
    m.add_argument("--json", action="store_true", help="structured output (default; always JSON)")
    m.set_defaults(func=route_command)
    
    # engine
    e = rs.add_parser("engine", help="subconscious engine: produce schema")
    e.add_argument("prompt")
    e.add_argument("--top", type=int, default=5, help="max capability selections (default 5)")
    e.add_argument("--repo", metavar="PATH", help="repo path for last_state lookup")
    e.set_defaults(func=route_command)

    # act
    act = rs.add_parser("act", help="one-shot agent entrypoint: map intent and execute the safe existing capability")
    act.add_argument("intent")
    act.add_argument("--top", type=int, default=5, help="max capability selections/results")
    act.add_argument("--repo", metavar="PATH", help="repo path for state/index context")
    act.add_argument("--dry-run", action="store_true", help="compile action but do not execute")
    act.add_argument("--json", action="store_true", help="structured output (default; always JSON)")
    act.set_defaults(func=route_command)
    
    # refine
    ref = rs.add_parser("refine", help="intent refinement")
    ref.add_argument("intent")
    ref.set_defaults(func=route_command)
