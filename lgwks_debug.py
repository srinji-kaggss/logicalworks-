"""lgwks_debug — automated debugging: turn "it's broken" into "here's why + next step."

Runs commands, captures stdout/stderr/exit code, matches against a pattern database of known
failure signatures, and proposes fixes with risk classification. No AI needed for the common path;
ML can enrich later.

//why: Debugging currently costs 19 CLI commands. The user says "npm test failed" and the AI
spawns subprocess after subprocess. This module collapses that into ONE command with structured
output the AI can read directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui


# ── secret scrubber for debug logs ──────────────────────────────────────────
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|auth)\\s*[=:]\\s*['\"]?[^\\s'\"]{8,}['\"]?"
)


def _scrub(text: str) -> str:
    """Strip anything matching SECRET_RE before writing to disk."""
    return _SECRET_RE.sub("[REDACTED]", text)


# ── pattern database ─────────────────────────────────────────────────────────
# Each pattern: regex -> (check_id, severity, message_template, proposed_fix)

_PATTERNS: list[tuple[str, str, str, str, str, str]] = [
    # (regex, check_id, severity, message, fix_cmd, fix_risk)
    (
        r"ModuleNotFoundError: No module named '([^']+)'",
        "missing_module",
        "warn",
        "Missing Python module: {group1}",
        "pip install {group1}",
        "mutate",
    ),
    (
        r"ModuleNotFoundError: No module named \"([^\"]+)\"",
        "missing_module",
        "warn",
        "Missing Python module: {group1}",
        "pip install {group1}",
        "mutate",
    ),
    (
        r"command not found: ([^\\s]+)",
        "missing_binary",
        "warn",
        "Missing binary: {group1}",
        "brew install {group1}  # or pipx / npm / cargo",
        "mutate",
    ),
    (
        r"SyntaxError: invalid syntax",
        "syntax_error",
        "danger",
        "Python syntax error — check file/line in traceback",
        "lgwks review --repo .",
        "read",
    ),
    (
        r"AssertionError",
        "test_assertion",
        "warn",
        "Test assertion failed — behavior changed or regression",
        "lgwks review --repo .",
        "read",
    ),
    (
        r"fatal: not a git repository",
        "not_git_repo",
        "warn",
        "Not inside a git repo — cd to repo root",
        "cd <repo>",
        "read",
    ),
    (
        r"CONFLICT \(([^)]+)\)",
        "merge_conflict",
        "danger",
        "Git merge conflict: {group1}",
        "lgwks repo recover",
        "mutate",
    ),
    (
        r"gh: To use GitHub CLI in non-interactive mode",
        "gh_not_authed",
        "warn",
        "gh CLI not authenticated",
        "gh auth login",
        "mutate",
    ),
    (
        r"gh: not authenticated",
        "gh_not_authed",
        "warn",
        "gh CLI not authenticated",
        "gh auth login",
        "mutate",
    ),
    (
        r"playwright not installed",
        "playwright_missing",
        "warn",
        "Playwright not installed",
        "pipx install playwright && playwright install chromium",
        "mutate",
    ),
    (
        r"Error: Cannot find module '([^']+)'",
        "missing_node_module",
        "warn",
        "Missing Node module: {group1}",
        "npm install {group1}",
        "mutate",
    ),
    (
        r"npm ERR! code E404",
        "npm_404",
        "warn",
        "npm package not found — typo or private registry",
        "npm install <correct-name>",
        "mutate",
    ),
    (
        r"Permission denied",
        "permission_denied",
        "danger",
        "Permission denied — check file ownership or sudo",
        "ls -la <file>  # or chmod / chown",
        "destructive",
    ),
    (
        r"No such file or directory: ([^\\n]+)",
        "missing_file",
        "warn",
        "Missing file or directory: {group1}",
        "mkdir -p <dir>  # or restore from git",
        "mutate",
    ),
    (
        r"ECONNREFUSED",
        "connection_refused",
        "warn",
        "Connection refused — service not running",
        "start the service or check the port",
        "read",
    ),
    (
        r"ETIMEDOUT",
        "timeout",
        "warn",
        "Network timeout — check connectivity",
        "retry or check VPN/proxy",
        "read",
    ),
    (
        r"Port (\d+) is already in use",
        "port_in_use",
        "warn",
        "Port {group1} already in use",
        "lsof -i :{group1}  # find process, then kill or use new port",
        "mutate",
    ),
    (
        r"database is locked",
        "db_locked",
        "danger",
        "Database locked — another process holds it",
        "find and terminate the other process",
        "mutate",
    ),
    (
        r"FATAL: database "([^"]+)" does not exist",
        "missing_db",
        "warn",
        "Database does not exist: {group1}",
        "createdb {group1}  # or run migrations",
        "mutate",
    ),
    (
        r"django\.core\.exceptions\.ImproperlyConfigured",
        "django_config",
        "danger",
        "Django configuration error — missing env var or setting",
        "check .env and settings.py",
        "read",
    ),
    (
        r"pytest not found",
        "pytest_missing",
        "warn",
        "pytest not installed",
        "pip install pytest",
        "mutate",
    ),
]


# ── data models ──────────────────────────────────────────────────────────────

@dataclass
class DebugFinding:
    check: str
    severity: str  # info | warn | danger
    message: str
    line: int = 0
    fix_cmd: str = ""
    fix_risk: str = "read"
    evidence: str = ""


@dataclass
class DebugResult:
    command: str
    exit_code: int
    schema: str = "lgwks.debug.v0"
    findings: list[DebugFinding] = field(default_factory=list)
    stdout_preview: str = ""
    stderr_preview: str = ""
    duration_ms: float = 0.0


# ── core engine ──────────────────────────────────────────────────────────────

def _run_command(cmd: str, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str, float]:
    """Run a shell command. Returns (exit_code, stdout, stderr, duration_ms)."""
    start = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        dur = round((time.perf_counter() - start) * 1000, 1)
        return p.returncode, p.stdout, p.stderr, dur
    except subprocess.TimeoutExpired as e:
        dur = round((time.perf_counter() - start) * 1000, 1)
        return 124, "", f"timed out after {timeout}s", dur
    except Exception as e:
        dur = round((time.perf_counter() - start) * 1000, 1)
        return 1, "", str(e), dur


def _match_patterns(text: str) -> list[DebugFinding]:
    """Run pattern DB over text. Returns deduplicated findings."""
    findings: list[DebugFinding] = []
    seen: set[str] = set()
    for pattern, check_id, severity, msg_tpl, fix_cmd, fix_risk in _PATTERNS:
        for m in re.finditer(pattern, text):
            key = f"{check_id}:{m.start()}"
            if key in seen:
                continue
            seen.add(key)
            # Extract groups for template substitution
            groups = {f"group{i+1}": g for i, g in enumerate(m.groups())}
            message = msg_tpl.format(**groups)
            cmd = fix_cmd.format(**groups)
            # Estimate line number roughly
            line = text[:m.start()].count("\n") + 1
            findings.append(DebugFinding(
                check=check_id,
                severity=severity,
                message=message,
                line=line,
                fix_cmd=cmd,
                fix_risk=fix_risk,
                evidence=text[m.start():m.start()+80].strip(),
            ))
    return findings


def debug_command_run(cmd: str, cwd: Path | None = None, timeout: int = 60) -> DebugResult:
    """Run a command and debug the output."""
    rc, stdout, stderr, dur = _run_command(cmd, cwd, timeout)
    combined = stdout + "\n" + stderr
    findings = _match_patterns(combined)

    # If exit code non-zero but no pattern matched, emit a generic finding
    if rc != 0 and not findings:
        findings.append(DebugFinding(
            check="unknown_failure",
            severity="warn",
            message=f"Command exited with code {rc} — no known pattern matched",
            fix_cmd="lgwks solve git  # or inspect output manually",
            fix_risk="read",
            evidence=stderr[:120] or stdout[:120],
        ))

    result = DebugResult(
        command=cmd,
        exit_code=rc,
        findings=findings,
        stdout_preview=_scrub(stdout[:800]),
        stderr_preview=_scrub(stderr[:800]),
        duration_ms=dur,
    )
    _append_debug_log(result)
    return result


# ── debug log (append-only, scrubbed) ────────────────────────────────────────

def _debug_log_path() -> Path:
    return Path.cwd() / ".lgwks" / "debug-log.jsonl"


def _append_debug_log(result: DebugResult) -> None:
    """Append a scrubbed record to the local debug log."""
    log_path = _debug_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "command": result.command,
        "exit_code": result.exit_code,
        "findings": [{"check": f.check, "severity": f.severity, "message": f.message} for f in result.findings],
        "stdout_preview": result.stdout_preview,
        "stderr_preview": result.stderr_preview,
        "duration_ms": result.duration_ms,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_last_failure() -> dict[str, Any] | None:
    """Load the most recent non-zero exit code record from the debug log."""
    log_path = _debug_log_path()
    if not log_path.exists():
        return None
    last: dict[str, Any] | None = None
    with open(log_path, "r", encoding="utf-8") as fh:
        for ln in fh:
            try:
                rec = json.loads(ln)
                if rec.get("exit_code", 0) != 0:
                    last = rec
            except Exception:
                continue
    return last


# ── test runner ──────────────────────────────────────────────────────────────

def _run_tests(pattern: str | None = None, cwd: Path | None = None) -> DebugResult:
    """Run pytest and debug failures."""
    cmd = "python -m pytest"
    if pattern:
        cmd += f" -k {pattern}"
    cmd += " -q"
    rc, stdout, stderr, dur = _run_command(cmd, cwd, timeout=120)
    combined = stdout + "\n" + stderr
    findings = _match_patterns(combined)

    # Additional pytest-specific heuristics
    failed_test_match = re.search(r"FAILED ([^\s]+)", combined)
    if failed_test_match:
        test_name = failed_test_match.group(1)
        findings.append(DebugFinding(
            check="pytest_failed",
            severity="warn",
            message=f"Test failed: {test_name}",
            fix_cmd=f"lgwks debug test --pattern {test_name}",
            fix_risk="read",
            evidence=test_name,
        ))
        # Correlate with git diff
        try:
            diff_rc, diff_out = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(cwd) if cwd else None,
            ).returncode, ""
            if diff_rc == 0:
                diff_files = [ln.strip() for ln in diff_out.splitlines() if ln.strip()]
                if diff_files:
                    findings.append(DebugFinding(
                        check="diff_correlation",
                        severity="info",
                        message=f"Recent changes in: {', '.join(diff_files[:3])}",
                        fix_cmd="lgwks review --repo .",
                        fix_risk="read",
                        evidence=", ".join(diff_files[:3]),
                    ))
        except Exception:
            pass

    if rc != 0 and not findings:
        findings.append(DebugFinding(
            check="test_suite_failure",
            severity="warn",
            message=f"Test suite failed (exit {rc}) — inspect output",
            fix_cmd="python -m pytest -xvs",
            fix_risk="read",
        ))

    result = DebugResult(
        command=cmd,
        exit_code=rc,
        findings=findings,
        stdout_preview=_scrub(stdout[:800]),
        stderr_preview=_scrub(stderr[:800]),
        duration_ms=dur,
    )
    _append_debug_log(result)
    return result


# ── CLI renderers ────────────────────────────────────────────────────────────

def _render_findings(findings: list[DebugFinding], on: bool) -> list[str]:
    out: list[str] = []
    for f in findings:
        color = ui.EMERALD if f.severity == "info" else (ui.AMBER if f.severity == "warn" else ui.RUST)
        out.append(ui.spine(ui.fg(f"  [{f.severity.upper()}] {f.message}", color, on=on), on=on))
        if f.evidence:
            out.append(ui.twig(f.evidence[:80], 1, "proof", on=on))
        if f.fix_cmd:
            risk_color = ui.EMERALD if f.fix_risk == "read" else (ui.AMBER if f.fix_risk == "mutate" else ui.RUST)
            out.append(ui.twig(f"fix [{f.fix_risk}]: {f.fix_cmd}", 1, "next", on=on))
    return out


# ── command dispatch ─────────────────────────────────────────────────────────

def run_command(args: argparse.Namespace) -> int:
    cmd = " ".join(args.command)
    cwd = Path(getattr(args, "cwd", ".")).resolve()
    result = debug_command_run(cmd, cwd, timeout=getattr(args, "timeout", 60))

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": result.schema,
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "findings": [{"check": f.check, "severity": f.severity, "message": f.message,
                          "line": f.line, "fix_cmd": f.fix_cmd, "fix_risk": f.fix_risk} for f in result.findings],
            "stdout_preview": result.stdout_preview,
            "stderr_preview": result.stderr_preview,
        }, indent=2, ensure_ascii=False))
        return result.exit_code

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · debug", f"{result.command} — exit {result.exit_code} ({result.duration_ms}ms)", on=on)
    out.append(ui.spine(on=on))
    if result.findings:
        out.append(ui.spine(ui.fg(f"findings ({len(result.findings)})", ui.CREAM_DIM, on=on), on=on))
        out.extend(_render_findings(result.findings, on))
    else:
        out.append(ui.spine(ui.fg("✓ No findings — clean run", ui.EMERALD, on=on), on=on))
    if result.stdout_preview:
        out.append(ui.spine(ui.fg("stdout preview", ui.CREAM_DIM, on=on), on=on))
        for ln in result.stdout_preview.splitlines()[:8]:
            out.append(ui.twig(ln[:80], 1, "proof", on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · debug", on=on)); out.append("")
    print("\n".join(out))
    return result.exit_code


def last_command(args: argparse.Namespace) -> int:
    rec = _load_last_failure()
    if not rec:
        print("error: no debug log found — run `lgwks debug <cmd>` first", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.debug.v0",
            "check": "last",
            "record": rec,
        }, indent=2))
        return 0

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · debug last", f"{rec['command']} — exit {rec['exit_code']}", on=on)
    out.append(ui.spine(on=on))
    for f in rec.get("findings", []):
        color = ui.EMERALD if f["severity"] == "info" else (ui.AMBER if f["severity"] == "warn" else ui.RUST)
        out.append(ui.spine(ui.fg(f"  [{f['severity'].upper()}] {f['message']}", color, on=on), on=on))
    if rec.get("stdout_preview"):
        out.append(ui.spine(ui.fg("stdout preview", ui.CREAM_DIM, on=on), on=on))
        for ln in rec["stdout_preview"].splitlines()[:6]:
            out.append(ui.twig(ln[:80], 1, "proof", on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · debug last", on=on)); out.append("")
    print("\n".join(out))
    return rec.get("exit_code", 1)


def test_command(args: argparse.Namespace) -> int:
    pattern = getattr(args, "pattern", None)
    cwd = Path(getattr(args, "cwd", ".")).resolve()
    result = _run_tests(pattern, cwd)

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": result.schema,
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "findings": [{"check": f.check, "severity": f.severity, "message": f.message,
                          "line": f.line, "fix_cmd": f.fix_cmd, "fix_risk": f.fix_risk} for f in result.findings],
        }, indent=2, ensure_ascii=False))
        return result.exit_code

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · debug test", f"{result.command} — exit {result.exit_code} ({result.duration_ms}ms)", on=on)
    out.append(ui.spine(on=on))
    if result.findings:
        out.append(ui.spine(ui.fg(f"findings ({len(result.findings)})", ui.CREAM_DIM, on=on), on=on))
        out.extend(_render_findings(result.findings, on))
    else:
        out.append(ui.spine(ui.fg("✓ All tests passed", ui.EMERALD, on=on), on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · debug test", on=on)); out.append("")
    print("\n".join(out))
    return result.exit_code


# ── parser registration ──────────────────────────────────────────────────────

def add_parser(sub) -> None:
    debug = sub.add_parser("debug", help="automated debugging — run, parse, propose fix")
    ds = debug.add_subparsers(dest="debug_command", required=True)

    run = ds.add_parser("run", help="run a command and debug the output")
    run.add_argument("command", nargs="+", help="command to run (e.g. npm test)")
    run.add_argument("--cwd", default=".", help="working directory")
    run.add_argument("--timeout", type=int, default=60, help="seconds before kill")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=run_command)

    last = ds.add_parser("last", help="replay last failure from debug log")
    last.add_argument("--json", action="store_true")
    last.set_defaults(func=last_command)

    test = ds.add_parser("test", help="run pytest and debug failures")
    test.add_argument("--pattern", default=None, help="pytest -k pattern")
    test.add_argument("--cwd", default=".")
    test.add_argument("--json", action="store_true")
    test.set_defaults(func=test_command)
