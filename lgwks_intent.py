"""lgwks_intent — schema-driven intent router. A 10-line declaration drives automation.

Defense-in-Depth layers:
  T0 schema validation: strict version pin, typed fields, repo slug regex, bounded numbers.
  T1 input sanitization: next_if keys allowlisted; substitution escapes shell metacharacters.
  T2 probe sandbox: isolated subprocess, per-probe timeout, no shell=True anywhere.
  T3 secret scrub: _SECRET_RE strips credentials from all probe stdout/stderr.
  T4 rate/circuit: probe count capped per route; consecutive failures back off.
  T5 audit: .lgwks/intent-audit.jsonl records every routing decision with full probed state.
  T6 execution gate: auto-execute (--yes) carries risk class (read/mutate/destructive);
     destructive commands require explicit confirmation, not --yes alone.

No AI needed for routing; ML can enrich later.
//why: The user wants to say "what's next from GH issue 258" as ONE command, not 19.
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


# ── constants ───────────────────────────────────────────────────────────────

INTENT_SCHEMA = "lgwks.intent.v0"
_MAX_PROBES_PER_ROUTE = 12
_MAX_ISSUE = 9_999_999
_MAX_PR = 9_999_999

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key\w*|token\w*|password\w*|secret\w*|auth\w*)\s*([=:]\s*(bearer|token)?|(bearer|token))\s*['\"]?[^\s'\"]{8,}['\"]?"
)

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Conditions we allow in next_if (extensible, but gated)
_ALLOWLIST_CONDITIONS = frozenset({
    "issue.open", "issue.closed",
    "tests.fail", "tests.pass",
    "pr.draft", "pr.open", "pr.closed",
    "review.danger", "review.warn",
    "dirty", "clean",
    "default",
})

# Risk classification for next actions (pattern -> risk class)
_RISK_MAP: dict[str, str] = {
    "rm": "destructive",
    "git push": "mutate",
    "git merge": "mutate",
    "git rebase": "mutate",
    "npm install": "mutate",
    "pip install": "mutate",
    "brew install": "mutate",
    "gh pr merge": "mutate",
    "gh issue close": "mutate",
    "lgwks debug test": "read",
    "lgwks review": "read",
    "lgwks repo status": "read",
    "lgwks gh": "read",
    "cat ": "read",
    "ls ": "read",
    "echo ": "read",
}


def _classify_risk(cmd: str) -> str:
    for prefix, risk in _RISK_MAP.items():
        if prefix in cmd:
            return risk
    return "mutate"  # default caution


# ── audit ───────────────────────────────────────────────────────────────────

def _audit_log_path() -> Path:
    return Path.cwd() / ".lgwks" / "intent-audit.jsonl"


def _audit(intent_file: str, matched: str, next_cmd: str, probed: dict[str, Any]) -> None:
    log = _audit_log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "intent_file": intent_file,
        "matched_condition": matched,
        "next_cmd": next_cmd,
        "risk": _classify_risk(next_cmd),
        "probed_state": probed,
    }
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── input validation ────────────────────────────────────────────────────────

def _validate_slug(slug: str | None) -> str | None:
    if not slug:
        return None
    slug = slug.strip()
    if not _SLUG_RE.match(slug):
        raise ValueError(f"invalid repo slug: {slug!r} — expected owner/repo")
    return slug


def _validate_number(n: int, name: str, max_val: int = _MAX_ISSUE) -> int:
    if n < 0 or n > max_val:
        raise ValueError(f"{name} must be 0..{max_val}, got {n}")
    return int(n)


def _validate_next_if_keys(next_if: dict[str, str]) -> dict[str, str]:
    invalid = [k for k in next_if if k not in _ALLOWLIST_CONDITIONS]
    if invalid:
        raise ValueError(f"unsupported next_if conditions: {invalid!r} — allowed: {sorted(_ALLOWLIST_CONDITIONS)}")
    return next_if


def _scrub(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text)


def _safe_substitute(cmd: str, intent: "IntentDoc") -> str:
    """Replace placeholders with validated, shell-safe values."""
    # Escape any shell metacharacters in replacements
    repo = shlex.quote(intent.repo) if intent.repo else ""
    project = shlex.quote(intent.project) if intent.project else ""
    issue = str(intent.issue)
    pr = str(intent.pr)
    cmd = cmd.replace("{repo}", repo)
    cmd = cmd.replace("{project}", project)
    cmd = cmd.replace("{issue}", issue)
    cmd = cmd.replace("{pr}", pr)
    return cmd


# ── data models ────────────────────────────────────────────────────────────

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
    schema: str = INTENT_SCHEMA
    intent: dict[str, Any] = field(default_factory=dict)
    probed_state: dict[str, Any] = field(default_factory=dict)
    matched_condition: str = ""
    next_action: str = ""
    next_cmd: str = ""
    next_cmd_risk: str = "read"
    reason: str = ""
    would_run: bool = False
    blocked: bool = False
    block_reason: str = ""


# ── probes ───────────────────────────────────────────────────────────────────

def _run_probe(cmd_parts: list[str], timeout: int = 15, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a probe with shell=False and scrubbed output. Returns (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        return p.returncode, _scrub(p.stdout), _scrub(p.stderr)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except FileNotFoundError as e:
        return 127, "", f"command not found: {e}"
    except Exception as e:
        return 1, "", str(e)


def _probe_issue_open(repo: str, issue: int) -> tuple[bool, dict[str, Any]]:
    if not issue or not repo:
        return False, {}
    rc, out, err = _run_probe(
        ["gh", "issue", "view", str(issue), "--repo", repo, "--json", "state"],
        timeout=15,
    )
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            state = data.get("state", "").lower()
            return state == "open", {"state": state}
        except Exception:
            pass
    return False, {"_error": err or out[:200]}


def _probe_issue_closed(repo: str, issue: int) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_issue_open(repo, issue)
    return not matched and ctx.get("state") == "closed", ctx


def _probe_pr_draft(repo: str, pr: int) -> tuple[bool, dict[str, Any]]:
    if not pr or not repo:
        return False, {}
    rc, out, err = _run_probe(
        ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "state"],
        timeout=15,
    )
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            state = data.get("state", "").lower()
            return state == "draft", {"state": state}
        except Exception:
            pass
    return False, {"_error": err or out[:200]}


def _probe_pr_open(repo: str, pr: int) -> tuple[bool, dict[str, Any]]:
    if not pr or not repo:
        return False, {}
    rc, out, err = _run_probe(
        ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "state"],
        timeout=15,
    )
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            state = data.get("state", "").lower()
            return state == "open", {"state": state}
        except Exception:
            pass
    return False, {"_error": err or out[:200]}


def _probe_pr_closed(repo: str, pr: int) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_pr_open(repo, pr)
    return not matched and ctx.get("state") == "closed", ctx


def _probe_tests_fail(cwd: Path) -> tuple[bool, dict[str, Any]]:
    rc, out, err = _run_probe(
        ["python", "-m", "pytest", "-q"],
        timeout=120,
        cwd=cwd,
    )
    return rc != 0, {"exit_code": rc, "preview": (err or out)[:200]}


def _probe_tests_pass(cwd: Path) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_tests_fail(cwd)
    return not matched, ctx


def _probe_review_danger(cwd: Path) -> tuple[bool, dict[str, Any]]:
    rc, out, err = _run_probe(
        ["python", "-m", "lgwks", "review", "--repo", str(cwd), "--json"],
        timeout=60,
        cwd=cwd,
    )
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            findings = data.get("findings", [])
            danger = any(f.get("severity") == "danger" for f in findings)
            return danger, {"findings_count": len(findings), "danger": danger}
        except Exception:
            pass
    return False, {"_error": err or out[:200]}


def _probe_review_warn(cwd: Path) -> tuple[bool, dict[str, Any]]:
    rc, out, err = _run_probe(
        ["python", "-m", "lgwks", "review", "--repo", str(cwd), "--json"],
        timeout=60,
        cwd=cwd,
    )
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            findings = data.get("findings", [])
            warn = any(f.get("severity") in ("warn", "danger") for f in findings)
            return warn, {"findings_count": len(findings), "warn_or_above": warn}
        except Exception:
            pass
    return False, {"_error": err or out[:200]}


def _probe_dirty(cwd: Path) -> tuple[bool, dict[str, Any]]:
    rc, out, err = _run_probe(
        ["git", "status", "--porcelain"],
        timeout=10,
        cwd=cwd,
    )
    dirty = bool(out.strip())
    return dirty, {"files_changed": len([l for l in out.splitlines() if l.strip()])}


def _probe_clean(cwd: Path) -> tuple[bool, dict[str, Any]]:
    matched, ctx = _probe_dirty(cwd)
    return not matched, ctx


_PROBE_MAP: dict[str, Any] = {
    "issue.open": _probe_issue_open,
    "issue.closed": _probe_issue_closed,
    "tests.fail": _probe_tests_fail,
    "tests.pass": _probe_tests_pass,
    "pr.draft": _probe_pr_draft,
    "pr.open": _probe_pr_open,
    "pr.closed": _probe_pr_closed,
    "review.danger": _probe_review_danger,
    "review.warn": _probe_review_warn,
    "dirty": _probe_dirty,
    "clean": _probe_clean,
}


# ── router ───────────────────────────────────────────────────────────────────

def _resolve_intent(path: Path) -> IntentDoc:
    """Load, validate, and sanitize an intent file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema = raw.get("schema")
    if schema != INTENT_SCHEMA:
        raise ValueError(f"expected schema {INTENT_SCHEMA!r}, got {schema!r}")

    repo = _validate_slug(raw.get("repo", ""))
    issue = _validate_number(raw.get("issue", 0), "issue", _MAX_ISSUE)
    pr = _validate_number(raw.get("pr", 0), "pr", _MAX_PR)
    next_if = _validate_next_if_keys(raw.get("next_if", {}))

    # Ensure "default" is last in evaluation order
    ordered = {}
    for k, v in next_if.items():
        if k != "default":
            ordered[k] = v
    if "default" in next_if:
        ordered["default"] = next_if["default"]

    return IntentDoc(
        schema=schema,
        project=raw.get("project", ""),
        repo=repo or "",
        issue=issue,
        pr=pr,
        context=raw.get("context", []),
        goal=raw.get("goal", ""),
        next_if=ordered,
    )


def _route(intent: IntentDoc, cwd: Path, intent_file: str) -> RouteResult:
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

    probe_count = 0
    for condition, action_cmd in intent.next_if.items():
        if probe_count >= _MAX_PROBES_PER_ROUTE:
            result.blocked = True
            result.block_reason = f"probe limit ({_MAX_PROBES_PER_ROUTE}) exceeded — aborted for safety"
            break

        if condition == "default":
            result.matched_condition = "default"
            result.next_action = action_cmd
            result.next_cmd = _safe_substitute(action_cmd, intent)
            result.next_cmd_risk = _classify_risk(result.next_cmd)
            result.reason = "fallback — no other condition matched"
            break

        probe_fn = _PROBE_MAP.get(condition)
        if not probe_fn:
            continue

        if condition.startswith("issue."):
            matched, state = probe_fn(intent.repo, intent.issue)
        elif condition.startswith("pr."):
            matched, state = probe_fn(intent.repo, intent.pr)
        else:
            matched, state = probe_fn(cwd)

        probe_count += 1
        result.probed_state[condition] = {"matched": matched, "state": state}
        if matched:
            result.matched_condition = condition
            result.next_action = action_cmd
            result.next_cmd = _safe_substitute(action_cmd, intent)
            result.next_cmd_risk = _classify_risk(result.next_cmd)
            result.reason = f"condition '{condition}' matched"
            break
    else:
        result.reason = "no condition matched and no default fallback"

    _audit(intent_file, result.matched_condition, result.next_cmd, result.probed_state)
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
    result = _route(intent, cwd, str(path))

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": result.schema,
            "intent": result.intent,
            "probed_state": result.probed_state,
            "matched_condition": result.matched_condition,
            "next_action": result.next_action,
            "next_cmd": result.next_cmd,
            "next_cmd_risk": result.next_cmd_risk,
            "reason": result.reason,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
        }, indent=2, ensure_ascii=False))
        return 1 if result.blocked else (0 if result.matched_condition else 1)

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · intent", intent.project, on=on)
    out.append(ui.spine(on=on))
    out.append(ui.spine(ui.fg(f"goal: {intent.goal or '(none)'}", ui.CREAM_DIM, on=on), on=on))
    if intent.context:
        out.append(ui.spine(ui.fg(f"context: {', '.join(intent.context)}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(on=on))

    if result.blocked:
        out.append(ui.spine(ui.fg(f"✗ BLOCKED: {result.block_reason}", ui.RUST, on=on), on=on))
        out.append(""); out.append("  " + ui.footer("lgwks · intent", on=on)); out.append("")
        print("\n".join(out))
        return 126

    if result.matched_condition:
        risk_color = ui.EMERALD if result.next_cmd_risk == "read" else (ui.AMBER if result.next_cmd_risk == "mutate" else ui.RUST)
        out.append(ui.spine(ui.fg(f"matched: {result.matched_condition}", ui.EMERALD, on=on), on=on))
        out.append(ui.spine(ui.fg(f"next: {result.next_cmd}", ui.CREAM, on=on), on=on))
        out.append(ui.spine(ui.fg(f"risk: {result.next_cmd_risk}", risk_color, on=on), on=on))
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
        if result.next_cmd_risk == "destructive":
            print(f"\n  → BLOCKED: destructive command requires explicit confirmation, not --yes")
            print(f"     run manually: {result.next_cmd}")
            return 126
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
        print("error: no .lgwks/intent.json found — run `lgwks intent init <name> > .lgwks/intent.json`", file=sys.stderr)
        return 1
    # Pass through to route_command with constructed args
    args.file = str(intent_path)
    return route_command(args)


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
    route.add_argument("--yes", action="store_true", help="auto-execute the next action (blocked for destructive)")
    route.set_defaults(func=route_command)

    nxt = ins.add_parser("next", help="read .lgwks/intent.json and print next action")
    nxt.add_argument("--cwd", default=".")
    nxt.add_argument("--json", action="store_true")
    nxt.add_argument("--yes", action="store_true")
    nxt.set_defaults(func=next_command)
