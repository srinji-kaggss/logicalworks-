"""lgwks_session — session boundary analyzer (begin / end / summary).

Reads the last N git actions, CLI commands, worktree changes, and produces a
token-efficient summary of everything since the last session marker. Designed to
run at session start ("what happened since I left?") and session end ("here is
what we did this session").

//why: context windows are finite. A human or peer agent resuming work needs the
densest possible summary of recent activity, not a full git log. This is the
membrane between sessions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_repo import _git, _is_repo


_MARKER_FILE = Path.home() / ".config" / "lgwks" / "session-markers.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_marker(repo: Path, kind: str, note: str = "") -> None:
    _MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"t": _now(), "repo": str(repo), "kind": kind, "note": note})
    with open(_MARKER_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def _last_marker(repo: Path) -> dict[str, Any] | None:
    if not _MARKER_FILE.exists():
        return None
    matches: list[dict[str, Any]] = []
    with open(_MARKER_FILE, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
                if rec.get("repo") == str(repo):
                    matches.append(rec)
            except Exception:
                continue
    return matches[-1] if matches else None


def _shell_history_last_n(n: int = 50) -> list[str]:
    """Best-effort read of recent shell history. Agnostic to shell (bash/zsh/fish)."""
    histfile = os.environ.get("HISTFILE", "")
    if not histfile:
        # guess common defaults
        for candidate in (Path.home() / ".zsh_history", Path.home() / ".bash_history"):
            if candidate.exists():
                histfile = str(candidate)
                break
    if not histfile or not Path(histfile).exists():
        return []
    try:
        with open(histfile, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except Exception:
        return []
    # zsh history has timestamps as `: 1234567890:0;command`
    cleaned: list[str] = []
    for ln in lines:
        ln = ln.rstrip("\n")
        if ln.startswith(": "):
            m = re.match(r": \d+:\d;(.+)", ln)
            if m:
                cleaned.append(m.group(1))
        else:
            cleaned.append(ln)
    return cleaned[-n:]


def _git_activity_since(repo: Path, since_iso: str | None) -> dict[str, Any]:
    """Collect git activity since a timestamp or the last session marker."""
    # commits
    fmt = "%h|%s|%ci"
    if since_iso:
        rc, out = _git(repo, "log", f"--since={since_iso}", "--pretty=format:" + fmt)
    else:
        rc, out = _git(repo, "log", "-n", "20", "--pretty=format:" + fmt)
    commits = []
    for ln in out.splitlines():
        parts = ln.split("|", 2)
        if len(parts) == 3:
            commits.append({"sha": parts[0], "subject": parts[1], "date": parts[2]})

    # reflog ops (checkouts, resets, rebases)
    rc, out = _git(repo, "reflog", "-n", "20", "--date=iso")
    reflog = [ln.strip() for ln in out.splitlines() if ln.strip()][:10]

    # branches created/deleted
    rc, out = _git(repo, "reflog", "--all", "-n", "40")
    branch_ops = [ln for ln in out.splitlines() if any(k in ln for k in ("checkout: moving", "branch: Created", "branch: Deleted"))][:10]

    # worktrees created/removed
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    worktrees = []
    current_wt = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            current_wt = line[9:]
        if line.startswith("branch ") and current_wt:
            worktrees.append(current_wt)

    # stashes
    rc, out = _git(repo, "stash", "list")
    stashes = len(out.splitlines()) if out else 0

    # uncommitted / untracked
    rc, out = _git(repo, "status", "--short")
    uncommitted = len(out.splitlines()) if out else 0

    return {
        "commits": commits,
        "reflog": reflog,
        "branch_ops": branch_ops,
        "worktrees": worktrees,
        "stashes": stashes,
        "uncommitted": uncommitted,
    }


def _summarize_activity(repo: Path, activity: dict[str, Any], history: list[str]) -> dict[str, Any]:
    """Produce a token-efficient summary."""
    summary: dict[str, Any] = {
        "schema": "lgwks.session.summary.v0",
        "repo": str(repo),
        "generated_at": _now(),
    }

    # Commits: group by verb
    verbs = Counter[str]()
    scopes: list[str] = []
    for c in activity["commits"]:
        subject = c["subject"]
        m = re.match(r"^(\w+)(?:\(([^)]+)\))?:", subject)
        if m:
            verbs[m.group(1)] += 1
            if m.group(2):
                scopes.append(m.group(2))
        else:
            verbs["other"] += 1

    summary["commits"] = {
        "count": len(activity["commits"]),
        "verbs": dict(sorted(verbs.items(), key=lambda x: -x[1])),
        "scopes": sorted(set(scopes)) if scopes else [],
        "latest": activity["commits"][0]["subject"] if activity["commits"] else None,
    }

    # Reflog: detect patterns
    patterns: dict[str, int] = {"checkouts": 0, "resets": 0, "rebases": 0, "merges": 0}
    for ln in activity["reflog"]:
        if "checkout: moving" in ln:
            patterns["checkouts"] += 1
        elif "reset: moving" in ln:
            patterns["resets"] += 1
        elif "rebase" in ln:
            patterns["rebases"] += 1
        elif "merge" in ln:
            patterns["merges"] += 1
    summary["reflog_patterns"] = {k: v for k, v in patterns.items() if v > 0}

    # Branch ops
    summary["branches"] = {
        "created": len([b for b in activity["branch_ops"] if "Created" in b]),
        "deleted": len([b for b in activity["branch_ops"] if "Deleted" in b]),
    }

    # Worktrees
    summary["worktrees"] = len(activity["worktrees"])

    # Dirty state
    summary["dirty"] = {
        "uncommitted": activity["uncommitted"],
        "stashes": activity["stashes"],
    }

    # Shell history: filter for lgwks / git / cargo / npm commands
    tool_cmds = [ln for ln in history if re.search(r"\b(lgwks|git|cargo|npm|python3?|pytest|make)\b", ln)]
    summary["shell_tool_commands"] = tool_cmds[-10:]  # last 10 only

    # R-meter: categorize token burn as Recovery / Invention / Noise
    recovery_signals = {"fix", "revert", "undo", "repair", "restore", "rebuild",
                       "test", "debug", "patch", "correct", "resolve", "close",
                       "regression", "broken", "fail", "error", "bug", "issue"}
    invention_signals = {"feat", "feature", "add", "new", "create", "build",
                        "implement", "design", "architect", "introduce", "innovate",
                        "optimize", "improve", "refactor", "upgrade", "enhance"}
    noise_signals = {"wip", "temp", "draft", "placeholder", "todo", "hack",
                      "workaround", "stub", "mock", "skip", "ignore",
                      "merge", "bump", "update deps", "changelog", "docs"}

    def _categorize_token(verb: str, subject: str) -> str:
        text = f"{verb} {subject}".lower()
        if any(s in text for s in recovery_signals):
            return "recovery"
        if any(s in text for s in invention_signals):
            return "invention"
        if any(s in text for s in noise_signals):
            return "noise"
        return "invention"  # default: assume productive work

    r_counts = {"recovery": 0, "invention": 0, "noise": 0, "uncategorized": 0}
    for c in activity["commits"]:
        subject = c["subject"]
        m = re.match(r"^(\w+)", subject)
        verb = m.group(1) if m else "other"
        cat = _categorize_token(verb, subject)
        r_counts[cat] += 1

    # Also categorize shell commands
    for cmd in tool_cmds:
        cmd_lower = cmd.lower()
        if any(s in cmd_lower for s in {"revert", "restore", "reset", "checkout", "clean"}):
            r_counts["recovery"] += 0.3  # partial weight for shell recovery
        elif any(s in cmd_lower for s in {"test", "pytest", "debug", "fix"}):
            r_counts["recovery"] += 0.3
        elif any(s in cmd_lower for s in {"build", "run", "deploy", "ship"}):
            r_counts["invention"] += 0.3
        elif any(s in cmd_lower for s in {"status", "log", "diff", "show", "ls", "help"}):
            r_counts["noise"] += 0.3

    total = sum(r_counts.values())
    summary["r_meter"] = {
        "counts": {k: round(v, 1) for k, v in r_counts.items()},
        "percentages": {k: round(v / total * 100, 1) if total else 0 for k, v in r_counts.items()},
        "dominant": max(r_counts, key=r_counts.get) if total else "unknown",
        "total_weighted": round(total, 1),
    }

    # Narrative (one paragraph)
    parts: list[str] = []
    if summary["commits"]["count"]:
        parts.append(f"{summary['commits']['count']} commit(s) — top verbs: {', '.join(f'{k}:{v}' for k,v in list(summary['commits']['verbs'].items())[:3])}.")
    if summary["reflog_patterns"]:
        parts.append(f"Reflog: {', '.join(f'{k}:{v}' for k,v in summary['reflog_patterns'].items())}.")
    if summary["branches"]["created"] or summary["branches"]["deleted"]:
        parts.append(f"Branches created {summary['branches']['created']}, deleted {summary['branches']['deleted']}.")
    if summary["dirty"]["uncommitted"] or summary["dirty"]["stashes"]:
        parts.append(f"Dirty: {summary['dirty']['uncommitted']} uncommitted, {summary['dirty']['stashes']} stash(es).")
    # Add R-meter to narrative only if there was activity
    rm = summary.get("r_meter", {})
    if parts and rm.get("dominant") and rm.get("total_weighted", 0) > 0:
        parts.append(f"Token burn: {rm['dominant']} dominant ({rm['percentages'].get(rm['dominant'], 0)}%).")
    summary["narrative"] = " ".join(parts) if parts else "No activity detected since last marker."

    return summary


def session_begin(repo: Path) -> dict[str, Any]:
    """Run at session start: summarize since last marker, then write a new begin marker."""
    last = _last_marker(repo)
    since = last.get("t") if last else None
    activity = _git_activity_since(repo, since)
    history = _shell_history_last_n(50)
    summary = _summarize_activity(repo, activity, history)
    _write_marker(repo, "begin")
    return summary


def session_end(repo: Path, note: str = "") -> dict[str, Any]:
    """Run at session end: summarize since last begin marker, then write end marker."""
    last = _last_marker(repo)
    since = last.get("t") if last and last.get("kind") in ("begin", "end") else None
    activity = _git_activity_since(repo, since)
    history = _shell_history_last_n(50)
    summary = _summarize_activity(repo, activity, history)
    _write_marker(repo, "end", note)
    return summary


def session_summary(repo: Path, n_commits: int = 20) -> dict[str, Any]:
    """Ad-hoc summary regardless of markers."""
    activity = _git_activity_since(repo, None)
    # trim commits to N
    activity["commits"] = activity["commits"][:n_commits]
    history = _shell_history_last_n(30)
    return _summarize_activity(repo, activity, history)


# ── CLI surfaces ──

def _render_summary(summary: dict[str, Any]) -> list[str]:
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · session", summary.get("narrative", ""), on=on)
    out.append(ui.spine(on=on))

    commits = summary.get("commits", {})
    if commits.get("count"):
        out.append(ui.spine(ui.fg(f"commits {commits['count']} · latest: {commits['latest']}", ui.CREAM_DIM, on=on), on=on))
        if commits.get("verbs"):
            verbs = ", ".join(f"{k}:{v}" for k, v in list(commits["verbs"].items())[:4])
            out.append(ui.twig(f"verbs: {verbs}", 1, "info", on=on))

    reflog = summary.get("reflog_patterns", {})
    if reflog:
        out.append(ui.spine(ui.fg(f"reflog: {', '.join(f'{k}:{v}' for k,v in reflog.items())}", ui.CREAM_DIM, on=on), on=on))

    branches = summary.get("branches", {})
    if branches.get("created") or branches.get("deleted"):
        out.append(ui.spine(ui.fg(f"branches +{branches.get('created',0)} -{branches.get('deleted',0)}", ui.CREAM_DIM, on=on), on=on))

    dirty = summary.get("dirty", {})
    if dirty.get("uncommitted") or dirty.get("stashes"):
        out.append(ui.spine(ui.fg(f"dirty: {dirty.get('uncommitted',0)} uncommitted · {dirty.get('stashes',0)} stashes", ui.RUST, on=on), on=on))

    shell = summary.get("shell_tool_commands", [])
    if shell:
        out.append(ui.spine(ui.fg("recent commands", ui.CREAM_DIM, on=on), on=on))
        for cmd in shell[-5:]:
            out.append(ui.twig(cmd, 1, "cmd", on=on))

    # R-meter
    rm = summary.get("r_meter", {})
    if rm:
        out.append(ui.spine(ui.fg("R-meter (token burn)", ui.CREAM_DIM, on=on), on=on))
        dominant = rm.get("dominant", "unknown")
        pct = rm.get("percentages", {})
        detail = " · ".join(f"{k}:{v}%" for k, v in list(pct.items())[:3])
        out.append(ui.twig(f"dominant: {dominant} ({pct.get(dominant, 0)}%) — {detail}", 1, "info", on=on))

    out.append(""); out.append("  " + ui.footer("lgwks · session", on=on)); out.append("")
    return out


def begin_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    summary = session_begin(repo)
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
        return 0
    print("\n".join(_render_summary(summary)))
    return 0


def end_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    summary = session_end(repo, getattr(args, "note", ""))
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
        return 0
    print("\n".join(_render_summary(summary)))
    return 0


def summary_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    summary = session_summary(repo, n_commits=getattr(args, "commits", 20))
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
        return 0
    print("\n".join(_render_summary(summary)))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("session", help="session boundary: begin, end, summary")
    ps = p.add_subparsers(dest="session_command", required=True)

    beg = ps.add_parser("begin", help="mark session start + summarize since last marker")
    beg.add_argument("--repo", default=".", help="path to repo")
    beg.add_argument("--json", action="store_true", help="structured output")
    beg.set_defaults(func=begin_command)

    end = ps.add_parser("end", help="mark session end + summarize what happened")
    end.add_argument("--repo", default=".", help="path to repo")
    end.add_argument("--note", default="", help="freeform session note")
    end.add_argument("--json", action="store_true", help="structured output")
    end.set_defaults(func=end_command)

    summ = ps.add_parser("summary", help="ad-hoc summary regardless of markers")
    summ.add_argument("--repo", default=".", help="path to repo")
    summ.add_argument("--commits", type=int, default=20, help="number of commits to include")
    summ.add_argument("--json", action="store_true", help="structured output")
    summ.set_defaults(func=summary_command)
