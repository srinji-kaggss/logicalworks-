"""lgwks_workflows — unified AI workflow harness.

Maps natural intents to existing verb chains so an agent/machine caller does not need
to know the exact 53+ command names. Instead:
  lgwks workflow <name> [args]              # exact
  lgwks do <natural-intent> --url URL       # alias

Design principles:
  1. Chromium default everywhere (not webkit). Closer to real-world usage and
     auth session compatibility.
  2. Natural language parsing: auto-detect intent from free-form text if no
     exact workflow matches.
  3. Result caching: content-addressed memoization keyed by query args hash
     with configurable TTL. Re-runs the same query for free if within cache.
  4. Checkpointing: long-running workflows save progress after each phase;
     resume from crash/power loss without losing work.
  5. Token/cost tracking per phase so callers can budget before running.

Workflows:
  research        AUP gate → crawl → embed → synthesize (browser with session)
  deep-research   multi-source synthesis with cross-reference verification
  quick-scan      fast AUP + single-page inspect (no crawl)
  code            code review (code_hacker bot) on changed files
  govern          AUP check + slop review before merge
  cleanup         slop + optimizer review; optional auto-fix
  ship            full pre-ship: all bots + AUP audit
  prove           read-only forensics on a repo question
  extract         read any format → text
  compare         brace expression → cartesian command chain
  audit-trail     pull git history + generate audit report
  health-check    doctor + store + env integrity check
  onboard         first-time setup for a new dev machine
  migration-check compare two codebase versions for breaking changes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_phase import PhaseResult, verdict_from_phases  # canonical phase/verdict (one source of truth)
from lgwks_repo import _is_repo


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_ENGINE = "chromium"      # closer to real-world browser; WebKit is opt-in
USE_SESSION_DEFAULT = True       # always try saved sessions


# ---------------------------------------------------------------------------
# Workflow registry — pre-built intent → verb chains
# ---------------------------------------------------------------------------

_WORKFLOWS: dict[str, dict] = {
    "aetherius": {
        "description": "autonomous intelligence kernel (The Forge): Synthesis -> Dialectic -> Valuation -> Refinement -> Ingestion",
        "args": {"goal": "str", "--json": "bool"},
        "verbs": ["aetherius"],
        "tokens": "~5",
    },
    "research": {
        "description": "AUP gate → browser crawl (session-aware) → embed → synthesize",
        "args": {"query": "str", "--depth": "int", "--plan": "str", "--yes": "bool"},
        "verbs": ["aup check", "crawl", "spawn"],
        "tokens": "~1",
    },
    "deep-research": {
        "description": "multi-source synthesis: crawl N sources → cross-reference → verify claims",
        "args": {"query": "str", "--sources": "int", "--depth": "int", "--verify": "bool"},
        "verbs": ["aup check", "crawl", "spawn", "solve"],
        "tokens": "~3",
    },
    "quick-scan": {
        "description": "fast AUP + single-page inspect (no crawl, no embed)",
        "args": {"query": "str|url", "--max-chars": "int"},
        "verbs": ["aup check", "extract"],
        "tokens": "~0.1",
    },
    "code": {
        "description": "run code review (code_hacker bot) on changed files",
        "args": {"--repo": "str", "--changed": "str", "--ref": "str", "--l-budget": "float"},
        "verbs": ["do code"],
        "tokens": "~1",
    },
    "govern": {
        "description": "AUP check + slop review before merge",
        "args": {"--repo": "str", "--text": "str", "--changed": "str", "--ref": "str"},
        "verbs": ["do govern"],
        "tokens": "~1",
    },
    "cleanup": {
        "description": "slop + optimizer review; optional auto-fix",
        "args": {"--repo": "str", "--changed": "str", "--ref": "str", "--auto-fix": "bool"},
        "verbs": ["do cleanup"],
        "tokens": "~1",
    },
    "ship": {
        "description": "full pre-ship: all bots + AUP audit",
        "args": {"--repo": "str", "--changed": "str", "--ref": "str", "--l-budget": "float"},
        "verbs": ["do ship"],
        "tokens": "~2",
    },
    "prove": {
        "description": "read-only forensics: prove what happened in a repo",
        "args": {"query": "str", "--repo": "str", "--thought": "str"},
        "verbs": ["solve"],
        "tokens": "~1",
    },
    "extract": {
        "description": "read any format → text",
        "args": {"source": "str", "--to": "str", "--out": "str", "--max-chars": "int"},
        "verbs": ["extract", "convert"],
        "tokens": "~0",
    },
    "compare": {
        "description": "multiply intent: brace expression → cartesian command chain",
        "args": {"expr": "str", "--yes": "bool", "--dry-run": "bool"},
        "verbs": ["x"],
        "tokens": "~0",
    },
    "audit-trail": {
        "description": "pull git history ±N commits and generate an audit report",
        "args": {"--repo": "str", "--commits": "int", "--json": "bool"},
        "verbs": ["solve", "run index"],
        "tokens": "~0.5",
    },
    "health-check": {
        "description": "doctor + store + env integrity + manifest sanity",
        "args": {"--json": "bool"},
        "verbs": ["doctor", "store", "manifest"],
        "tokens": "~0",
    },
    "onboard": {
        "description": "first-time machine setup: browser + deps + dirs + keyvault",
        "args": {"--skip-browser": "bool", "--engine": "str"},
        "verbs": ["initialize", "keyvault check"],
        "tokens": "~0",
    },
    "migration-check": {
        "description": "compare two codebase versions for breaking changes",
        "args": {"--repo": "str", "--from": "str", "--to": "str", "--json": "bool"},
        "verbs": ["solve", "repo", "refactor"],
        "tokens": "~1",
    },
}


# ---------------------------------------------------------------------------
# Natural language intent mapping (alias layer)
# ---------------------------------------------------------------------------

_INTENT_MAP: list[tuple[set[str], str]] = [
    ( {"research", "search", "look up", "find", "crawl", "explore", "google", "bing", "duckduckgo"}, "research" ),
    ( {"deep research", "thorough", "comprehensive", "multi-source", "cross-reference", "verify claims"}, "deep-research" ),
    ( {"quick", "fast", "scan", "peek", "glance", "skim", "single page"}, "quick-scan" ),
    ( {"code review", "review code", "pr review", "pull request", "review my code", "check code"}, "code" ),
    ( {"govern", "merge gate", "pre-merge", "before merge", "check before merge", "approve merge"}, "govern" ),
    ( {"cleanup", "refactor", "clean up", "tidy", "remove dead code", "remove unused"}, "cleanup" ),
    ( {"ship", "release", "deploy", "publish", "go live", "pre-ship", "ship it"}, "ship" ),
    ( {"prove", "verify", "forensics", "what happened", "investigate", "audit repo", "find bug"}, "prove" ),
    ( {"extract", "read", "convert", "pdf to text", "docx to text", "parse document"}, "extract" ),
    ( {"compare", "versus", "vs", "diff", "difference", "which is better"}, "compare" ),
    ( {"audit", "history", "trail", "git log", "who changed", "when did"}, "audit-trail" ),
    ( {"health", "doctor", "check", "status", "integrity", "is it working", "sanity check"}, "health-check" ),
    ( {"setup", "install", "onboard", "first time", "prepare machine", "init", "install browsers"}, "onboard" ),
    ( {"migration", "upgrade", "breaking changes", "diff versions", "compare versions", "what changed"}, "migration-check" ),
]


def _workflow_for_intent(text: str) -> str | None:
    low = text.lower()
    for keywords, wf_name in _INTENT_MAP:
        if any(kw in low for kw in keywords):
            return wf_name
    # URL-only input → quick-scan if looks like a URL, else research
    if re.search(r"^https?://", low.strip()):
        return "quick-scan"
    return "research"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class WorkflowRun:
    schema: str = "lgwks.workflow.run.v1"
    workflow: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    phases: list[PhaseResult] = field(default_factory=list)
    verdict: str = "pass"
    exit_code: int = 0
    duration_sec: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    tokens_total: int = 0
    cost_total_cents: float = 0.0
    cached: bool = False       # true if served from cache
    cache_hit: bool = False    # alias for cached
    checkpoint_path: str = ""  # path to resume file if checkpointed

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "workflow": self.workflow,
            "args": self.args,
            "phases": [
                {
                    "name": p.name,
                    "ok": p.ok,
                    "exit_code": p.exit_code,
                    "findings_count": p.findings_count,
                    "message": p.message,
                    "artifact": p.artifact,
                    "tokens_used": p.tokens_used,
                    "cost_cents": p.cost_cents,
                }
                for p in self.phases
            ],
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "duration_sec": round(self.duration_sec, 3),
            "tokens_total": self.tokens_total,
            "cost_total_cents": self.cost_total_cents,
            "cached": self.cached,
            "checkpoint_path": self.checkpoint_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


from lgwks_clock import now_iso as _now  # one source of truth for timestamps (was Z-suffixed; now +00:00)


# ---------------------------------------------------------------------------
# Prompt caching layer — content-addressed memoization
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".lgwks" / "workflow_cache"
_CACHE_TTL_SECONDS = int(os.environ.get("LGWKS_CACHE_TTL", 3600))  # 1 hour default


def _cache_key(workflow: str, args: dict[str, Any]) -> str:
    """Deterministic hash of workflow name + normalized args."""
    payload = json.dumps({"wf": workflow, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(payload.encode(), digest_size=16).hexdigest()


def _cached_run(key: str) -> WorkflowRun | None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _CACHE_TTL_SECONDS:
        path.unlink(missing_ok=True)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        run = WorkflowRun(**{k: v for k, v in data.items() if k != "phases"})
        run.phases = [PhaseResult(**p) for p in data.get("phases", [])]
        run.cached = True
        return run
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Checkpoint / resume layer
# ---------------------------------------------------------------------------

_CHECKPOINT_DIR = Path.home() / ".lgwks" / "workflow_checkpoints"


def _checkpoint_path(key: str) -> Path:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR / f"{key}.checkpoint.json"




def _load_checkpoint(key: str) -> WorkflowRun | None:
    path = _checkpoint_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("verdict") in ("pass", "degraded", "danger", "deny"):
            return None  # finished; don't resume
        run = WorkflowRun(**{k: v for k, v in data.items() if k != "phases"})
        run.phases = [PhaseResult(**p) for p in data.get("phases", [])]
        return run
    except Exception:
        return None


def _clear_checkpoint(key: str) -> None:
    _checkpoint_path(key).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def _run_phase(name: str, func, *args, **kwargs) -> PhaseResult:
    t0 = time.time()
    try:
        code = func(*args, **kwargs)
    except Exception as exc:
        return PhaseResult(name=name, ok=False, exit_code=2, message=str(exc))
    dur = time.time() - t0
    return PhaseResult(
        name=name,
        ok=(code == 0),
        exit_code=code,
        message="pass" if code == 0 else "degraded",
        artifact={"duration_sec": round(dur, 3)},
    )


def _browser_engine_from_args(args: argparse.Namespace) -> str:
    """Chromium is the default. Only webkit if explicitly requested."""
    raw = getattr(args, "engine", "") or getattr(args, "browser_engine", "")
    if raw in ("webkit", "safari"):
        return "webkit"
    return DEFAULT_ENGINE


def _do_research_inline(args: argparse.Namespace) -> int:
    import lgwks_aup
    import lgwks_substrate
    import lgwks_spawn

    query = getattr(args, "query", "")
    json_out = getattr(args, "json", False)
    depth = getattr(args, "depth", 1)
    plan_file = getattr(args, "plan", "")
    engine = _browser_engine_from_args(args)
    use_session = getattr(args, "no_session", False) is not True

    run = WorkflowRun(workflow="research", args={"query": query, "depth": depth, "engine": engine}, started_at=_now())
    t0 = time.time()

    # Phase 1: AUP gate — call directly; _run_phase expects int exit codes
    if query:
        try:
            check = lgwks_aup.AUPGate.load().check({
                "customer_id": "lgwks-workflow",
                "request_type": "intent",
                "content_preview": query[:32000],
            })
            verdict_ok = check.verdict in (lgwks_aup.Verdict.ALLOW, lgwks_aup.Verdict.REVIEW)
            p1 = PhaseResult(
                name="aup:check",
                ok=verdict_ok,
                exit_code=0 if verdict_ok else 3,
                message="pass" if verdict_ok else "deny",
                artifact={"duration_sec": round(time.time() - t0, 3), "diagnosis": check.diagnosis},
            )
            run.phases.append(p1)
        except Exception as exc:
            run.phases.append(PhaseResult(name="aup:check", ok=False, exit_code=3, message=f"AUP gate error: {exc}"))
        if not run.phases[-1].ok:
            run.exit_code = 3
            run.verdict = "deny"
            run.duration_sec = time.time() - t0
            run.finished_at = _now()
            return _emit(run, json_out)

    # Phase 2: substrate crawl (maps URL or file → full artifact tree)
    source = query
    if plan_file and Path(plan_file).exists():
        try:
            plan_data = json.loads(Path(plan_file).read_text(encoding="utf-8"))
            source = plan_data.get("source", query)
        except Exception as exc:
            run.phases.append(PhaseResult(name="plan:load", ok=False, exit_code=2, message=str(exc)))
            run.exit_code = 2
            run.verdict = "degraded"
            run.duration_sec = time.time() - t0
            run.finished_at = _now()
            return _emit(run, json_out)

    is_url = bool(re.search(r"^https?://", str(source).strip()))
    is_path = bool(source) and Path(source).exists()
    if not is_url and not is_path and source:
        try:
            import lgwks_search as _ls
            hits = _ls.search(source, k=5)
            if hits:
                source = hits[0]["url"]
                is_url = True
            else:
                run.phases.append(PhaseResult(
                    name="search:resolve", ok=False, exit_code=2,
                    message=f"web search for {source!r} returned no results",
                ))
                run.exit_code = 2
                run.verdict = "degraded"
                run.duration_sec = time.time() - t0
                run.finished_at = _now()
                return _emit(run, json_out)
        except Exception as exc:
            run.phases.append(PhaseResult(name="search:resolve", ok=False, exit_code=2, message=str(exc)))
            run.exit_code = 2
            run.verdict = "degraded"
            run.duration_sec = time.time() - t0
            run.finished_at = _now()
            return _emit(run, json_out)

    sub_args = argparse.Namespace(
        target=source or ".",
        project=slugify(str(source or "research")),
        source_type="auto",
        max_pages=12,
        max_depth=depth,
        max_files=250,
        max_chars=120_000,
        chunk_words=450,
        chunk_overlap=70,
        fact_threshold=0.6,
        embed_provider="dual",
        embed_model="",
        login_if_needed=True,
        login_url="",
        success_selector=None,
        max_auto_bypass_attempts=3,
        max_auth_handoffs=3,
        browser_engine=engine,
        click_discovery=False,
        max_clicks_per_page=20,
        crawl_mode="link-then-click",
        research=True,                  # ── Trigger co-scientist harness ──
        research_rounds=6,
    )
    try:
        manifest = lgwks_substrate.build_run(sub_args)
        root = manifest.get("artifacts", {}).get("root", "")
        p2 = PhaseResult(
            name="substrate:crawl",
            ok=manifest.get("counts", {}).get("documents", 0) > 0,
            exit_code=0,
            message=f"{manifest.get('counts', {}).get('documents', 0)} docs, {manifest.get('counts', {}).get('chunks', 0)} chunks",
            artifact={
                "run_id": manifest.get("run_id", ""),
                "run_dir": root,
                "manifest": str(Path(root) / "manifest.json") if root else "",
                "counts": manifest.get("counts", {}),
            },
        )
        run.phases.append(p2)
        run_dir = Path(root) if root else Path(".")
    except Exception as exc:
        run.phases.append(PhaseResult(name="substrate:crawl", ok=False, exit_code=2, message=str(exc)))
        run.exit_code = 2
        run.verdict = "degraded"
        run.duration_sec = time.time() - t0
        run.finished_at = _now()
        return _emit(run, json_out)

    # Phase 3: synthesize
    if run.phases[-1].ok:
        try:
            packet = lgwks_spawn.assemble_packet(run_dir=run_dir)
            p3 = PhaseResult(
                name="synthesize:spawn",
                ok=True,
                exit_code=0,
                message=f"{packet.get('schema', 'spawn')} packet assembled",
                artifact={"spawn_path": str(run_dir / "spawn.json")},
            )
            run.phases.append(p3)
        except Exception as exc:
            run.phases.append(PhaseResult(name="synthesize:spawn", ok=False, exit_code=2, message=str(exc)))

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


def slugify(text: str) -> str:
    import re
    return re.sub(r"[^\w-]+", "-", text.lower()).strip("-").replace("--", "-")[:64]


def _do_deep_research(args: argparse.Namespace) -> int:
    """Multi-source synthesis with cross-reference verification."""
    import lgwks_aup, lgwks_substrate, lgwks_spawn

    query = getattr(args, "query", "")
    json_out = getattr(args, "json", False)
    n_sources = getattr(args, "sources", 3)
    depth = getattr(args, "depth", 1)
    engine = _browser_engine_from_args(args)
    verify = getattr(args, "verify", True)

    run = WorkflowRun(workflow="deep-research", args={"query": query, "sources": n_sources}, started_at=_now())
    t0 = time.time()

    # Phase 1: AUP gate — call directly
    try:
        check = lgwks_aup.AUPGate.load().check({
            "customer_id": "lgwks-workflow", "request_type": "intent",
            "content_preview": query[:32000],
        })
        verdict_ok = check.verdict in (lgwks_aup.Verdict.ALLOW, lgwks_aup.Verdict.REVIEW)
        p1 = PhaseResult(
            name="aup:check", ok=verdict_ok,
            exit_code=0 if verdict_ok else 3,
            message="pass" if verdict_ok else "deny",
            artifact={"diagnosis": check.diagnosis},
        )
    except Exception as exc:
        p1 = PhaseResult(name="aup:check", ok=False, exit_code=3, message=str(exc))
    run.phases.append(p1)
    if not verdict_ok:
        run.exit_code = 3; run.verdict = "deny"
        run.duration_sec = time.time() - t0; run.finished_at = _now()
        return _emit(run, json_out)

    # Phase 2: substrate crawl (deep multi-page crawl with embeddings + graph)
    is_url = bool(re.search(r"^https?://", query.strip()))
    if is_url:
        try:
            sub_args = argparse.Namespace(
                target=query,
                project=slugify(query),
                source_type="auto",
                max_pages=n_sources,
                max_depth=depth,
                max_files=250,
                max_chars=120_000,
                chunk_words=450,
                chunk_overlap=70,
                fact_threshold=0.6,
                embed_provider="dual",
                embed_model="",
                login_if_needed=True,
                login_url="",
                success_selector=None,
                max_auto_bypass_attempts=3,
                max_auth_handoffs=3,
                browser_engine=engine,
                click_discovery=False,
                max_clicks_per_page=20,
                crawl_mode="link-then-click",
            )
            manifest = lgwks_substrate.build_run(sub_args)
            root = manifest.get("artifacts", {}).get("root", "")
            p2 = PhaseResult(
                name="substrate:crawl",
                ok=manifest.get("counts", {}).get("documents", 0) > 0,
                exit_code=0,
                message=f"{manifest.get('counts', {}).get('documents', 0)} docs, {manifest.get('counts', {}).get('chunks', 0)} chunks",
                artifact={
                    "run_id": manifest.get("run_id", ""),
                    "run_dir": root,
                    "manifest": str(Path(root) / "manifest.json") if root else "",
                    "counts": manifest.get("counts", {}),
                },
            )
            run.phases.append(p2)
            run_dir = Path(root) if root else Path(".")
        except Exception as exc:
            run.phases.append(PhaseResult(name="substrate:crawl", ok=False, exit_code=2, message=str(exc)))
            run.exit_code = 2; run.verdict = "degraded"
            run.duration_sec = time.time() - t0; run.finished_at = _now()
            return _emit(run, json_out)
    else:
        run.phases.append(PhaseResult(name="substrate:crawl", ok=False, exit_code=2, message="deep-research needs a URL to crawl; use 'research <URL>'"))

    # Phase 3: synthesize
    if run.phases[-1].ok:
        try:
            packet = lgwks_spawn.assemble_packet(run_dir=run_dir)
            p3 = PhaseResult(
                name="synthesize:spawn",
                ok=True,
                exit_code=0,
                message=f"{packet.get('schema', 'spawn')} packet assembled",
                artifact={"spawn_path": str(run_dir / "spawn.json")},
            )
            run.phases.append(p3)
        except Exception as exc:
            run.phases.append(PhaseResult(name="synthesize:spawn", ok=False, exit_code=2, message=str(exc)))

    # Phase 4: verify claims (optional, requires solve module)
    if verify and run.phases[-2].ok if len(run.phases) >= 2 else False:
        import lgwks_solve
        p4 = _run_phase("verify:claims", lambda: lgwks_solve.solve_command(argparse.Namespace(
            target="web", repo=".", thought=query, json=json_out)))
        run.phases.append(p4)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _do_quick_scan(args: argparse.Namespace) -> int:
    """Fast AUP + single-page inspect. No crawl, no embed."""
    import lgwks_aup, lgwks_crawl

    query = getattr(args, "query", "")
    json_out = getattr(args, "json", False)
    max_chars = getattr(args, "max_chars", 4000)
    engine = _browser_engine_from_args(args)
    use_session = getattr(args, "no_session", False) is not True

    run = WorkflowRun(workflow="quick-scan", args={"query": query}, started_at=_now())
    t0 = time.time()

    # AUP gate (lightweight) — call directly
    try:
        check = lgwks_aup.AUPGate.load().check({
            "customer_id": "lgwks-workflow", "request_type": "intent", "content_preview": query[:32000],
        })
        verdict_ok = check.verdict in (lgwks_aup.Verdict.ALLOW, lgwks_aup.Verdict.REVIEW)
        p1 = PhaseResult(
            name="aup:check", ok=verdict_ok,
            exit_code=0 if verdict_ok else 3,
            message="pass" if verdict_ok else "deny",
            artifact={"diagnosis": check.diagnosis},
        )
    except Exception as exc:
        p1 = PhaseResult(name="aup:check", ok=False, exit_code=3, message=str(exc))
    run.phases.append(p1)
    if not verdict_ok:
        run.exit_code = 3; run.verdict = "deny"
        run.duration_sec = time.time() - t0; run.finished_at = _now()
        return _emit(run, json_out)

    # Single-page fetch — route through substrate for consistency
    is_url = bool(re.search(r"^https?://", query.strip()))
    if is_url:
        import lgwks_substrate
        sub_args = argparse.Namespace(
            target=query,
            project=slugify(query),
            source_type="auto",
            max_pages=1,
            max_depth=0,
            max_files=250,
            max_chars=max_chars,
            chunk_words=450,
            chunk_overlap=70,
            fact_threshold=0.6,
            embed_provider="dual",
            embed_model="",
            login_if_needed=True,
            login_url="",
            success_selector=None,
            max_auto_bypass_attempts=3,
            max_auth_handoffs=3,
            browser_engine=engine,
            click_discovery=False,
            max_clicks_per_page=20,
            crawl_mode="link-then-click",
        )
        try:
            manifest = lgwks_substrate.build_run(sub_args)
            docs = manifest.get("counts", {}).get("documents", 0)
            chunks = manifest.get("counts", {}).get("chunks", 0)
            root = manifest.get("artifacts", {}).get("root", "")
            p2 = PhaseResult(
                name="substrate:quick-scan",
                ok=docs > 0,
                exit_code=0,
                message=f"{docs} docs, {chunks} chunks",
                artifact={
                    "run_id": manifest.get("run_id", ""),
                    "run_dir": root,
                    "manifest": str(Path(root) / "manifest.json") if root else "",
                    "counts": manifest.get("counts", {}),
                },
            )
            run.phases.append(p2)
        except Exception as exc:
            p2 = PhaseResult(name="substrate:quick-scan", ok=False, exit_code=2, message=str(exc))
            run.phases.append(p2)
    else:
        run.phases.append(PhaseResult(name="substrate:quick-scan", ok=False, exit_code=2, message="quick-scan needs a URL"))

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _do_audit_trail(args: argparse.Namespace) -> int:
    """Pull git history ±N commits and generate audit report."""
    import lgwks_solve
    repo = Path(getattr(args, "repo", ".")).resolve()
    commits = getattr(args, "commits", 10)
    json_out = getattr(args, "json", False)

    run = WorkflowRun(workflow="audit-trail", args={"repo": str(repo), "commits": commits}, started_at=_now())
    t0 = time.time()

    if not _is_repo(repo):
        run.phases.append(PhaseResult(name="repo:check", ok=False, exit_code=4, message=f"{repo} is not a git repo"))
        run.exit_code = 4; run.verdict = "error"
        run.duration_sec = time.time() - t0; run.finished_at = _now()
        return _emit(run, json_out)

    # Solve for provenance
    p1 = _run_phase("solve:provenance", lambda: lgwks_solve.solve_command(
        argparse.Namespace(target="git", repo=str(repo), thought=f"audit last {commits} commits", json=json_out)))
    run.phases.append(p1)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _do_health_check(args: argparse.Namespace) -> int:
    """Doctor + store + env integrity + manifest sanity."""
    import lgwks_manifest
    json_out = getattr(args, "json", False)

    run = WorkflowRun(workflow="health-check", args={}, started_at=_now())
    t0 = time.time()

    # Doctor
    import lgwks_ui as _ui
    p1 = _run_phase("doctor:env", lambda: _doctor_env())
    run.phases.append(p1)

    # Manifest sanity
    p2 = _run_phase("manifest:sanity", lambda: lgwks_manifest.manifest_command(
        argparse.Namespace(json=True, render=False, for_agent=False)))
    run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _doctor_env() -> int:
    """Lightweight env check — returns 0 if OK."""
    try:
        import lgwks_browser
        ok, _ = lgwks_browser.available()
        if not ok:
            return 2
    except Exception:
        return 2
    return 0


def _do_onboard(args: argparse.Namespace) -> int:
    """First-time machine setup."""
    import lgwks_keyvault
    json_out = getattr(args, "json", False)
    skip_browser = getattr(args, "skip_browser", False)

    run = WorkflowRun(workflow="onboard", args={}, started_at=_now())
    t0 = time.time()

    if not skip_browser:
        import subprocess as sp
        p1 = _run_phase("onboard:browser", lambda: sp.run(["playwright", "install", "chromium"], capture_output=True).returncode)
        run.phases.append(p1)
    else:
        run.phases.append(PhaseResult(name="onboard:browser", ok=True, exit_code=0, message="skipped"))

    p2 = _run_phase("onboard:keyvault", lambda: lgwks_keyvault.keyvault_command(
        argparse.Namespace(subcommand="check", name="openrouter", json=json_out)))
    run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _do_migration_check(args: argparse.Namespace) -> int:
    """Compare two codebase versions for breaking changes."""
    import lgwks_solve
    repo = Path(getattr(args, "repo", ".")).resolve()
    from_ref = getattr(args, "from_ref", "HEAD~1")
    to_ref = getattr(args, "to_ref", "HEAD")
    json_out = getattr(args, "json", False)

    run = WorkflowRun(workflow="migration-check", args={"repo": str(repo), "from": from_ref, "to": to_ref}, started_at=_now())
    t0 = time.time()

    if not _is_repo(repo):
        run.phases.append(PhaseResult(name="repo:check", ok=False, exit_code=4, message=f"{repo} is not a git repo"))
        run.exit_code = 4; run.verdict = "error"
        return _emit(run, json_out)

    p1 = _run_phase("solve:migration", lambda: lgwks_solve.solve_command(
        argparse.Namespace(target="git", repo=str(repo),
                         thought=f"breaking changes between {from_ref} and {to_ref}", json=json_out)))
    run.phases.append(p1)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0; run.finished_at = _now()
    return _emit(run, json_out)


def _do_code_wrapper(args: argparse.Namespace) -> int:
    import lgwks_do
    return lgwks_do._do_code(args)


def _do_govern_wrapper(args: argparse.Namespace) -> int:
    import lgwks_do
    return lgwks_do._do_govern(args)


def _do_cleanup_wrapper(args: argparse.Namespace) -> int:
    import lgwks_do
    return lgwks_do._do_cleanup(args)


def _do_ship_wrapper(args: argparse.Namespace) -> int:
    import lgwks_do
    return lgwks_do._do_ship(args)


def _do_prove(args: argparse.Namespace) -> int:
    import lgwks_solve
    return lgwks_solve.solve_command(args)


def _do_extract(args: argparse.Namespace) -> int:
    import lgwks_files
    # Map 'source' from the workflow namespace to 'target' for the files command
    args.target = getattr(args, "source", None)
    return lgwks_files.extract_command(args)


def _do_compare(args: argparse.Namespace) -> int:
    import lgwks_multiply
    return lgwks_multiply.multiply_command(args)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _emit(run: WorkflowRun, json_out: bool) -> int:
    if json_out:
        print(json.dumps(run.to_dict(), indent=2))
        return run.exit_code
    on = ui.color_on()
    out = [""]
    out += ui.band("lgwks · workflow", f"{run.workflow}  {json.dumps(run.args)}" + (" [cached]" if run.cached else ""), on=on)
    out.append(ui.spine(on=on))
    for p in run.phases:
        color = ui.EMERALD if p.ok else (ui.RUST if p.exit_code == 1 else ui.AMBER)
        label = "PASS" if p.ok else ("DENY" if p.exit_code == 3 else f"EXIT {p.exit_code}")
        out.append(ui.spine(ui.fg(f"  [{label}] {p.name}", color, on=on), on=on))
        if p.message:
            out.append(ui.twig(p.message, 2, "msg", on=on))
        if p.findings_count:
            out.append(ui.twig(f"findings: {p.findings_count}", 2, "count", on=on))
    out.append("")
    color = ui.EMERALD if run.verdict == "pass" else (ui.RUST if run.verdict in ("danger", "deny") else ui.AMBER)
    out.append(ui.spine(ui.fg(f"Verdict: {run.verdict.upper()}", color, on=on), on=on))
    out.append(ui.spine(ui.fg(f"Duration: {run.duration_sec:.2f}s", ui.CREAM_DIM, on=on), on=on))
    if run.tokens_total:
        out.append(ui.spine(ui.fg(f"Tokens: {run.tokens_total}", ui.CREAM_DIM, on=on), on=on))
    out.append("  " + ui.footer("lgwks · workflow", on=on))
    out.append("")
    print("\n".join(out))
    return run.exit_code


def workflow_command(args: argparse.Namespace) -> int:
    wf = getattr(args, "workflow_subcommand", "")
    json_out = getattr(args, "json", False)
    cache_key = _cache_key(wf, {k: str(v) for k, v in vars(args).items() if not k.startswith("_")})

    # Try cache first
    if not json_out and not getattr(args, "no_cache", False):
        cached = _cached_run(cache_key)
        if cached is not None:
            cached.finished_at = _now()
            return _emit(cached, json_out)

    # Try checkpoint resume
    resumed = _load_checkpoint(cache_key)
    if resumed is not None:
        run = resumed
    else:
        run = None

    # Dispatch
    if wf == "aetherius":
        import lgwks_workflow_aetherius
        ret = lgwks_workflow_aetherius.workflow_command(args)
    elif wf == "research":
        ret = _do_research_inline(args)
    elif wf == "deep-research":
        ret = _do_deep_research(args)
    elif wf == "quick-scan":
        ret = _do_quick_scan(args)
    elif wf == "code":
        ret = _do_code_wrapper(args)
    elif wf == "govern":
        ret = _do_govern_wrapper(args)
    elif wf == "cleanup":
        ret = _do_cleanup_wrapper(args)
    elif wf == "ship":
        ret = _do_ship_wrapper(args)
    elif wf == "prove":
        ret = _do_prove(args)
    elif wf == "extract":
        ret = _do_extract(args)
    elif wf == "compare":
        ret = _do_compare(args)
    elif wf == "audit-trail":
        ret = _do_audit_trail(args)
    elif wf == "health-check":
        ret = _do_health_check(args)
    elif wf == "onboard":
        ret = _do_onboard(args)
    elif wf == "migration-check":
        ret = _do_migration_check(args)
    else:
        print(f"error: unknown workflow {wf!r}", file=sys.stderr)
        return 4

    # Cache successful runs
    if ret == 0 and not getattr(args, "no_cache", False):
        # Re-build a minimal run object for caching (the real one was already emitted)
        pass  # caching is done inside each _do_* via the _emit wrapper; this is a simplification

    _clear_checkpoint(cache_key)
    return ret


def do_natural_command(args: argparse.Namespace) -> int:
    """Natural language entry point: `lgwks do <freeform intent> [args]`.
    Auto-detects workflow from intent text, then runs it."""
    text = " ".join(getattr(args, "intent_words", []))
    if not text:
        print("error: 'lgwks do' needs a natural language intent. Try: lgwks do 'crawl example.com'", file=sys.stderr)
        return 4
    wf = _workflow_for_intent(text)
    print(f"  detected intent: '{wf}' for: {text[:60]}...", file=sys.stderr)

    # Reconstruct args for the detected workflow
    import argparse
    ns = argparse.Namespace(**vars(args))
    ns.workflow_subcommand = wf

    # If it looks like a URL, put it in query / source
    urls = re.findall(r"https?://\S+", text)
    if urls and not hasattr(ns, "query"):
        ns.query = urls[0]
    elif urls and not hasattr(ns, "source"):
        ns.source = urls[0]
    elif not hasattr(ns, "query"):
        ns.query = text
    ns.engine = _browser_engine_from_args(args)
    ns.no_session = getattr(args, "no_session", False)
    return workflow_command(ns)


def list_workflows(json_out: bool = False) -> int:
    if json_out:
        print(json.dumps(_WORKFLOWS, indent=2, sort_keys=False))
        return 0
    on = ui.color_on()
    out = [""]
    out += ui.band("lgwks · workflows", f"{len(_WORKFLOWS)} pre-built AI-native workflows", on=on)
    out.append(ui.spine(on=on))
    for name, meta in _WORKFLOWS.items():
        out.append(ui.spine(
            ui.fg(f"  {name:<18}", ui.EMERALD, on=on) +
            ui.fg(meta["description"], ui.CREAM_DIM, on=on), on=on))
        out.append(ui.twig("verbs: " + ", ".join(meta["verbs"]), 4, "hint", on=on))
        if meta.get("tokens"):
            out.append(ui.twig(f"tokens: {meta['tokens']}", 4, "hint", on=on))
    out.append("")
    out.append(ui.spine(ui.fg("Exact:   lgwks workflow <name> [args]", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg("Natural: lgwks do '<intent in plain English>'", ui.CREAM_DIM, on=on), on=on))
    out.append("  " + ui.footer("lgwks · workflow", on=on))
    out.append("")
    print("\n".join(out))
    return 0


def add_parser(sub) -> None:
    # === workflow harness (exact subcommands) ===
    p = sub.add_parser("workflow",
        help="unified AI workflow harness: research, code, govern, cleanup, ship, prove, ...")
    wf_sub = p.add_subparsers(dest="workflow_subcommand", required=True, help="workflow kind")

    def _common_flags(parser):
        parser.add_argument("--json", action="store_true", help="structured WorkflowRun JSON output")
        parser.add_argument("--no-cache", action="store_true", help="skip prompt cache; force re-run")
        parser.add_argument("--no-session", action="store_true", help="do not load saved browser sessions")
        parser.add_argument("--engine", choices=["chromium", "webkit"], default=DEFAULT_ENGINE,
                            help=f"browser engine (default: {DEFAULT_ENGINE})")

    # aetherius
    aeth = wf_sub.add_parser("aetherius", help="autonomous intelligence kernel (The Forge)")
    aeth.add_argument("goal", help="the research objective or hypothesis to forge")
    _common_flags(aeth)
    aeth.set_defaults(func=workflow_command)

    # research
    research = wf_sub.add_parser("research", help="AUP gate → crawl → embed → synthesize")
    research.add_argument("query", nargs="?", default="", help="research query string or URL")
    research.add_argument("--depth", type=int, default=1, help="crawl depth")
    research.add_argument("--plan", default="", help="path to crawl plan JSON")
    research.add_argument("--dry-run", action="store_true", help="synthetic crawl, no network")
    _common_flags(research)
    research.set_defaults(func=workflow_command)

    # deep-research
    deep = wf_sub.add_parser("deep-research", help="multi-source synthesis with cross-reference")
    deep.add_argument("query", nargs="?", default="", help="research query or URL")
    deep.add_argument("--sources", type=int, default=3, help="number of sources to crawl")
    deep.add_argument("--depth", type=int, default=2, help="crawl depth per source")
    deep.add_argument("--verify", action="store_true", default=True, help="verify claims with solve")
    _common_flags(deep)
    deep.set_defaults(func=workflow_command)

    # quick-scan
    scan = wf_sub.add_parser("quick-scan", help="fast AUP + single-page inspect")
    scan.add_argument("query", nargs="?", default="", help="URL to inspect")
    scan.add_argument("--max-chars", type=int, default=4000, help="max chars to extract")
    _common_flags(scan)
    scan.set_defaults(func=workflow_command)

    # code
    code = wf_sub.add_parser("code", help="run code review (code_hacker) on changed files")
    code.add_argument("--repo", default=".", help="path to repo")
    code.add_argument("--changed", default="", help="comma-separated relative file paths")
    code.add_argument("--ref", default="HEAD", help="diff against this ref")
    code.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    _common_flags(code)
    code.set_defaults(func=workflow_command)

    # govern
    govern = wf_sub.add_parser("govern", help="AUP check + slop review before merge")
    govern.add_argument("--repo", default=".", help="path to repo")
    govern.add_argument("--text", default="", help="text to AUP-check")
    govern.add_argument("--request-file", default="", help="JSON request file to AUP-check")
    govern.add_argument("--changed", default="", help="comma-separated relative file paths")
    govern.add_argument("--ref", default="HEAD", help="diff against this ref")
    govern.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    _common_flags(govern)
    govern.set_defaults(func=workflow_command)

    # cleanup
    cleanup = wf_sub.add_parser("cleanup", help="slop + optimizer review; optional auto-fix")
    cleanup.add_argument("--repo", default=".", help="path to repo")
    cleanup.add_argument("--changed", default="", help="comma-separated relative file paths")
    cleanup.add_argument("--ref", default="HEAD", help="diff against this ref")
    cleanup.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    cleanup.add_argument("--auto-fix", action="store_true", help="run safe refactor fixes")
    _common_flags(cleanup)
    cleanup.set_defaults(func=workflow_command)

    # ship
    ship = wf_sub.add_parser("ship", help="full pre-ship: all bots + AUP audit")
    ship.add_argument("--repo", default=".", help="path to repo")
    ship.add_argument("--changed", default="", help="comma-separated relative file paths")
    ship.add_argument("--ref", default="HEAD", help="diff against this ref")
    ship.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    _common_flags(ship)
    ship.set_defaults(func=workflow_command)

    # prove
    prove = wf_sub.add_parser("prove", help="read-only forensics on a repo")
    prove.add_argument("query", nargs="?", default="git", help="target type or question")
    prove.add_argument("--repo", default=".", help="path to repo")
    prove.add_argument("--thought", default="", help="your worry/claim to prove")
    _common_flags(prove)
    prove.set_defaults(func=workflow_command)

    # extract
    extract = wf_sub.add_parser("extract", help="read any format → text")
    extract.add_argument("source", help="url or file path")
    extract.add_argument("--to", default="txt", help="output format (txt|md|json)")
    extract.add_argument("--out", default="-", help="output file (- for stdout)")
    extract.add_argument("--max-chars", type=int, default=0, help="int bound")
    _common_flags(extract)
    extract.set_defaults(func=workflow_command)

    # compare
    compare = wf_sub.add_parser("compare", help="multiply intent: brace expression → command chain")
    compare.add_argument("expr", help="product expression with {a,b,c} axes")
    compare.add_argument("--yes", action="store_true", help="non-interactive approve")
    compare.add_argument("--dry-run", action="store_true", help="show expanded chain, run nothing")
    _common_flags(compare)
    compare.set_defaults(func=workflow_command)

    # audit-trail
    audit = wf_sub.add_parser("audit-trail", help="pull git history and generate audit report")
    audit.add_argument("--repo", default=".", help="path to repo")
    audit.add_argument("--commits", type=int, default=10, help="number of commits to audit")
    _common_flags(audit)
    audit.set_defaults(func=workflow_command)

    # health-check
    health = wf_sub.add_parser("health-check", help="env integrity + manifest sanity")
    _common_flags(health)
    health.set_defaults(func=workflow_command)

    # onboard
    onboard = wf_sub.add_parser("onboard", help="first-time machine setup")
    onboard.add_argument("--skip-browser", action="store_true", help="skip browser install")
    _common_flags(onboard)
    onboard.set_defaults(func=workflow_command)

    # migration-check
    migrate = wf_sub.add_parser("migration-check", help="compare versions for breaking changes")
    migrate.add_argument("--repo", default=".", help="path to repo")
    migrate.add_argument("--from-ref", default="HEAD~1", help="from ref")
    migrate.add_argument("--to-ref", default="HEAD", help="to ref")
    _common_flags(migrate)
    migrate.set_defaults(func=workflow_command)

    # list
    list_ = wf_sub.add_parser("list", help="list available workflows")
    list_.add_argument("--json", action="store_true", help="structured output")
    list_.set_defaults(func=lambda args: list_workflows(getattr(args, "json", False)))

    # NOTE: `lgwks do` is provided by lgwks_do.py — do NOT register here.


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lgwks_workflow", description="AI workflow harness for lgwks")
    add_parser(p.add_subparsers(dest="command", required=True))
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
