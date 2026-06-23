"""lgwks_agent — the single AGENT front door (machine-first).

Perceive then act, in one door (like a Claude-Code-style harness):
  lgwks agent "<intent>"          → WorldView only (perceive; no side effects)
  lgwks agent "<intent>" --act    → WorldView + compile an ActionPlan + run it

It replaces the four overlapping doors (route / do / wf-run / x) with one well:
  MAP   lgwks_engine.run_engine          → WorldView (PRD §6 schema, non-generative)
  PLAN  compile_plan(intent, worldview)  → ActionPlan {single|workflow|batch}
  RUN   compose(plan)                     one import-based phase-runner, guarded
  WORK  CAPABILITIES[name]                direct module calls, never subprocess

Spec: spec/second-harness/SPEC-front-door-factory-v1.md  (security S1–S7, fail-closed).
The human projection is a separate door (oversight); INV-1 keeps the two unmerged.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "lgwks.agent.v1"

_WRITE_WORDS = {"delete", "remove", "publish", "ship", "merge", "push", "cleanup",
                "fix", "write", "refactor", "commit", "govern"}
_NET_WORDS = {"research", "scrape", "crawl", "ingest", "source", "sources", "web", "fetch"}
_CODE_WORDS = {"code", "codebase", "function", "class", "method", "symbol", "implementation",
               "implement", "where", "find", "grep", "dependency", "dependencies",
               "entrypoint", "call", "calls", "orchestrator", "harness"}


# ── helpers ────────────────────────────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    import lgwks_lexicon as lex
    return set(lex.tokens(text, min_len=2, stop=lex.STOP_CLI, unique=True))


def _extract_url(text: str) -> str:
    m = re.search(r"https?://[^\s\"'<>]+", text or "")
    return m.group(0).rstrip(".,);]") if m else ""


# ── effect taxonomy (spec §5/§6) ─────────────────────────────────────────────
# The manifest carries no per-verb effect metadata, so the door owns this
# policy. FAIL-CLOSED: any verb not positively classified read/network is
# treated as `write` (approval-gated by S1), so an unrecognized or newly-added
# verb can never auto-exec from a bare intent — it over-gates, never under-gates.
_NETWORK_VERBS = {"crawl", "fetch", "research", "ingest",
                  "state spawn", "state run crawl", "ops daemon research"}
_READ_VERBS = {"doctor", "manifest", "extract", "convert", "codebase",
               "review", "solve", "verify", "prove"}
_READ_TOKENS = {"doctor", "status", "list", "info", "query", "audit", "audit-graph",
                "graph", "viz", "check", "verify", "resolve", "replay", "stats",
                "ready", "cards", "handoff", "comprehend", "cohere", "aup",
                "index", "context", "health-check", "audit-trail", "migration-check",
                "prove", "tokenizers"}


def _effect_class(verb: str, url: str = "") -> str:
    """read | network | write for a canonical verb. Fail-closed → write."""
    if url or verb in _NETWORK_VERBS:
        return "network"
    if verb in _READ_VERBS:
        return "read"
    if verb.rsplit(" ", 1)[-1] in _READ_TOKENS:
        return "read"
    return "write"  # fail-closed: unknown/mutating verbs require approval


def _operand(intent: str, url: str) -> str:
    """Best-effort single positional for a dispatched verb (file path / url / query)."""
    if url:
        return url
    for tok in intent.split():
        if "/" in tok or re.search(r"\.\w{1,5}$", tok):
            return tok
    return intent


# ── MAP: intent → WorldView (the perceive payload) ──────────────────────────
def worldview(intent: str, repo: Path | None, top: int) -> dict[str, Any]:
    import lgwks_engine
    eng = lgwks_engine.run_engine(intent, repo=repo, top=top)
    insights = eng.get("insights") or {}
    return {
        "attention": eng.get("attention", {}),
        "retrieval": eng.get("retrieval", []),
        "last_state": eng.get("last_state", {}),
        "insights": {
            "scores": insights.get("scores", {}),
            "selections": insights.get("selections", []),
            "flags": insights.get("flags", []),
        },
        "pathways": eng.get("pathways", []),
        "risk": ((eng.get("meta") or {}).get("risk") or {"verdict": "allow"}),
    }


# ── PLAN: intent + WorldView → ActionPlan ───────────────────────────────────
def compile_plan(intent: str, wv: dict[str, Any]) -> dict[str, Any]:
    toks = _tokens(intent)
    pathways = list(wv.get("pathways") or [])
    selections = list((wv.get("insights") or {}).get("selections") or [])
    selected = str(pathways[0] if pathways else (selections[0].get("verb") if selections else ""))

    # batch — deterministic brace product-expansion of literal commands (the old `x`)
    if "{" in intent and "}" in intent:
        import lgwks_multiply as mx
        cmds = mx._expand_braces(intent)
        risks = [mx._classify(c) for c in cmds]
        worst = max((mx._RISK_ORDER[r] for r in risks), default=0)
        return {
            "kind": "batch", "intent_class": "batch_exec",
            "effect_class": "read" if worst == 0 else "write",
            "approval": "force" if worst >= 3 else ("once" if worst >= 1 else "none"),
            "steps": [{"verb": "sh", "args": {"cmd": c}, "risk": r,
                       "effect_class": "read" if r == "read" else "write"}
                      for c, r in zip(cmds, risks)],
            "reason": "brace product expansion (one declaration, expanded to argv; one approval)",
        }

    # write/mutation — NEVER auto-exec from NL (S1); compile a typed, approval-gated plan
    if toks & _WRITE_WORDS:
        gate = toks & {"ship", "govern", "cleanup", "merge", "publish"}
        verb = "review" if gate else (selected or "review")
        return {
            "kind": "workflow", "intent_class": "code_change", "effect_class": "write",
            "approval": "once",
            "steps": [{"verb": verb, "args": {"intent": intent}, "effect_class": "write"}],
            "reason": "mutation intent requires an explicit typed workflow + approval, not NL auto-exec",
        }

    # network — external/source ingestion
    url = _extract_url(intent)
    if url or (toks & _NET_WORDS):
        return {
            "kind": "single", "intent_class": "research", "effect_class": "network",
            "approval": "none",
            "steps": [{"verb": "ingest", "args": {"target": url or intent}, "effect_class": "network"}],
            "reason": "intent asks for external/source ingestion",
        }

    # read — code understanding via the AI-native index
    if selected.startswith("codebase ") or (toks & _CODE_WORDS):
        return {
            "kind": "single", "intent_class": "codebase_search", "effect_class": "read",
            "approval": "none",
            "steps": [{"verb": "codebase", "args": {"query": intent}, "effect_class": "read"}],
            "reason": "intent asks for implementation/code understanding",
        }

    # general — route to the engine's top-ranked capability (the MAP layer already
    # did the hard work; PLAN must not discard it). One intent_class per resolved
    # verb (S7). Effect class is classified fail-closed; S1/S2/S3 gate execution.
    if selected:
        url2 = _extract_url(intent)
        effect = _effect_class(selected, url2)
        is_wf = selected.startswith("ops workflow ")
        return {
            "kind": "workflow" if is_wf else "single",
            "intent_class": selected,
            "effect_class": effect,
            "approval": "once" if effect == "write" else "none",
            "steps": [{
                "verb": selected,
                "args": {"intent": intent, "operand": _operand(intent, url2)},
                "effect_class": effect,
            }],
            "reason": f"engine ranked '{selected}' top for this intent",
        }

    return {
        "kind": "single", "intent_class": "unresolved", "effect_class": "read",
        "approval": "none", "steps": [],
        "reason": "intent did not map to an executable lgwks capability",
    }


# ── WORK: capability dispatch (direct import; never subprocess) ──────────────
def _cap_codebase(step: dict[str, Any], repo: Path | None):
    import lgwks_codebase
    from lgwks_phase import PhaseResult
    q = str(step.get("args", {}).get("query", ""))
    st = lgwks_codebase.status()
    if not st.get("indexed", True) and "entity_count" not in st:
        lgwks_codebase.build_index(repo)
    results = lgwks_codebase.search(q, top_k=5)
    return PhaseResult(name="codebase:search", ok=True, exit_code=0,
                       message=f"{len(results)} results", artifact={"query": q, "results": results})


def _cap_ingest(step: dict[str, Any], repo: Path | None):
    import lgwks_substrate
    import lgwks_substrate_io as _io  # canonical filesystem slug (one source of truth)
    from lgwks_phase import PhaseResult
    target = str(step.get("args", {}).get("target", ""))
    ns = argparse.Namespace(
        target=target, project=_io._slug(target), source_type="auto",
        max_pages=12, max_depth=1, max_files=250, max_chars=120_000,
        chunk_words=450, chunk_overlap=70, fact_threshold=0.6,
        embed_provider="dual", embed_model="", login_if_needed=True, login_url="",
        success_selector=None, max_auto_bypass_attempts=3, max_auth_handoffs=3,
        browser_engine="chromium", click_discovery=False, max_clicks_per_page=20,
        crawl_mode="link-then-click",
    )
    try:
        manifest = lgwks_substrate.build_run(ns)
    except Exception as exc:
        return PhaseResult(name="ingest", ok=False, exit_code=2, message=str(exc))
    counts = manifest.get("counts", {})
    ok = int(counts.get("documents", 0) or 0) > 0 and int(counts.get("chunks", 0) or 0) > 0
    return PhaseResult(name="ingest", ok=ok, exit_code=0 if ok else 2,
                       message=f"{counts.get('documents', 0)} docs, {counts.get('chunks', 0)} chunks",
                       artifact={"run_id": manifest.get("run_id", ""), "counts": counts})


def _cap_review(step: dict[str, Any], repo: Path | None):
    # composer library = lgwks_do's leaf helpers (import-based phase runner, per spec §7)
    import lgwks_do
    return lgwks_do._run_review(repo or Path("."), bots="all", changed="", ref="HEAD",
                                json_out=True, l_budget=0.15)


CAPABILITIES = {
    "codebase": _cap_codebase,
    "ingest": _cap_ingest,
    "review": _cap_review,
}

# Generic dispatch routes any other engine-selected verb through the ONE
# canonical CLI table (lgwks build_parser → registered func), in-process and
# without subprocess (S4). This avoids re-deriving ~90 per-verb adapters; the
# dispatch table is the single source of truth.
_MAIN_PARSER = None


def _main_parser():
    global _MAIN_PARSER
    if _MAIN_PARSER is None:
        from importlib.machinery import SourceFileLoader
        main = SourceFileLoader("lgwks_main", str(Path(__file__).with_name("lgwks"))).load_module()
        _MAIN_PARSER = main.build_parser()
    return _MAIN_PARSER


def _cap_dispatch(step: dict[str, Any], repo: Path | None):
    import contextlib
    import io
    from lgwks_phase import PhaseResult
    verb = str(step.get("verb", ""))
    operand = str(step.get("args", {}).get("operand", "")
                  or step.get("args", {}).get("intent", ""))
    tokens = verb.split()
    parser = _main_parser()

    ns = None
    for argv in ([*tokens], ([*tokens, operand] if operand else None)):
        if argv is None:
            continue
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                ns = parser.parse_args(argv)
            break
        except SystemExit:
            ns = None
    if ns is None or not getattr(ns, "func", None):
        return PhaseResult(name=verb, ok=False, exit_code=2,
                           message="capability needs arguments not derivable from intent")

    if repo is not None and hasattr(ns, "repo") and not getattr(ns, "repo", None):
        ns.repo = str(repo)
    if hasattr(ns, "json"):  # machine-first (S6) where the verb supports it
        ns.json = True

    try:
        with contextlib.redirect_stdout(io.StringIO()) as cap_out:
            rc = ns.func(ns)
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 2
        cap_out = None
    except Exception as exc:  # an adapter raising is a failed phase, not a crash
        return PhaseResult(name=verb, ok=False, exit_code=2, message=str(exc)[:300])

    rc = rc if isinstance(rc, int) else 0
    captured = cap_out.getvalue() if cap_out is not None else ""
    return PhaseResult(name=verb, ok=(rc == 0), exit_code=rc,
                       message=f"{verb} rc={rc}", artifact={"stdout": captured[:4000]})


# ── RUN: the one composer (phases + guards S2/S4/S5; verdict) ────────────────
def compose(plan: dict[str, Any], repo: Path | None) -> tuple[int, list[dict[str, Any]]]:
    import contextlib
    import io
    from lgwks_phase import PhaseResult
    phases: list[PhaseResult] = []

    # S6 — machine-first: capabilities and gates may print human chatter to
    # stdout; the door's only stdout is its own lgwks.agent.v1 JSON envelope.
    # Capture everything here so a chatty `review`/AUP run can't corrupt it.
    with contextlib.redirect_stdout(io.StringIO()):
        # S2 — AUP gate before any network/ingest step
        if plan.get("effect_class") == "network":
            import lgwks_do
            target = ""
            for s in plan.get("steps", []):
                target = str(s.get("args", {}).get("target", "")) or target
            aup = lgwks_do._run_aup_check(text=target, json_out=True)
            phases.append(aup)
            if not aup.ok:
                return 3, [p.__dict__ for p in phases]

        if plan.get("kind") == "batch":
            # S4 — no shell: multiply runs argv via shlex, bounded
            import lgwks_multiply as mx
            for s in plan.get("steps", []):
                r = mx._run_one(str(s.get("args", {}).get("cmd", "")))
                phases.append(PhaseResult(name=f"sh:{s.get('risk','?')}", ok=bool(r.get("ok")),
                                          exit_code=0 if r.get("ok") else (r.get("rc") or 2),
                                          message=str(r.get("out", ""))[:400]))
        else:
            for s in plan.get("steps", []):
                cap = CAPABILITIES.get(s.get("verb", ""), _cap_dispatch)
                phases.append(cap(s, repo))

    rc = max((p.exit_code for p in phases), default=0)
    return rc, [p.__dict__ for p in phases]


# ── act: the door ────────────────────────────────────────────────────────────
def act(intent: str, *, repo: Path | None = None, top: int = 5,
        execute: bool = False, approve: bool = False, force: bool = False) -> dict[str, Any]:
    wv = worldview(intent, repo, top)
    plan = compile_plan(intent, wv)
    # The smart form: surface the daemon's canonical next-steps (computed from the
    # ONE work-capability registry × state) so the entrypoint GUIDES the agent —
    # rather than only emitting a single keyword-classified plan. Pure + sessionless
    # here (base menu); the daemon packet fills state when a session is live.
    import lgwks_daemon_store
    next_steps = lgwks_daemon_store.next_steps([])
    out: dict[str, Any] = {
        "schema": SCHEMA, "intent": intent, "worldview": wv, "plan": plan,
        "next_steps": next_steps,
        "executed": False, "blocked": False, "block_reason": "", "result": None,
    }

    # S3 — risk gate
    if (wv.get("risk") or {}).get("verdict") == "block":
        out["blocked"] = True
        out["block_reason"] = "risk gate blocked the intent"
        return out

    if not execute or not plan.get("steps"):
        return out

    # S1 — no NL → write/destructive auto-exec without explicit approval
    needs = plan.get("approval", "none")
    if needs == "once" and not (approve or force):
        out["blocked"] = True
        out["block_reason"] = "write/mutation plan requires --yes (approval:once)"
        return out
    if needs == "force" and not force:
        out["blocked"] = True
        out["block_reason"] = "destructive plan requires --force"
        return out

    rc, phases = compose(plan, repo)
    out["executed"] = True
    out["phases"] = phases
    out["ok"] = rc == 0
    return out


def agent_command(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else None
    result = act(
        args.intent, repo=repo, top=getattr(args, "top", 5),
        execute=getattr(args, "act", False),
        approve=getattr(args, "yes", False), force=getattr(args, "force", False),
    )
    print(json.dumps(result, indent=2, default=str))
    if result.get("blocked"):
        return 2
    return 0 if result.get("ok", True) else 2


def add_parser(sub) -> None:
    p = sub.add_parser("agent", help="single agent front door: world view, then trigger a workflow")
    p.add_argument("intent", help="natural-language intent")
    p.add_argument("--act", action="store_true", help="execute the compiled workflow (else: world view only)")
    p.add_argument("--yes", action="store_true", help="approve a write/mutation plan (approval:once)")
    p.add_argument("--force", action="store_true", help="approve a destructive plan")
    p.add_argument("--top", type=int, default=5, help="max capability selections/results")
    p.add_argument("--repo", metavar="PATH", help="repo path for state/index context")
    p.set_defaults(func=agent_command)
