"""lgwks_review — graph-aware, spec-bound code review.

Consumes `repo graph` structural context, git diff, and heuristics to produce a review
artifact. After review, proposes git actions (commit message, branch rename, PR creation)
based on the analysis. The human gate is preserved: `--yes` auto-executes read-only
proposals; mutating actions need explicit confirmation.

//why: `cohere` verifies compiler/framework/idiom gates on a single file. `review`
cross-cuts the whole change: impact analysis via the graph, adversarial heuristics
(trivial assertions, hardcoded secrets, missing error paths), and proposes concrete
next steps. This is the missing G3 adversarial layer for the development supply chain.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_repo import _git, _is_repo, repo_graph


_HEURISTIC_PATTERNS = {
    "trivial_assertion": re.compile(r"assert\s+\d+\s*==\s*\d+|assert\s+True|assert\s+False"),
    "hardcoded_secret": re.compile(r"api[_-]?key\s*=\s*['\"][^'\"]{8,}['\"]|password\s*=\s*['\"][^'\"]+['\"]|token\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
    "bare_except": re.compile(r"except\s*:\s*$|except\s+Exception\s*:\s*.*pass"),
    "missing_docstring": re.compile(r"^\s*(?:def|class)\s+\w+\([^)]*\):\s*\n\s+(?!['\"]|#)"),
    "print_debug": re.compile(r"\bprint\s*\(\s*(?:[\"']debug|TODO|FIXME|HACK)"),
    "todo_without_issue": re.compile(r"#\s*(TODO|FIXME|HACK)(?!\s*#\d+)"),
}


@dataclass
class ReviewFinding:
    file: str
    line: int
    check: str
    severity: str  # info | warn | danger
    message: str
    snippet: str = ""


@dataclass
class ReviewArtifact:
    schema: str = "lgwks.review.v0"
    files_changed: list[str] = field(default_factory=list)
    findings: list[ReviewFinding] = field(default_factory=list)
    graph_impact: list[dict[str, Any]] = field(default_factory=list)
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    commit_suggestion: str = ""


def _git_diff(repo: Path, ref: str = "HEAD") -> tuple[list[str], dict[str, str]]:
    """Return (files, file_to_diff). Default: staged vs HEAD."""
    rc, out = _git(repo, "diff", "--cached", "--name-only")
    files = [ln for ln in out.splitlines() if ln.strip()]
    if not files:
        # nothing staged — compare working tree vs HEAD
        rc, out = _git(repo, "diff", "--name-only")
        files = [ln for ln in out.splitlines() if ln.strip()]
    diffs: dict[str, str] = {}
    for f in files:
        rc, d = _git(repo, "diff", "--cached", "--", f) if (repo / f).exists() else _git(repo, "diff", "HEAD", "--", f)
        diffs[f] = d
    return files, diffs


def _heuristic_scan(path: Path, rel: str) -> list[ReviewFinding]:
    """Run static heuristics on a single file."""
    findings: list[ReviewFinding] = []
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return findings
    lines = source.splitlines()
    for check, pattern in _HEURISTIC_PATTERNS.items():
        for i, ln in enumerate(lines, start=1):
            if pattern.search(ln):
                findings.append(ReviewFinding(
                    file=rel, line=i, check=check,
                    severity="warn" if check in ("todo_without_issue", "missing_docstring", "print_debug") else "danger",
                    message=f"{check.replace('_', ' ')}", snippet=ln.strip()[:80],
                ))
    # AST-level checks
    if path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                # detect assert with literal comparison (already regex covered, but AST is more precise)
                if isinstance(node.test, ast.Compare):
                    # e.g., assert 20 == 20
                    left = node.test.left
                    comparators = node.test.comparators
                    if all(isinstance(n, ast.Constant) for n in [left] + comparators):
                        findings.append(ReviewFinding(
                            file=rel, line=getattr(node, "lineno", 0), check="trivial_assertion_ast",
                            severity="danger", message="assert compares constants — always true/false, not a real test",
                            snippet=lines[getattr(node, "lineno", 1)-1].strip()[:80],
                        ))
    return findings


def _impact_analysis(repo: Path, files: list[str], graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Cross-reference changed files with the codebase graph to find callers and analogs."""
    impacts: list[dict[str, Any]] = []
    file_set = set(files)
    # Find callers: edges where `to` is an import from a changed file
    changed_modules = {f.replace("/", ".").replace(".py", "") for f in files if f.endswith(".py")}
    for edge in graph.get("edges", []):
        if edge.get("type") == "import" and edge.get("from") not in file_set:
            imp = edge.get("to", "")
            for cm in changed_modules:
                if imp == cm or imp.startswith(cm + "."):
                    impacts.append({
                        "kind": "caller",
                        "changed": cm,
                        "caller": edge["from"],
                        "note": f"{edge['from']} imports from changed module {cm}",
                    })
    # De-duplicate
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for imp in impacts:
        key = imp["caller"] + "->" + imp["changed"]
        if key not in seen:
            seen.add(key)
            uniq.append(imp)
    return uniq


def _propose_git_actions(repo: Path, artifact: ReviewArtifact) -> list[dict[str, Any]]:
    """Based on review findings, propose concrete next git actions."""
    actions: list[dict[str, Any]] = []
    has_danger = any(f.severity == "danger" for f in artifact.findings)
    has_warn = any(f.severity == "warn" for f in artifact.findings)

    # Commit message suggestion
    files = ", ".join(artifact.files_changed[:3])
    if has_danger:
        actions.append({
            "verb": "commit",
            "cmd": f'git commit -m "WIP: review findings on {files} (danger detected)"',
            "risk": "mutate",
            "reason": "danger findings present — do not ship without fixing",
        })
    else:
        actions.append({
            "verb": "commit",
            "cmd": f'git commit -m "review: {files}"',
            "risk": "mutate",
            "reason": "clean review — commit with descriptive message",
        })

    # If there are callers impacted, suggest a broader test/review
    if artifact.graph_impact:
        actions.append({
            "verb": "warn",
            "cmd": "",
            "risk": "read",
            "reason": f"{len(artifact.graph_impact)} caller(s) may be affected — run tests before pushing",
        })

    # If no findings, suggest push
    if not has_danger and not has_warn:
        actions.append({
            "verb": "push",
            "cmd": "git push origin $(git branch --show-current)",
            "risk": "mutate",
            "reason": "review clean — safe to push",
        })

    return actions


def review_repo(repo: Path, ref: str = "HEAD") -> ReviewArtifact:
    """Run the full review pipeline."""
    files, diffs = _git_diff(repo, ref)
    artifact = ReviewArtifact(files_changed=files)

    # Heuristic scan on changed files
    for f in files:
        fpath = repo / f
        if fpath.exists() and fpath.is_file():
            artifact.findings.extend(_heuristic_scan(fpath, f))

    # Graph impact analysis
    graph = repo_graph(repo)
    artifact.graph_impact = _impact_analysis(repo, files, graph)

    # Propose actions
    artifact.proposed_actions = _propose_git_actions(repo, artifact)

    # Commit suggestion
    scope = " · ".join(files[:3]) if files else "repo"
    if any(f.severity == "danger" for f in artifact.findings):
        artifact.commit_suggestion = f"review: fix {len([f for f in artifact.findings if f.severity=='danger'])} danger finding(s) in {scope}"
    else:
        artifact.commit_suggestion = f"review: {scope} — clean"

    return artifact


def _render_findings(findings: list[ReviewFinding]) -> list[str]:
    on = ui.color_on()
    out: list[str] = []
    for f in findings:
        color = ui.EMERALD if f.severity == "info" else (ui.AMBER if f.severity == "warn" else ui.RUST)
        out.append(ui.spine(ui.fg(f"  [{f.severity.upper()}] {f.file}:{f.line} — {f.message}", color, on=on), on=on))
        if f.snippet:
            out.append(ui.twig(f.snippet, 1, "proof", on=on))
    return out


def review_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    artifact = review_repo(repo, getattr(args, "ref", "HEAD"))

    if getattr(args, "json", False):
        print(json.dumps({
            "schema": artifact.schema,
            "files_changed": artifact.files_changed,
            "findings": [{"file": f.file, "line": f.line, "check": f.check, "severity": f.severity,
                          "message": f.message, "snippet": f.snippet} for f in artifact.findings],
            "graph_impact": artifact.graph_impact,
            "proposed_actions": artifact.proposed_actions,
            "commit_suggestion": artifact.commit_suggestion,
        }, indent=2))
        return 0

    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · review", f"{len(artifact.files_changed)} file(s)", on=on)
    out.append(ui.spine(on=on))

    if artifact.findings:
        out.append(ui.spine(ui.fg(f"findings ({len(artifact.findings)})", ui.CREAM_DIM, on=on), on=on))
        out.extend(_render_findings(artifact.findings))
    else:
        out.append(ui.spine(ui.fg("✓ No heuristic findings — clean diff.", ui.EMERALD, on=on), on=on))

    if artifact.graph_impact:
        out.append(ui.spine(ui.fg(f"impact ({len(artifact.graph_impact)})", ui.CREAM_DIM, on=on), on=on))
        for imp in artifact.graph_impact[:5]:
            out.append(ui.twig(imp["note"], 1, "imp", on=on))
        if len(artifact.graph_impact) > 5:
            out.append(ui.twig(f"… and {len(artifact.graph_impact)-5} more", 1, "imp", on=on))

    if artifact.proposed_actions:
        out.append(ui.spine(ui.fg("proposed next steps", ui.CREAM_DIM, on=on), on=on))
        for a in artifact.proposed_actions:
            risk_color = ui.EMERALD if a["risk"] == "read" else ui.AMBER
            out.append(ui.twig(f"[{a['verb']}] {a['reason']}", 1, "next", on=on))
            if a["cmd"]:
                out.append(ui.twig(a["cmd"], 2, "cmd", on=on))

    out.append(""); out.append("  " + ui.footer("lgwks · review", on=on)); out.append("")
    print("\n".join(out))

    # Auto-execute read-only proposals if --yes
    if getattr(args, "yes", False):
        for a in artifact.proposed_actions:
            if a["risk"] == "read":
                print(f"  (auto-accepted read-only proposal: {a['reason']})")
            elif a["verb"] in ("commit", "push"):
                print(f"  (mutating proposal skipped without explicit confirmation: {a['verb']})", file=sys.stderr)

    return 0 if not any(f.severity == "danger" for f in artifact.findings) else 1


def add_parser(sub) -> None:
    p = sub.add_parser("review", help="graph-aware code review + proposed git actions")
    p.add_argument("--repo", default=".", help="path to repo")
    p.add_argument("--ref", default="HEAD", help="diff against this ref")
    p.add_argument("--json", action="store_true", help="structured output")
    p.add_argument("--yes", action="store_true", help="auto-accept read-only proposals")
    p.set_defaults(func=review_command)
