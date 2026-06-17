"""lgwks_ops — consolidated operations and lifecycle workflows.

Provides unified implementations for:
  - health-check: doctor + store + env integrity
  - onboard: first-time machine setup
  - audit-trail: git history provenance
  - migration-check: breaking changes between versions

This module centralizes the "maintenance" logic that was previously duplicated
between lgwks_workflows.py and other surfaces.
"""

from __future__ import annotations

import argparse
import json
import subprocess as sp
import sys
import time
from pathlib import Path
from typing import Any

import lgwks_ui as ui
import lgwks_phase as phase
from lgwks_clock import now_iso as _now
from lgwks_repo import _is_repo

def health_check(json_out: bool = False) -> int:
    """Doctor + store + env integrity + manifest sanity."""
    import lgwks_manifest
    t0 = time.time()
    phases = []

    # 1. Doctor / Env
    try:
        import lgwks_browser
        ok, _ = lgwks_browser.available()
        p1 = phase.PhaseResult(name="doctor:env", ok=ok, exit_code=0 if ok else 2, 
                               message="browser available" if ok else "playwright missing")
    except Exception as exc:
        p1 = phase.PhaseResult(name="doctor:env", ok=False, exit_code=2, message=str(exc))
    phases.append(p1)

    # 2. Manifest sanity
    try:
        manifest = lgwks_manifest.manifest_command(argparse.Namespace(json=True, render=False, for_agent=False))
        p2 = phase.PhaseResult(name="manifest:sanity", ok=(manifest == 0), exit_code=manifest, 
                               message="manifest ok" if manifest == 0 else "manifest corrupted")
        phases.append(p2)
    except Exception as exc:
        phases.append(phase.PhaseResult(name="manifest:sanity", ok=False, exit_code=2, message=str(exc)))

    # 3. Cognition Log integrity
    try:
        import lgwks_cognition
        log = lgwks_cognition.CognitionLog("main")
        ok = log.verify()
        p3 = phase.PhaseResult(name="cognition:verify", ok=ok, exit_code=0 if ok else 1, 
                               message="chain ok" if ok else "chain broken")
        phases.append(p3)
    except Exception as exc:
        phases.append(phase.PhaseResult(name="cognition:verify", ok=False, exit_code=2, message=str(exc)))

    return _emit("health-check", phases, t0, json_out)

def onboard(skip_browser: bool = False, json_out: bool = False) -> int:
    """First-time machine setup."""
    import lgwks_keyvault
    t0 = time.time()
    phases = []

    if not skip_browser:
        try:
            res = sp.run(["playwright", "install", "chromium"], capture_output=True, text=True)
            ok = (res.returncode == 0)
            phases.append(phase.PhaseResult(name="onboard:browser", ok=ok, exit_code=res.returncode, 
                                           message="chromium installed" if ok else res.stderr))
        except Exception as exc:
            phases.append(phase.PhaseResult(name="onboard:browser", ok=False, exit_code=2, message=str(exc)))
    else:
        phases.append(phase.PhaseResult(name="onboard:browser", ok=True, exit_code=0, message="skipped"))

    try:
        kv = lgwks_keyvault.keyvault_command(argparse.Namespace(subcommand="check", name="openrouter", json=json_out))
        phases.append(phase.PhaseResult(name="onboard:keyvault", ok=(kv == 0), exit_code=kv, 
                                       message="keyvault ok" if kv == 0 else "keys missing"))
    except Exception as exc:
        phases.append(phase.PhaseResult(name="onboard:keyvault", ok=False, exit_code=2, message=str(exc)))

    return _emit("onboard", phases, t0, json_out)

def audit_trail(repo: Path, commits: int = 10, json_out: bool = False) -> int:
    """Pull git history ±N commits and generate audit report."""
    import lgwks_solve
    t0 = time.time()
    phases = []

    if not _is_repo(repo):
        phases.append(phase.PhaseResult(name="repo:check", ok=False, exit_code=4, message=f"{repo} is not a git repo"))
        return _emit("audit-trail", phases, t0, json_out)

    try:
        res = lgwks_solve.solve_command(argparse.Namespace(
            target="git", repo=str(repo), thought=f"audit last {commits} commits", json=json_out))
        phases.append(phase.PhaseResult(name="solve:provenance", ok=(res == 0), exit_code=res, 
                                       message="audit complete" if res == 0 else "audit failed"))
    except Exception as exc:
        phases.append(phase.PhaseResult(name="solve:provenance", ok=False, exit_code=2, message=str(exc)))

    return _emit("audit-trail", phases, t0, json_out)

def migration_check(repo: Path, from_ref: str = "HEAD~1", to_ref: str = "HEAD", json_out: bool = False) -> int:
    """Compare two codebase versions for breaking changes."""
    import lgwks_solve
    t0 = time.time()
    phases = []

    if not _is_repo(repo):
        phases.append(phase.PhaseResult(name="repo:check", ok=False, exit_code=4, message=f"{repo} is not a git repo"))
        return _emit("migration-check", phases, t0, json_out)

    try:
        res = lgwks_solve.solve_command(argparse.Namespace(
            target="git", repo=str(repo), thought=f"breaking changes between {from_ref} and {to_ref}", json=json_out))
        phases.append(phase.PhaseResult(name="solve:migration", ok=(res == 0), exit_code=res, 
                                       message="migration check complete" if res == 0 else "check failed"))
    except Exception as exc:
        phases.append(phase.PhaseResult(name="solve:migration", ok=False, exit_code=2, message=str(exc)))

    return _emit("migration-check", phases, t0, json_out)

def _emit(name: str, phases: list, t0: float, json_out: bool) -> int:
    verdict = phase.verdict_from_phases(phases)
    dur = time.time() - t0
    
    if json_out:
        print(json.dumps({
            "workflow": name,
            "phases": [p.__dict__ for p in phases],
            "verdict": verdict,
            "duration_sec": round(dur, 3),
            "ts": _now(),
        }, indent=2))
    else:
        on = ui.color_on()
        print("\n".join(ui.band(f"lgwks · {name}", _now(), on=on)))
        for p in phases:
            color = ui.EMERALD if p.ok else (ui.RUST if p.exit_code == 3 else ui.AMBER)
            print(f"  [{'PASS' if p.ok else 'FAIL'}] {p.name}: {p.message}")
        print(f"Verdict: {verdict.upper()} ({dur:.2f}s)")
    
    return max(p.exit_code for p in phases) if phases else 0

def add_parser(sub) -> None:
    p = sub.add_parser("lifecycle", help="lifecycle operations: health, onboard, audit, migration")
    ops_sub = p.add_subparsers(dest="ops_subcommand", required=True)

    # health
    health = ops_sub.add_parser("health", help="environment + store integrity check")
    health.add_argument("--json", action="store_true")
    health.set_defaults(func=lambda args: health_check(args.json))

    # onboard
    onb = ops_sub.add_parser("onboard", help="first-time setup")
    onb.add_argument("--skip-browser", action="store_true")
    onb.add_argument("--json", action="store_true")
    onb.set_defaults(func=lambda args: onboard(args.skip_browser, args.json))

    # audit
    aud = ops_sub.add_parser("audit", help="git history provenance")
    aud.add_argument("--repo", default=".")
    aud.add_argument("--commits", type=int, default=10)
    aud.add_argument("--json", action="store_true")
    aud.set_defaults(func=lambda args: audit_trail(Path(args.repo), args.commits, args.json))

    # migration
    mig = ops_sub.add_parser("migration", help="check for breaking changes")
    mig.add_argument("--repo", default=".")
    mig.add_argument("--from", dest="from_ref", default="HEAD~1")
    mig.add_argument("--to", dest="to_ref", default="HEAD")
    mig.add_argument("--json", action="store_true")
    mig.set_defaults(func=lambda args: migration_check(Path(args.repo), args.from_ref, args.to_ref, args.json))

    # cognition (observability!)
    cog = ops_sub.add_parser("cognition", help="inspect the AI cognition log")
    cog.add_argument("--stream", default="main")
    cog.add_argument("--json", action="store_true")
    cog.add_argument("--verify", action="store_true", help="verify log integrity")
    
    def _cog_cmd(args):
        import lgwks_cognition
        if args.verify:
            log = lgwks_cognition.CognitionLog(args.stream)
            ok = log.verify()
            print(f"Cognition log {args.stream!r} integrity: {'OK' if ok else 'BROKEN'}")
            return 0 if ok else 1
        res = lgwks_cognition.status(args.stream)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            on = ui.color_on()
            print("\n".join(ui.band("lgwks · cognition", args.stream, on=on)))
            for k, v in res.items():
                print(f"  {k:<12}: {v}")
        return 0
        
    cog.set_defaults(func=_cog_cmd)
