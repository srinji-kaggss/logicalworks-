"""lgwks_do — unified orchestrator: code, research, govern, cleanup, ship.

Runs multi-phase workflows by composing existing verbs programmatically.
No shell-outs: modules are imported and their command functions called directly.

Exit-code contract:
  0   all phases passed
  1   danger findings in review
  2   degraded / missing artifacts
  3   AUP deny or governance failure
  4   repo not found or other setup error

Machine output (--json) produces a DoRun artifact with per-phase results.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_repo import _is_repo


def _slugify(text: str) -> str:
    return re.sub(r"[^\w-]+", "-", text.lower()).strip("-").replace("--", "-")[:64]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    name: str
    ok: bool
    exit_code: int
    findings_count: int = 0
    message: str = ""
    artifact: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoRun:
    schema: str = "lgwks.do.run.v1"
    command: str = ""
    repo: str = "."
    phases: list[PhaseResult] = field(default_factory=list)
    verdict: str = "pass"   # pass | degraded | danger | deny | error
    exit_code: int = 0
    duration_sec: float = 0.0
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "command": self.command,
            "repo": self.repo,
            "phases": [
                {
                    "name": p.name,
                    "ok": p.ok,
                    "exit_code": p.exit_code,
                    "findings_count": p.findings_count,
                    "message": p.message,
                    "artifact": p.artifact,
                }
                for p in self.phases
            ],
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "duration_sec": round(self.duration_sec, 3),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_review_args(
    repo: Path,
    bots: str,
    changed: str = "",
    ref: str = "HEAD",
    json_out: bool = False,
    l_budget: float = 0.15,
    synth: bool = False,
) -> argparse.Namespace:
    """Build a argparse Namespace matching lgwks_review.review_command expectations."""
    ns = argparse.Namespace()
    ns.repo = str(repo)
    ns.ref = ref
    ns.json = json_out
    ns.yes = False
    ns.bots = bots
    ns.changed = changed
    ns.synth = synth
    ns.l_budget = l_budget
    ns.watch = False
    return ns


def _run_review(repo: Path, bots: str, changed: str, ref: str, json_out: bool, l_budget: float) -> PhaseResult:
    import lgwks_review
    ns = _build_review_args(repo, bots, changed=changed, ref=ref, json_out=json_out, l_budget=l_budget)
    t0 = time.time()
    try:
        code = lgwks_review.review_command(ns)
    except Exception as exc:
        return PhaseResult(name=f"review:{bots}", ok=False, exit_code=2, message=str(exc))
    dur = time.time() - t0
    # Infer findings count from generated report if possible
    findings = 0
    try:
        out = repo / "findings" / "machine-packet.json"
        if out.exists():
            with out.open("r", encoding="utf-8") as f:
                mp = json.load(f)
            findings = mp.get("grounded_claim_count", 0)
    except Exception:
        pass
    return PhaseResult(
        name=f"review:{bots}",
        ok=(code == 0),
        exit_code=code,
        findings_count=findings,
        message="pass" if code == 0 else ("danger" if code == 1 else "degraded"),
        artifact={"duration_sec": round(dur, 3)},
    )


def _run_aup_check(text: str = "", request_file: str = "", json_out: bool = False) -> PhaseResult:
    import lgwks_aup
    t0 = time.time()
    try:
        content = text
        if request_file:
            content = Path(request_file).read_text(encoding="utf-8")
        request = {
            "customer_id": "lgwks-do",
            "request_type": "intent",
            "content_preview": content[:32000],
        }
        result = lgwks_aup.AUPGate.load().check(request)
    except Exception as exc:
        return PhaseResult(name="aup:check", ok=False, exit_code=3, message=str(exc))
    dur = time.time() - t0
    ok = result.verdict in (lgwks_aup.Verdict.ALLOW, lgwks_aup.Verdict.REVIEW)
    return PhaseResult(
        name="aup:check",
        ok=ok,
        exit_code=0 if ok else 3,
        findings_count=0,
        message=result.verdict.value,
        artifact={
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "matched_rule": result.matched_rule.to_dict() if result.matched_rule else None,
            "duration_sec": round(dur, 3),
        },
    )


def _run_aup_audit(json_out: bool = False) -> PhaseResult:
    import lgwks_aup
    t0 = time.time()
    try:
        summary = lgwks_aup.AUPGate.load().export_audit()
    except Exception as exc:
        return PhaseResult(name="aup:audit", ok=False, exit_code=3, message=str(exc))
    dur = time.time() - t0
    return PhaseResult(
        name="aup:audit",
        ok=True,
        exit_code=0,
        findings_count=summary.get("refusal_count", 0),
        message=f"{summary.get('refusal_count', 0)} refusals, {summary.get('telemetry_count', 0)} telemetry",
        artifact={**summary, "duration_sec": round(dur, 3)},
    )


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _do_code(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 4
    run = DoRun(command="code", repo=str(repo), started_at=_now())
    t0 = time.time()
    changed = getattr(args, "changed", "")
    ref = getattr(args, "ref", "HEAD")
    json_out = getattr(args, "json", False)
    l_budget = float(getattr(args, "l_budget", 0.15))

    # Phase 1: code review (code_hacker bot only)
    p1 = _run_review(repo, bots="code_hacker", changed=changed, ref=ref, json_out=json_out, l_budget=l_budget)
    run.phases.append(p1)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = _verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


def _do_research(args: argparse.Namespace) -> int:
    # Phase 1: AUP check on the query text itself
    query = getattr(args, "query", "")
    json_out = getattr(args, "json", False)
    run = DoRun(command="research", repo=".", started_at=_now())
    t0 = time.time()

    if query:
        p1 = _run_aup_check(text=query, json_out=json_out)
        run.phases.append(p1)
        if not p1.ok:
            run.exit_code = 3
            run.verdict = "deny"
            run.duration_sec = time.time() - t0
            run.finished_at = _now()
            return _emit(run, json_out)

    # Phase 2: research execution via substrate if URL, else akinator stub
    is_url = bool(re.search(r"^https?://", query.strip()))
    if is_url:
        import lgwks_substrate
        sub_args = argparse.Namespace(
            target=query,
            project=slugify(query),
            source_type="auto",
            max_pages=12,
            max_depth=getattr(args, "depth", 1),
            max_files=250,
            max_chars=120_000,
            chunk_words=450,
            chunk_overlap=70,
            fact_threshold=0.6,
            embed_provider="deterministic",
            embed_model="",
            login_if_needed=True,
            login_url="",
            success_selector=None,
            max_auto_bypass_attempts=3,
            max_auth_handoffs=3,
            browser_engine="chromium",
            click_discovery=False,
            max_clicks_per_page=20,
            crawl_mode="link-then-click",
        )
        try:
            manifest = lgwks_substrate.build_run(sub_args)
            root = manifest.get("artifacts", {}).get("root", "")
            p2 = PhaseResult(
                name="substrate:research",
                ok=manifest.get("counts", {}).get("documents", 0) > 0,
                exit_code=0,
                message=f"{manifest.get('counts',{}).get('documents',0)} docs, {manifest.get('counts',{}).get('chunks',0)} chunks",
                artifact={
                    "run_id": manifest.get("run_id", ""),
                    "run_dir": root,
                    "manifest": str(Path(root) / "manifest.json") if root else "",
                    "counts": manifest.get("counts", {}),
                },
            )
        except Exception as exc:
            p2 = PhaseResult(name="substrate:research", ok=False, exit_code=2, message=str(exc))
    else:
        p2 = PhaseResult(name="research", ok=False, exit_code=2, message="akinator research requires the lgwks-akinator binary")
    run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = _verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


def _do_govern(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 4
    run = DoRun(command="govern", repo=str(repo), started_at=_now())
    t0 = time.time()
    text = getattr(args, "text", "")
    request_file = getattr(args, "request_file", "")
    changed = getattr(args, "changed", "")
    ref = getattr(args, "ref", "HEAD")
    json_out = getattr(args, "json", False)
    l_budget = float(getattr(args, "l_budget", 0.15))

    # Phase 1: AUP check on provided text/request
    if text or request_file:
        p1 = _run_aup_check(text=text, request_file=request_file, json_out=json_out)
        run.phases.append(p1)
        if not p1.ok:
            run.exit_code = 3
            run.verdict = "deny"
            run.duration_sec = time.time() - t0
            run.finished_at = _now()
            return _emit(run, json_out)

    # Phase 2: slop review on changed files
    p2 = _run_review(repo, bots="slop_math", changed=changed, ref=ref, json_out=json_out, l_budget=l_budget)
    run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = _verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


def _do_cleanup(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 4
    run = DoRun(command="cleanup", repo=str(repo), started_at=_now())
    t0 = time.time()
    changed = getattr(args, "changed", "")
    ref = getattr(args, "ref", "HEAD")
    json_out = getattr(args, "json", False)
    l_budget = float(getattr(args, "l_budget", 0.15))
    auto_fix = getattr(args, "auto_fix", False)

    # Phase 1: slop + optimizer review
    p1 = _run_review(repo, bots="slop_math,optimizer", changed=changed, ref=ref, json_out=json_out, l_budget=l_budget)
    run.phases.append(p1)

    # Phase 2: optional auto-fix (refactor remove_unused_imports)
    if auto_fix:
        p2 = _run_refactor(repo, "remove_unused_imports", changed=changed, json_out=json_out)
        run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = _verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


def _do_ship(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 4
    run = DoRun(command="ship", repo=str(repo), started_at=_now())
    t0 = time.time()
    changed = getattr(args, "changed", "")
    ref = getattr(args, "ref", "HEAD")
    json_out = getattr(args, "json", False)
    l_budget = float(getattr(args, "l_budget", 0.15))

    # Phase 1: full review (all bots)
    p1 = _run_review(repo, bots="all", changed=changed, ref=ref, json_out=json_out, l_budget=l_budget)
    run.phases.append(p1)

    # Phase 2: AUP audit (informational)
    p2 = _run_aup_audit(json_out=json_out)
    run.phases.append(p2)

    run.exit_code = max(p.exit_code for p in run.phases)
    run.verdict = _verdict_from_phases(run.phases)
    run.duration_sec = time.time() - t0
    run.finished_at = _now()
    return _emit(run, json_out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_refactor(repo: Path, task: str, changed: str = "", json_out: bool = False) -> PhaseResult:
    import lgwks_refactor
    ns = argparse.Namespace()
    ns.repo = str(repo)
    ns.task = task
    ns.dry_run = not getattr(ns, "yes", False)
    ns.json = json_out
    ns.changed = changed
    t0 = time.time()
    try:
        code = lgwks_refactor.refactor_command(ns)
    except Exception as exc:
        return PhaseResult(name=f"refactor:{task}", ok=False, exit_code=2, message=str(exc))
    dur = time.time() - t0
    return PhaseResult(name=f"refactor:{task}", ok=(code == 0), exit_code=code, message="pass" if code == 0 else "degraded", artifact={"duration_sec": round(dur, 3)})


def _verdict_from_phases(phases: list[PhaseResult]) -> str:
    codes = [p.exit_code for p in phases]
    if any(c == 3 for c in codes):
        return "deny"
    if any(c == 1 for c in codes):
        return "danger"
    if any(c == 2 for c in codes):
        return "degraded"
    if any(c == 4 for c in codes):
        return "error"
    return "pass"


def _emit(run: DoRun, json_out: bool) -> int:
    if json_out:
        print(json.dumps(run.to_dict(), indent=2))
        return run.exit_code
    on = ui.color_on()
    out = [""]
    out += ui.band("lgwks · do", f"{run.command}  {run.repo}", on=on)
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
    out.append("  " + ui.footer("lgwks · do", on=on))
    out.append("")
    print("\n".join(out))
    return run.exit_code


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def do_command(args: argparse.Namespace) -> int:
    sub = getattr(args, "do_subcommand", "")
    if sub == "code":
        return _do_code(args)
    if sub == "research":
        return _do_research(args)
    if sub == "govern":
        return _do_govern(args)
    if sub == "cleanup":
        return _do_cleanup(args)
    if sub == "ship":
        return _do_ship(args)
    print(f"error: unknown do subcommand {sub!r}", file=sys.stderr)
    return 4


def add_parser(sub) -> None:
    p = sub.add_parser("do", help="unified orchestrator: code, research, govern, cleanup, ship")
    do_sub = p.add_subparsers(dest="do_subcommand", required=True, help="workflow kind")

    # do code
    code = do_sub.add_parser("code", help="run code review (code_hacker) on changed files")
    code.add_argument("--repo", default=".", help="path to repo")
    code.add_argument("--changed", default="", help="comma-separated relative file paths")
    code.add_argument("--ref", default="HEAD", help="diff against this ref")
    code.add_argument("--json", action="store_true", help="structured DoRun JSON output")
    code.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    code.set_defaults(func=do_command)

    # do research
    research = do_sub.add_parser("research", help="run research query with AUP gate")
    research.add_argument("query", nargs="?", default="", help="research query string")
    research.add_argument("--depth", type=int, default=1, help="research depth")
    research.add_argument("--model", default="", help="model override")
    research.add_argument("--json", action="store_true", help="structured DoRun JSON output")
    research.set_defaults(func=do_command)

    # do govern
    govern = do_sub.add_parser("govern", help="AUP check + slop review before merge")
    govern.add_argument("--repo", default=".", help="path to repo")
    govern.add_argument("--text", default="", help="text to AUP-check")
    govern.add_argument("--request-file", default="", help="JSON request file to AUP-check")
    govern.add_argument("--changed", default="", help="comma-separated relative file paths")
    govern.add_argument("--ref", default="HEAD", help="diff against this ref")
    govern.add_argument("--json", action="store_true", help="structured DoRun JSON output")
    govern.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    govern.set_defaults(func=do_command)

    # do cleanup
    cleanup = do_sub.add_parser("cleanup", help="slop + optimizer review; optional auto-fix")
    cleanup.add_argument("--repo", default=".", help="path to repo")
    cleanup.add_argument("--changed", default="", help="comma-separated relative file paths")
    cleanup.add_argument("--ref", default="HEAD", help="diff against this ref")
    cleanup.add_argument("--json", action="store_true", help="structured DoRun JSON output")
    cleanup.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    cleanup.add_argument("--auto-fix", action="store_true", help="run safe refactor fixes")
    cleanup.set_defaults(func=do_command)

    # do ship
    ship = do_sub.add_parser("ship", help="full pre-ship: all bots + AUP audit")
    ship.add_argument("--repo", default=".", help="path to repo")
    ship.add_argument("--changed", default="", help="comma-separated relative file paths")
    ship.add_argument("--ref", default="HEAD", help="diff against this ref")
    ship.add_argument("--json", action="store_true", help="structured DoRun JSON output")
    ship.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget")
    ship.set_defaults(func=do_command)
