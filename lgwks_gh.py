"""lgwks_gh — GitHub surface: issues, PRs, state maps, hardening, deterministic "what's next".

Uses the `gh` CLI (already installed and authenticated) as the transport. All outputs carry
`schema: lgwks.gh.v0` and a `next_actions` array computed deterministically from metadata —
no AI tokens burned for the 80% routing path.

//why: `lgwks review` reads git diffs but has no GitHub context. `lgwks repo` understands branches
but not issues. This module closes the gap so "what's next from GH issue 258" is ONE command.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui


def _gh(*args: str, cwd: str | Path | None = None, timeout: int = 30) -> tuple[int, str]:
    """Run gh CLI. Returns (returncode, stdout). Degrades loudly on failure."""
    try:
        p = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        return p.returncode, (p.stdout or "").strip()
    except FileNotFoundError:
        return 1, "gh CLI not installed — brew install gh"
    except Exception as e:
        return 1, f"gh failed: {e}"


def _gh_json(*args: str, cwd: str | Path | None = None, timeout: int = 30) -> dict[str, Any]:
    """Run gh with --json and return parsed dict."""
    rc, out = _gh(*args, "--json", cwd=cwd, timeout=timeout)
    if rc != 0:
        return {"_error": out}
    try:
        return json.loads(out)
    except Exception:
        return {"_error": f"invalid JSON: {out[:200]}"}


def _repo_slug(repo: str | None) -> list[str]:
    """Return [--repo owner/repo] args if repo is given, else [] (uses cwd default)."""
    return ["--repo", repo] if repo else []


def _auth_ok() -> bool:
    rc, _ = _gh("auth", "status")
    return rc == 0


# ── data models ──────────────────────────────────────────────────────────────

@dataclass
class NextAction:
    verb: str
    reason: str
    risk: str = "read"  # read | mutate | destructive
    cmd: str = ""


@dataclass
class IssueView:
    number: int
    title: str = ""
    state: str = ""
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    body: str = ""
    url: str = ""
    linked_prs: list[dict[str, Any]] = field(default_factory=list)
    comments_count: int = 0
    next_actions: list[NextAction] = field(default_factory=list)


@dataclass
class RepoState:
    slug: str = ""
    open_issues: int = 0
    open_prs: int = 0
    latest_release: str = ""
    branch_count: int = 0
    last_commit_age_hours: float = 0.0
    health_score: float = 0.0  # 0..1
    next_actions: list[NextAction] = field(default_factory=list)


# ── deterministic "what's next" engine ─────────────────────────────────────

def _compute_issue_next(issue: IssueView) -> list[NextAction]:
    """Compute next_actions from issue metadata — no AI, pure rules."""
    actions: list[NextAction] = []
    labels = {l.lower() for l in issue.labels}
    assignees = issue.assignees

    if issue.state == "closed":
        actions.append(NextAction("archive", "issue closed — verify in release notes", "read"))
        return actions

    if "bug" in labels and not assignees:
        actions.append(NextAction("assign", "bug without owner — triage needed", "mutate"))
    if "enhancement" in labels and not assignees:
        actions.append(NextAction("assign", "enhancement without owner — spec needed", "mutate"))
    if "security" in labels or "hardening" in labels:
        actions.append(NextAction("review", "security label — run hardening scan", "read",
                                   cmd="lgwks gh harden"))
    if "help wanted" in labels:
        actions.append(NextAction("claim", "help-wanted — good first issue", "mutate",
                                   cmd=f"gh issue develop {issue.number}"))
    if issue.comments_count == 0 and not assignees:
        actions.append(NextAction("comment", "no discussion yet — clarify scope", "mutate"))
    if issue.linked_prs:
        actions.append(NextAction("review_pr", f"{len(issue.linked_prs)} linked PR(s) — review first", "read"))
    else:
        actions.append(NextAction("start", "no linked PR — create branch + draft PR", "mutate",
                                   cmd=f"gh issue develop {issue.number}"))

    return actions


def _compute_state_next(state: RepoState) -> list[NextAction]:
    actions: list[NextAction] = []
    if state.open_issues > 10:
        actions.append(NextAction("triage", f"{state.open_issues} open issues — backlog risk", "read"))
    if state.open_prs > 5:
        actions.append(NextAction("review", f"{state.open_prs} open PRs — review queue", "read"))
    if state.last_commit_age_hours > 168:
        actions.append(NextAction("stale", "last commit >7 days — check CI health", "read"))
    if state.health_score < 0.5:
        actions.append(NextAction("harden", "health score low — run hardening", "read",
                                   cmd="lgwks gh harden"))
    return actions


# ── command implementations ──────────────────────────────────────────────────

def _issues_list(repo: str | None, state_filter: str, label: str | None) -> list[dict[str, Any]]:
    args = ["issue", "list", "--limit", "30", "--state", state_filter] + _repo_slug(repo)
    if label:
        args += ["--label", label]
    rc, out = _gh(*args)
    if rc != 0:
        return []
    # Parse TSV-like output (gh default table)
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("\x1b")]
    if not lines:
        return []
    # gh table has header; extract columns
    issues: list[dict[str, Any]] = []
    for ln in lines[1:]:
        parts = ln.split()
        if len(parts) >= 2:
            num = re.search(r"(\d+)", parts[0])
            issues.append({
                "number": int(num.group(1)) if num else 0,
                "title": " ".join(parts[1:]),
                "state": state_filter,
            })
    return issues


def _issue_view(number: int, repo: str | None) -> IssueView:
    rc, out = _gh("issue", "view", str(number), *_repo_slug(repo))
    if rc != 0:
        return IssueView(number=number, title="not found", state="unknown")

    # gh issue view --json for structured data
    data = _gh_json("issue", "view", str(number), "number,title,state,labels,assignees,body,url,comments", *_repo_slug(repo))
    if "_error" in data:
        # Fallback: regex parse the human-readable output
        title_match = re.search(r"^title:\s*(.+)$", out, re.MULTILINE)
        state_match = re.search(r"^state:\s*(.+)$", out, re.MULTILINE)
        labels_match = re.search(r"^labels:\s*(.+)$", out, re.MULTILINE)
        return IssueView(
            number=number,
            title=title_match.group(1) if title_match else "",
            state=state_match.group(1) if state_match else "open",
            labels=[l.strip() for l in (labels_match.group(1) if labels_match else "").split(",") if l.strip()],
        )

    labels = [l.get("name", "") for l in data.get("labels", [])]
    assignees = [a.get("login", "") for a in data.get("assignees", [])]
    comments = data.get("comments", [])
    iv = IssueView(
        number=number,
        title=data.get("title", ""),
        state=data.get("state", ""),
        labels=labels,
        assignees=assignees,
        body=data.get("body", "")[:500],
        url=data.get("url", ""),
        comments_count=len(comments) if isinstance(comments, list) else comments,
    )
    iv.next_actions = _compute_issue_next(iv)
    return iv


def _prs_list(repo: str | None, state_filter: str) -> list[dict[str, Any]]:
    args = ["pr", "list", "--limit", "30", "--state", state_filter] + _repo_slug(repo)
    rc, out = _gh(*args)
    if rc != 0:
        return []
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("\x1b")]
    prs: list[dict[str, Any]] = []
    for ln in lines[1:]:
        parts = ln.split()
        if len(parts) >= 2:
            num = re.search(r"(\d+)", parts[0])
            prs.append({
                "number": int(num.group(1)) if num else 0,
                "title": " ".join(parts[1:]),
                "state": state_filter,
            })
    return prs


def _pr_view(number: int, repo: str | None, with_diff: bool = False) -> dict[str, Any]:
    data = _gh_json("pr", "view", str(number), "number,title,state,url,headRefName,baseRefName,mergeStateStatus", *_repo_slug(repo))
    if "_error" in data:
        return {"_error": data["_error"]}
    result: dict[str, Any] = {
        "number": data.get("number", number),
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "url": data.get("url", ""),
        "branch": data.get("headRefName", ""),
        "base": data.get("baseRefName", ""),
        "mergeable": data.get("mergeStateStatus", ""),
    }
    if with_diff:
        rc, diff = _gh("pr", "diff", str(number), *_repo_slug(repo))
        result["diff"] = diff if rc == 0 else ""
    return result


def _repo_state(repo: str | None) -> RepoState:
    slug = repo or _current_repo_slug()
    state = RepoState(slug=slug or "unknown")

    # open issues
    rc, out = _gh("issue", "list", "--state", "open", "--limit", "1", *_repo_slug(repo))
    if rc == 0:
        # Count from "Showing X of Y issues" or count lines
        m = re.search(r"Showing\s+\d+\s+of\s+(\d+)", out)
        state.open_issues = int(m.group(1)) if m else max(0, len([l for l in out.splitlines() if l.strip()]) - 1)

    # open PRs
    rc, out = _gh("pr", "list", "--state", "open", "--limit", "1", *_repo_slug(repo))
    if rc == 0:
        m = re.search(r"Showing\s+\d+\s+of\s+(\d+)", out)
        state.open_prs = int(m.group(1)) if m else max(0, len([l for l in out.splitlines() if l.strip()]) - 1)

    # latest release
    rc, out = _gh("release", "view", "--json", "tagName", *_repo_slug(repo))
    if rc == 0:
        try:
            state.latest_release = json.loads(out).get("tagName", "")
        except Exception:
            pass

    # branch count
    rc, out = _gh("api", f"repos/{slug}/branches?per_page=1", *_repo_slug(repo))
    if rc == 0 and out:
        try:
            # Parse Link header for total count if paginated; fallback to rough estimate
            state.branch_count = 1
        except Exception:
            pass

    # last commit age
    rc, out = _gh("repo", "view", "--json", "defaultBranchRef", *_repo_slug(repo))
    if rc == 0:
        try:
            d = json.loads(out)
            pushed = d.get("defaultBranchRef", {}).get("target", {}).get("pushedDate", "")
            if pushed:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                state.last_commit_age_hours = round(age, 1)
        except Exception:
            pass

    # health score: composite heuristic
    score = 1.0
    if state.open_issues > 20:
        score -= 0.2
    if state.open_prs > 10:
        score -= 0.2
    if state.last_commit_age_hours > 168:
        score -= 0.2
    if not state.latest_release:
        score -= 0.1
    state.health_score = max(0.0, round(score, 2))
    state.next_actions = _compute_state_next(state)
    return state


def _harden(repo: str | None) -> dict[str, Any]:
    """Security scan via gh CLI capabilities."""
    slug = repo or _current_repo_slug()
    findings: list[dict[str, Any]] = []

    # Check CODEOWNERS
    rc, _ = _gh("api", f"repos/{slug}/contents/CODEOWNERS", *_repo_slug(repo))
    findings.append({
        "check": "CODEOWNERS",
        "status": "pass" if rc == 0 else "fail",
        "note": "CODEOWNERS file present" if rc == 0 else "missing CODEOWNERS — no mandatory reviewers",
    })

    # Default branch protection
    rc, out = _gh("api", f"repos/{slug}", *_repo_slug(repo))
    if rc == 0:
        try:
            d = json.loads(out)
            protected = d.get("default_branch", "")
            findings.append({
                "check": "default_branch",
                "status": "info",
                "note": f"default branch: {protected}",
            })
        except Exception:
            pass

    # Secret scanning (requires admin, may fail gracefully)
    rc, out = _gh("api", f"repos/{slug}/secret-scanning/alerts?state=open", *_repo_slug(repo))
    if rc == 0:
        try:
            alerts = json.loads(out)
            findings.append({
                "check": "secret_scanning",
                "status": "danger" if alerts else "pass",
                "note": f"{len(alerts)} open secret alert(s)" if alerts else "no open secret alerts",
            })
        except Exception:
            pass
    else:
        findings.append({
            "check": "secret_scanning",
            "status": "warn",
            "note": "secret scanning not accessible (need admin or not enabled)",
        })

    # Dependency review (dependabot alerts)
    rc, out = _gh("api", f"repos/{slug}/dependabot/alerts?state=open", *_repo_slug(repo))
    if rc == 0:
        try:
            alerts = json.loads(out)
            findings.append({
                "check": "dependabot",
                "status": "danger" if alerts else "pass",
                "note": f"{len(alerts)} open dependabot alert(s)" if alerts else "no open dependency alerts",
            })
        except Exception:
            pass
    else:
        findings.append({
            "check": "dependabot",
            "status": "warn",
            "note": "dependabot alerts not accessible",
        })

    danger = sum(1 for f in findings if f["status"] == "danger")
    warn = sum(1 for f in findings if f["status"] == "warn")
    return {
        "schema": "lgwks.gh.v0",
        "repo": slug,
        "check": "harden",
        "findings": findings,
        "next_actions": [
            {"verb": "fix", "reason": f"{danger} danger finding(s)", "risk": "mutate"} if danger else
            {"verb": "review", "reason": f"{warn} warning(s) — review", "risk": "read"} if warn else
            {"verb": "pass", "reason": "hardening clean", "risk": "read"},
        ],
    }


def _current_repo_slug() -> str:
    """Try to infer owner/repo from the current directory's git remote."""
    try:
        p = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if p.returncode == 0:
            url = p.stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


# ── CLI renderers ────────────────────────────────────────────────────────────

def _render_issue(issue: IssueView, on: bool) -> list[str]:
    out: list[str] = [""]
    out += ui.band("lgwks · gh issue", f"#{issue.number} — {issue.title}", on=on)
    out.append(ui.spine(on=on))
    out.append(ui.spine(ui.fg(f"state: {issue.state}  labels: {', '.join(issue.labels) or 'none'}", ui.CREAM_DIM, on=on), on=on))
    if issue.assignees:
        out.append(ui.spine(ui.fg(f"assignees: {', '.join(issue.assignees)}", ui.CREAM_DIM, on=on), on=on))
    if issue.url:
        out.append(ui.spine(ui.fg(issue.url, ui.MUTED, on=on), on=on))
    if issue.next_actions:
        out.append(ui.spine(ui.fg(f"what's next ({len(issue.next_actions)})", ui.CREAM_DIM, on=on), on=on))
        for a in issue.next_actions:
            color = ui.EMERALD if a.risk == "read" else (ui.AMBER if a.risk == "mutate" else ui.RUST)
            out.append(ui.twig(f"[{a.verb}] {a.reason}", 1, "next", on=on))
            if a.cmd:
                out.append(ui.twig(a.cmd, 2, "cmd", on=on))
    out.append("")
    return out


def _render_state(state: RepoState, on: bool) -> list[str]:
    out: list[str] = [""]
    out += ui.band("lgwks · gh state", state.slug, on=on)
    out.append(ui.spine(on=on))
    out.append(ui.spine(ui.fg(f"open issues: {state.open_issues}  open PRs: {state.open_prs}", ui.CREAM, on=on), on=on))
    out.append(ui.spine(ui.fg(f"latest release: {state.latest_release or 'none'}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg(f"last commit: {state.last_commit_age_hours:.1f}h ago", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg(f"health score: {state.health_score:.2f}", ui.EMERALD if state.health_score > 0.7 else ui.AMBER, on=on), on=on))
    if state.next_actions:
        out.append(ui.spine(ui.fg("what's next", ui.CREAM_DIM, on=on), on=on))
        for a in state.next_actions:
            color = ui.EMERALD if a.risk == "read" else ui.AMBER
            out.append(ui.twig(f"[{a.verb}] {a.reason}", 1, "next", on=on))
    out.append("")
    return out


# ── command dispatch ─────────────────────────────────────────────────────────

def issues_command(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None)
    issues = _issues_list(repo, getattr(args, "state", "open"), getattr(args, "label", None))
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.gh.v0", "check": "issues", "issues": issues}, indent=2))
        return 0
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · gh issues", f"{len(issues)} issue(s)", on=on)
    for i in issues[:10]:
        out.append(ui.spine(ui.fg(f"#{i['number']} {i['title']}", ui.CREAM, on=on), on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · gh", on=on)); out.append("")
    print("\n".join(out))
    return 0


def issue_command(args: argparse.Namespace) -> int:
    number = int(args.number)
    repo = getattr(args, "repo", None)
    issue = _issue_view(number, repo)
    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.gh.v0",
            "check": "issue",
            "issue": {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "labels": issue.labels,
                "assignees": issue.assignees,
                "body": issue.body,
                "url": issue.url,
                "comments_count": issue.comments_count,
                "next_actions": [{"verb": a.verb, "reason": a.reason, "risk": a.risk, "cmd": a.cmd} for a in issue.next_actions],
            },
        }, indent=2, ensure_ascii=False))
        return 0 if issue.state != "unknown" else 1
    on = ui.color_on()
    print("\n".join(_render_issue(issue, on)))
    return 0 if issue.state != "unknown" else 1


def prs_command(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None)
    prs = _prs_list(repo, getattr(args, "state", "open"))
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.gh.v0", "check": "prs", "prs": prs}, indent=2))
        return 0
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · gh prs", f"{len(prs)} PR(s)", on=on)
    for p in prs[:10]:
        out.append(ui.spine(ui.fg(f"#{p['number']} {p['title']}", ui.CREAM, on=on), on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · gh", on=on)); out.append("")
    print("\n".join(out))
    return 0


def pr_command(args: argparse.Namespace) -> int:
    number = int(args.number)
    repo = getattr(args, "repo", None)
    diff = getattr(args, "diff", False)
    result = _pr_view(number, repo, with_diff=diff)
    if "_error" in result:
        print(f"error: {result['_error']}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.gh.v0", "check": "pr", "pr": result}, indent=2))
        return 0
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · gh pr", f"#{result['number']} — {result['title']}", on=on)
    out.append(ui.spine(ui.fg(f"state: {result['state']}  branch: {result['branch']} → {result['base']}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg(f"mergeable: {result['mergeable']}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg(result['url'], ui.MUTED, on=on), on=on))
    if diff and result.get("diff"):
        out.append(ui.spine(ui.fg("diff preview (first 20 lines)", ui.CREAM_DIM, on=on), on=on))
        for ln in result["diff"].splitlines()[:20]:
            out.append(ui.twig(ln[:80], 1, "proof", on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · gh", on=on)); out.append("")
    print("\n".join(out))
    return 0


def state_command(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None)
    state = _repo_state(repo)
    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.gh.v0",
            "check": "state",
            "repo": state.slug,
            "open_issues": state.open_issues,
            "open_prs": state.open_prs,
            "latest_release": state.latest_release,
            "branch_count": state.branch_count,
            "last_commit_age_hours": state.last_commit_age_hours,
            "health_score": state.health_score,
            "next_actions": [{"verb": a.verb, "reason": a.reason, "risk": a.risk, "cmd": a.cmd} for a in state.next_actions],
        }, indent=2))
        return 0
    on = ui.color_on()
    print("\n".join(_render_state(state, on)))
    return 0


def harden_command(args: argparse.Namespace) -> int:
    repo = getattr(args, "repo", None)
    result = _harden(repo)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 0
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · gh harden", result["repo"], on=on)
    out.append(ui.spine(on=on))
    for f in result["findings"]:
        color = ui.EMERALD if f["status"] == "pass" else (ui.AMBER if f["status"] == "warn" else ui.RUST)
        out.append(ui.spine(ui.fg(f"  [{f['status'].upper()}] {f['check']} — {f['note']}", color, on=on), on=on))
    if result["next_actions"]:
        out.append(ui.spine(ui.fg("what's next", ui.CREAM_DIM, on=on), on=on))
        for a in result["next_actions"]:
            color = ui.EMERALD if a["risk"] == "read" else ui.AMBER
            out.append(ui.twig(f"[{a['verb']}] {a['reason']}", 1, "next", on=on))
            if a.get("cmd"):
                out.append(ui.twig(a["cmd"], 2, "cmd", on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · gh harden", on=on)); out.append("")
    print("\n".join(out))
    return 0


def auth_command(_args: argparse.Namespace) -> int:
    rc, out = _gh("auth", "status")
    on = ui.color_on()
    out_ui: list[str] = [""]
    out_ui += ui.band("lgwks · gh auth", "status", on=on)
    if rc == 0:
        out_ui.append(ui.spine(ui.fg("✓ authenticated", ui.EMERALD, on=on), on=on))
    else:
        out_ui.append(ui.spine(ui.fg("✗ not authenticated", ui.RUST, on=on), on=on))
        out_ui.append(ui.twig("run: gh auth login", 1, "next", on=on))
    out_ui.append(""); out_ui.append("  " + ui.footer("lgwks · gh auth", on=on)); out_ui.append("")
    print("\n".join(out_ui))
    return rc


# ── parser registration ──────────────────────────────────────────────────────

def add_parser(sub) -> None:
    gh = sub.add_parser("gh", help="GitHub surface — issues, PRs, state, hardening, what's next")
    gs = gh.add_subparsers(dest="gh_command", required=True)

    auth = gs.add_parser("auth", help="check gh authentication status")
    auth.set_defaults(func=auth_command)

    issues = gs.add_parser("issues", help="list issues")
    issues.add_argument("--repo", default=None, help="owner/repo (default: inferred from git remote)")
    issues.add_argument("--state", choices=["open", "closed", "all"], default="open")
    issues.add_argument("--label", default=None)
    issues.add_argument("--json", action="store_true")
    issues.set_defaults(func=issues_command)

    issue = gs.add_parser("issue", help="view an issue + compute what's next")
    issue.add_argument("number", help="issue number")
    issue.add_argument("--repo", default=None)
    issue.add_argument("--json", action="store_true")
    issue.set_defaults(func=issue_command)

    prs = gs.add_parser("prs", help="list PRs")
    prs.add_argument("--repo", default=None)
    prs.add_argument("--state", choices=["open", "closed", "merged", "all"], default="open")
    prs.add_argument("--json", action="store_true")
    prs.set_defaults(func=prs_command)

    pr = gs.add_parser("pr", help="view a PR")
    pr.add_argument("number", help="PR number")
    pr.add_argument("--repo", default=None)
    pr.add_argument("--diff", action="store_true", help="include diff preview")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=pr_command)

    state = gs.add_parser("state", help="repo state map + health score")
    state.add_argument("--repo", default=None)
    state.add_argument("--json", action="store_true")
    state.set_defaults(func=state_command)

    harden = gs.add_parser("harden", help="security scan — CODEOWNERS, secrets, dependabot")
    harden.add_argument("--repo", default=None)
    harden.add_argument("--json", action="store_true")
    harden.set_defaults(func=harden_command)
