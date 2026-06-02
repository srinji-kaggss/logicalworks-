"""lgwks_intent — schema-driven intent router. A 10-line declaration drives automation.

The user writes an intent JSON (~10 lines). The CLI probes reality, matches `next_if`
conditions, and emits the ONE next action. No AI needed for routing; ML can enrich later.

//why: The user wants to say "what's next from GH issue 258" as ONE command, not 19.
This module makes that real: intent -> probe -> match -> act. The AI focuses on being
an AI, not a CLI debugger.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui


# ── intent schema ───────────────────────────────────────────────────────────

INTENT_SCHEMA = "lgwks.intent.v0"

# Probes are lightweight reality checks. Each returns (matched: bool, context: dict).
# Order matters: first match wins.


@dataclass
class IntentDoc:
    schema: str
    project: str = ""
    repo: str = ""
    issue: int = 0
    pr: int = 0
    context: list[str] = field(default_factory=list)
    goal: str = ""
    next_if: dict[str, str] = field(default_factory=dict)


@dataclass
class RouteResult:
    schema: str = "lgwks.intent.v0"
    intent: dict[str, Any] = field(default_factory=dict)
    probed_state: dict[str, Any] = field(default_factory=dict)
    matched_condition: str = ""
    next_action: str = ""
    next_cmd: str = ""
    reason: str = ""
    would_run: bool = False


# ── probes ───────────────────────────────────────────────────────────────────

def _probe_issue_open(repo: str, issue: int) -> tuple[bool, dict[str, Any]]:
    if not issue:
        return False, {}
    try:
        p = subprocess.run(
            ["gh", "issue", "view", str(issue), "--repo", repo, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if p.returncode == 0:
            data = json.loads(p.stdout)
            state = data.get("state", "").lower()
            return state == "open", {"state": state}
    except Exception:
        pass
    return False, {"_error": "probe failed"}


def _probe_issue_closed(repo: str, issue: int) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_issue_open(repo, issue)
    return not matched and ctx.get("state") == "closed", ctx


def _probe_tests_fail(cwd: Path) -> tuple[bool, dict[str, Any]]:
    try:
        p = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(cwd),
        )
        return p.returncode != 0, {"exit_code": p.returncode}
    except Exception:
        return False, {"_error": "probe failed"}


def _probe_tests_pass(cwd: Path) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_tests_fail(cwd)
    return not matched, ctx


def _probe_pr_draft(repo: str, pr: int) -> tuple[bool, dict[str, Any]]:
    if not pr:
        return False, {}
    try:
        p = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if p.returncode == 0:
            data = json.loads(p.stdout)
            state = data.get("state", "").lower()
            return state == "draft", {"state": state}
    except Exception:
        pass
    return False, {"_error": "probe failed"}


def _probe_review_danger(cwd: Path) -> tuple[bool, dict[str, Any]]:
    # Run lgwks review --json and check for danger findings
    try:
        p = subprocess.run(
            ["python", "-m", "lgwks", "review", "--repo", str(cwd), "--json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(cwd),
        )
        if p.returncode == 0 and p.stdout.strip():
            data = json.loads(p.stdout)
            findings = data.get("findings", [])
            danger = any(f.get("severity") == "danger" for f in findings)
            return danger, {"findings_count": len(findings), "danger": danger}
    except Exception:
        pass
    return False, {"_error": "probe failed"}


def _probe_dirty(cwd: Path) -> tuple[bool, dict[str, Any]]:
    try:
        p = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cwd),
        )
        dirty = bool(p.stdout.strip())
        return dirty, {"files_changed": len([l for l in p.stdout.splitlines() if l.strip()])}
    except Exception:
        return False, {"_error": "probe failed"}


def _probe_clean(cwd: Path) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_dirty(cwd)
    return not matched, ctx


_PROBE_MAP: dict[str, Any] = {
    "issue.open": _probe_issue_open,
    "issue.closed": _probe_issue_closed,
    "tests.fail": _probe_tests_fail,
    "tests.pass": _probe_tests_pass,
    "pr.draft": _probe_pr_draft,
    "review.danger": _probe_review_danger,
    "dirty": _probe_dirty,
    "clean": _probe_clean,
}


# ── router ───────────────────────────────────────────────────────────────────

def _resolve_intent(path: Path) -> IntentDoc:
    """Load and validate an intent file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != INTENT_SCHEMA:
        raise ValueError(f"expected schema {INTENT_SCHEMA}, got {raw.get('schema')!r}")
    return IntentDoc(
        schema=raw.get("schema", INTENT_SCHEMA),
        project=raw.get("project", ""),
        repo=raw.get("repo", ""),
        issue=raw.get("issue", 0),
        pr=raw.get("pr", 0),
        context=raw.get("context", []),
        goal=raw.get("goal", ""),
        next_if=raw.get("next_if", {}),
    )


def _substitute(cmd: str, intent: IntentDoc) -> str:
    """Replace {issue}, {pr}, {repo}, {project} with intent values."""
    cmd = cmd.replace("{issue}", str(intent.issue))
    cmd = cmd.replace("{pr}", str(intent.pr))
    cmd = cmd.replace("{repo}", intent.repo)
    cmd = cmd.replace("{project}", intent.project)
    return cmd


def _route(intent: IntentDoc, cwd: Path) -> RouteResult:
    """Evaluate next_if conditions in order. First match wins."""
    result = RouteResult(
        schema=INTENT_SCHEMA,
        intent={
            "project": intent.project,
            "repo": intent.repo,
            "issue": intent.issue,
            "pr": intent.pr,
            "goal": intent.goal,
            "context": intent.context,
        },
    )

    # Evaluate conditions in declared order
    for condition, action_cmd in intent.next_if.items():
        # Special case: "default" always matches
        if condition == "default":
            result.matched_condition = "default"
            result.next_action = action_cmd
            result.next_cmd = _substitute(action_cmd, intent)
            result.reason = "fallback — no other condition matched"
            return result

        # Map condition to probe
        probe_fn = _PROBE_MAP.get(condition)
        if not probe_fn:
            # Unknown condition — skip silently (extensibility hook)
            continue

        # Call probe with right args
        if condition.startswith("issue."):
            matched, state = probe_fn(intent.repo, intent.issue)
        elif condition.startswith("pr."):
            matched, state = probe_fn(intent.repo, intent.pr)
        else:
            matched, state = probe_fn(cwd)

        result.probed_state[condition] = {"matched": matched, "state": state}
        if matched:
            result.matched_condition = condition
            result.next_action = action_cmd
            result.next_cmd = _substitute(action_cmd, intent)
            result.reason = f"condition '{condition}' matched"
            return result

    # Nothing matched and no default
    result.reason = "no condition matched and no default fallback"
    return result


# ── CLI commands ─────────────────────────────────────────────────────────────

def _default_intent(name: str = "project") -> dict[str, Any]:
    return {
        "schema": INTENT_SCHEMA,
        "project": name,
        "repo": "",
        "issue": 0,
        "pr": 0,
        "context": [],
        "goal": "",
        "next_if": {
            "issue.open": "lgwks gh issue {issue} --next",
            "tests.fail": "lgwks debug test",
            "review.danger": "lgwks review --repo .",
            "dirty": "lgwks repo status",
            "default": "lgwks gh state --repo {repo}",
        },
    }


def init_command(args: argparse.Namespace) -> int:
    name = getattr(args, "name", "project")
    intent = _default_intent(name)
    print(json.dumps(intent, indent=2, ensure_ascii=False))
    return 0


def route_command(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"error: intent file not found: {path}", file=sys.stderr)
        return 1

    try:
        intent = _resolve_intent(path)
    except Exception as e:
        print(f"error: invalid intent file: {e}", file=sys.stderr)
        return 1

    cwd = Path(getattr(args, "cwd", ".")).resolve()
    result = _route(intent, cwd)

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": result.schema,
            "intent": result.intent,
            "probed_state": result.probed_state,
            "matched_condition": result.matched_condition,
            "next_action": result.next_action,
            "next_cmd": result.next_cmd,
            "reason": result.reason,
        }, indent=2, ensure_ascii=False))
        return 0

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · intent", intent.project, on=on)
    out.append(ui.spine(on=on))
    out.append(ui.spine(ui.fg(f"goal: {intent.goal or '(none)'}", ui.CREAM_DIM, on=on), on=on))
    if intent.context:
        out.append(ui.spine(ui.fg(f"context: {', '.join(intent.context)}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(on=on))
    if result.matched_condition:
        out.append(ui.spine(ui.fg(f"matched: {result.matched_condition}", ui.EMERALD, on=on), on=on))
        out.append(ui.spine(ui.fg(f"next: {result.next_cmd}", ui.CREAM, on=on), on=on))
        out.append(ui.spine(ui.fg(f"reason: {result.reason}", ui.CREAM_DIM, on=on), on=on))
    else:
        out.append(ui.spine(ui.fg("✗ No condition matched", ui.RUST, on=on), on=on))
        out.append(ui.twig("Add a 'default' fallback to your next_if", 1, "next", on=on))

    out.append("")
    out.append("  " + ui.footer("lgwks · intent", on=on))
    out.append("")
    print("\n".join(out))

    # Auto-execute if --yes and we have a next_cmd
    if getattr(args, "yes", False) and result.next_cmd:
        print(f"\n  → executing: {result.next_cmd}")
        try:
            p = subprocess.run(shlex.split(result.next_cmd), shell=False, cwd=str(cwd))
            return p.returncode
        except Exception as e:
            print(f"  → execution failed: {e}", file=sys.stderr)
            return 1

    return 0 if result.matched_condition else 1


def next_command(args: argparse.Namespace) -> int:
    """Read .lgwks/intent.json from repo root and print the next action."""
    cwd = Path(getattr(args, "cwd", ".")).resolve()
    intent_path = cwd / ".lgwks" / "intent.json"
    if not intent_path.exists():
        print("error: no .lgwks/intent.json found — run `lgwks intent --init >name> > .lgwks/intent.json`", file=sys.stderr)
        return 1
    return route_command(argparse.Namespace(file=str(intent_path), cwd=str(cwd), json=getattr(args, "json", False), yes=getattr(args, "yes", False)))


# ── parser registration ──────────────────────────────────────────────────────

def add_parser(sub) -> None:
    intent = sub.add_parser("intent", help="schema-driven intent router — declare, probe, act")
    ins = intent.add_subparsers(dest="intent_command", required=True)

    init = ins.add_parser("init", help="emit a starter intent JSON")
    init.add_argument("name", nargs="?", default="project", help="project name")
    init.set_defaults(func=init_command)

    route = ins.add_parser("route", help="read intent file, probe reality, emit next action")
    route.add_argument("file", help="path to intent JSON")
    route.add_argument("--cwd", default=".", help="working directory for probes")
    route.add_argument("--json", action="store_true")
    route.add_argument("--yes", action="store_true", help="auto-execute the next action")
    route.set_defaults(func=route_command)

    nxt = ins.add_parser("next", help="read .lgwks/intent.json and print next action")
    nxt.add_argument("--cwd", default=".")
    nxt.add_argument("--json", action="store_true")
    nxt.add_argument("--yes", action="store_true")
    nxt.set_defaults(func=next_command)
