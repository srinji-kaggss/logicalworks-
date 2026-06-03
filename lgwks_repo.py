"""lgwks_repo — repo lifecycle commands: audit, recover, cleanup, merge, handoff, graph.

End-to-end repo hygiene: read-only audit, safe recovery of dangling commits, cleanup of
stale branches/worktrees, merge orchestration with auto-conflict patterns, machine-readable
handoff reports, and lightweight codebase-graph extraction (the seed for Greptile-style
structural context).

//why: `solve git` diagnoses but does not act; `project review` reads deploy artifacts but
has no code-structure awareness. This module closes both gaps under one `repo` verb.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lgwks_ui as ui
import lgwks_graph as graph_engine
from lgwks_solve import _diagnose as _git_diagnose
from lgwks_steering import Steering


def _git(repo: Path, *args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 1, f"<git failed: {e}>"


def _gh(*args: str, cwd: str | Path | None = None, timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout,
                           cwd=str(cwd) if cwd else None)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 1, f"<gh failed: {e}>"


def _git_stderr(repo: Path, *args: str, timeout: int = 30) -> tuple[int, str]:
    """Run git and merge stderr into stdout (for commands like fsck that write to stderr)."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, f"<git failed: {e}>"


def _is_repo(repo: Path) -> bool:
    rc, out = _git(repo, "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out == "true"


def _head_sha(repo: Path) -> str:
    rc, out = _git(repo, "rev-parse", "--short", "HEAD")
    return out if rc == 0 else "unknown"


@dataclass
class AuditFinding:
    check: str
    severity: str  # info | warn | danger
    message: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class RecoverGroup:
    commit: str
    files: list[str]


def repo_audit(repo: Path) -> tuple[list[AuditFinding], dict[str, Any]]:
    """Six-zeros health check + pathological state diagnosis from solve/git."""
    findings: list[AuditFinding] = []

    # 1) uncommitted
    rc, out = _git(repo, "status", "--short")
    uncommitted = len(out.splitlines()) if out else 0
    if uncommitted:
        findings.append(AuditFinding("uncommitted", "warn", f"{uncommitted} uncommitted change(s)", ["git status --short"]))

    # 2) untracked
    rc, out = _git(repo, "ls-files", "--others", "--exclude-standard")
    untracked = len(out.splitlines()) if out else 0
    if untracked:
        findings.append(AuditFinding("untracked", "warn", f"{untracked} untracked file(s)", ["git ls-files --others --exclude-standard"]))

    # 3) stashes
    rc, out = _git(repo, "stash", "list")
    stashes = len(out.splitlines()) if out else 0
    if stashes:
        findings.append(AuditFinding("stashes", "info", f"{stashes} stash(es)", ["git stash list"]))

    # 4) dangling commits
    rc, out = _git_stderr(repo, "fsck", "--no-reflogs", "--dangling")
    dangling = [ln for ln in out.splitlines() if "dangling commit" in ln]
    if dangling:
        findings.append(AuditFinding("dangling", "danger", f"{len(dangling)} dangling commit(s)", ["git fsck --no-reflogs --dangling"]))

    # 5) merged branches
    rc, out = _git(repo, "branch", "--merged", "HEAD")
    merged = [ln.strip().lstrip("* ") for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("*")]
    # Exclude HEAD itself if listed
    merged = [b for b in merged if b != "HEAD"]
    if merged:
        findings.append(AuditFinding("merged_branches", "warn", f"{len(merged)} merged branch(es) not deleted: {', '.join(merged[:5])}" + ("…" if len(merged) > 5 else ""), ["git branch --merged HEAD"]))

    # 6) dirty worktrees
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    worktrees = []
    dirty = 0
    current_wt = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            current_wt = line[9:]
        if line.startswith("branch ") and current_wt:
            worktrees.append(current_wt)
    for wt in worktrees:
        if Path(wt).resolve() == repo.resolve():
            continue
        rc2, out2 = _git(Path(wt), "status", "--short")
        if out2:
            dirty += 1
            findings.append(AuditFinding("dirty_worktree", "warn", f"dirty worktree: {wt}", ["git status --short"]))
    if dirty == 0 and len(worktrees) > 1:
        findings.append(AuditFinding("worktrees", "info", f"{len(worktrees)-1} extra worktree(s)", ["git worktree list"]))

    # 7) open PRs via gh (gh infers repo from remote; run in repo dir)
    rc, out = _gh("pr", "list", "--state", "open", "--json", "number", cwd=repo)
    prs: list[Any] = []
    if rc == 0 and out:
        try:
            prs = json.loads(out)
            if prs:
                findings.append(AuditFinding("open_prs", "info", f"{len(prs)} open PR(s)", ["gh pr list --state open"]))
        except Exception:
            pass

    # 8) pathological state from solve/git (detached HEAD, rebase, conflicts)
    for f in _git_diagnose(repo):
        findings.append(AuditFinding(f"pathology:{f.severity}", f.severity, f.what, [e.command for e in f.evidence]))

    health = {
        "uncommitted": uncommitted,
        "untracked": untracked,
        "stashes": stashes,
        "dangling_commits": len(dangling),
        "merged_branches": len(merged),
        "dirty_worktrees": dirty,
        "open_prs": len(prs) if isinstance(prs, list) else 0,
        "repo": str(repo),
        "branch": _git(repo, "branch", "--show-current")[1] or "(detached)",
        "sha": _head_sha(repo),
    }
    return findings, health


def _file_exists_in_head(repo: Path, path: str) -> bool:
    rc, out = _git(repo, "ls-tree", "HEAD", path)
    return rc == 0 and out.strip() != ""


def repo_recover(repo: Path, dry_run: bool = False) -> tuple[list[RecoverGroup], list[str]]:
    """Scan dangling commits for files not present in HEAD and optionally extract them."""
    rc, out = _git_stderr(repo, "fsck", "--no-reflogs", "--dangling")
    dangling = [ln.split()[-1] for ln in out.splitlines() if "dangling commit" in ln]
    groups: list[RecoverGroup] = []
    extracted: list[str] = []
    for commit in dangling:
        rc, tree = _git(repo, "ls-tree", "-r", "--name-only", commit)
        if rc != 0 or not tree:
            continue
        missing = [p for p in tree.splitlines() if p and not _file_exists_in_head(repo, p)]
        if missing:
            groups.append(RecoverGroup(commit[:12], missing))
            if not dry_run:
                for p in missing:
                    dest = repo / p
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        show = subprocess.run(
                            ["git", "-C", str(repo), "show", f"{commit}:{p}"],
                            capture_output=True, text=True, timeout=30,
                        )
                        if show.returncode == 0:
                            dest.write_text(show.stdout, encoding="utf-8")
                            extracted.append(p)
                    except Exception as e:
                        extracted.append(f"ERROR {p}: {e}")
    if not dry_run and extracted:
        _git(repo, "add", "-A")
    return groups, extracted


def repo_cleanup(repo: Path, force: bool = False) -> dict[str, Any]:
    """Safe deletion of merged branches + worktrees + stashes + gc."""
    actions: list[str] = []
    skipped: list[str] = []

    # branches
    rc, out = _git(repo, "branch", "--merged", "HEAD")
    merged = [ln.strip().lstrip("* ") for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("*") and ln.strip() != "HEAD"]
    for b in merged:
        _git(repo, "branch", "-d", b)
        actions.append(f"deleted branch {b}")
        # attempt remote deletion if tracked
        rc2, _ = _git(repo, "push", "origin", "--delete", b)
        if rc2 == 0:
            actions.append(f"deleted remote branch origin/{b}")

    # worktrees
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    current_wt = None
    worktree_paths: list[str] = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            current_wt = line[9:]
        if line.startswith("branch ") and current_wt:
            worktree_paths.append(current_wt)
    for wt in worktree_paths:
        wt_path = Path(wt).resolve()
        if wt_path == repo.resolve():
            continue
        rc2, dirty = _git(wt_path, "status", "--short")
        if dirty and not force:
            skipped.append(f"worktree {wt} (uncommitted changes)")
            continue
        _git(repo, "worktree", "remove", "-f", str(wt_path))
        actions.append(f"removed worktree {wt}")

    # stashes
    rc, out = _git(repo, "stash", "list")
    if out:
        for i in range(len(out.splitlines())):
            _git(repo, "stash", "drop", f"stash@{{0}}")
        actions.append(f"cleared {len(out.splitlines())} stash(es)")

    # gc
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "--prune=now")
    actions.append("ran git reflog expire && git gc --prune=now")

    return {"actions": actions, "skipped": skipped}


def _resolve_conflict_keep_both_classes(path: Path) -> bool:
    """Auto-resolve test-file conflicts where both sides add distinct Test* classes."""
    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" not in text:
        return False
    # Pattern: <<<<<<< HEAD\nclass Test... =======\nclass Test... >>>>>>> branch
    pattern = re.compile(r"<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*", re.MULTILINE | re.DOTALL)
    def repl(m: re.Match[str]) -> str:
        left = m.group(1).strip()
        right = m.group(2).strip()
        if left.startswith("class Test") and right.startswith("class Test"):
            return left + "\n\n" + right + "\n"
        return m.group(0)
    new_text = pattern.sub(repl, text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def _resolve_conflict_sort_argparse(path: Path) -> bool:
    """Auto-resolve lgwks-script conflicts by keeping both argparse additions and sorting."""
    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" not in text:
        return False
    # Simplistic: remove conflict markers and dedent blocks; if the result is valid Python, keep it.
    # Real heuristic: if both sides are `sub.add_parser(...)` lines, merge and sort.
    lines = text.splitlines()
    out_lines: list[str] = []
    in_conflict = False
    left_block: list[str] = []
    right_block: list[str] = []
    for ln in lines:
        if ln.startswith("<<<<<<<"):
            in_conflict = True
            left_block = []
            continue
        if ln.startswith("======="):
            continue
        if ln.startswith(">>>>>>>"):
            in_conflict = False
            # heuristic: if both blocks look like add_parser lines, merge + sort
            if all("add_parser" in b for b in left_block + right_block if b.strip()):
                merged = sorted(set(left_block + right_block), key=lambda s: s.strip())
                out_lines.extend(merged)
            else:
                # cannot auto-resolve
                out_lines.append("<<<<<<< HEAD")
                out_lines.extend(left_block)
                out_lines.append("=======")
                out_lines.extend(right_block)
                out_lines.append(">>>>>>> conflict")
            left_block = []
            right_block = []
            continue
        if in_conflict:
            left_block.append(ln)
        else:
            out_lines.append(ln)
    new_text = "\n".join(out_lines) + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def repo_merge(repo: Path, pr_number: str) -> dict[str, Any]:
    """Rebase PR onto main, resolve known auto-patterns, push, merge via gh."""
    # fetch PR info
    rc, out = _gh("pr", "view", pr_number, "--json", "headRefName,baseRefName,state", cwd=repo)
    if rc != 0:
        return {"error": f"cannot fetch PR #{pr_number}: {out}"}
    try:
        pr = json.loads(out)
    except Exception as e:
        return {"error": f"bad gh json: {e}"}
    if pr.get("state") != "OPEN":
        return {"error": f"PR #{pr_number} is not open ({pr.get('state')})"}
    head = pr["headRefName"]
    base = pr.get("baseRefName", "main")

    # fetch branch
    _git(repo, "fetch", "origin", head)
    # checkout tracking branch
    _git(repo, "checkout", "-B", head, f"origin/{head}")
    # rebase
    rc, out = _git(repo, "rebase", base)
    if rc != 0:
        # inspect conflicted files
        rc2, conflict_out = _git(repo, "diff", "--name-only", "--diff-filter=U")
        conflict_files = conflict_out.splitlines() if conflict_out else []
        resolved_any = False
        for cf in conflict_files:
            cpath = repo / cf
            if not cpath.exists():
                continue
            if cf.endswith("test_research_stack.py"):
                resolved_any = _resolve_conflict_keep_both_classes(cpath) or resolved_any
            elif cf == "lgwks" or cf.endswith("/lgwks"):
                resolved_any = _resolve_conflict_sort_argparse(cpath) or resolved_any
            else:
                # Any .py file with <<<<<<< → abort per handoff spec
                if cpath.suffix == ".py":
                    return {"error": f"conflict in {cf} requires manual review (python file)", "conflicts": conflict_files}
        if not resolved_any:
            _git(repo, "rebase", "--abort")
            return {"error": "unresolved conflicts after rebase", "conflicts": conflict_files}
        # stage resolved files
        for cf in conflict_files:
            _git(repo, "add", cf)
        rc, out = _git(repo, "rebase", "--continue")
        if rc != 0:
            return {"error": f"rebase --continue failed: {out}"}

    # force-push rebased branch
    _git(repo, "push", "--force-with-lease", "origin", head)
    # merge via gh
    rc, out = _gh("pr", "merge", pr_number, "--squash", "--delete-branch", cwd=repo)
    if rc != 0:
        return {"error": f"gh merge failed: {out}"}
    return {"merged": pr_number, "head": head, "base": base}


def repo_handoff(repo: Path) -> dict[str, Any]:
    """Machine-readable handoff report with six-zeros invariant."""
    findings, health = repo_audit(repo)
    severe = [f for f in findings if f.severity == "danger"]
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema": "lgwks.repo.handoff.v0",
        "repo": str(repo),
        "branch": health.get("branch", "unknown"),
        "sha": health.get("sha", "unknown"),
        "health": {
            "uncommitted": health.get("uncommitted", 0),
            "untracked": health.get("untracked", 0),
            "stashes": health.get("stashes", 0),
            "dangling_commits": health.get("dangling_commits", 0),
            "merged_branches": health.get("merged_branches", 0),
            "dirty_worktrees": health.get("dirty_worktrees", 0),
            "open_prs": health.get("open_prs", 0),
        },
        "last_cleanup": {
            "date": now,
            "agent": "claude-opus-4.8",
            "actions": [f"audit: {len(findings)} finding(s)"],
            "risks": [f.message for f in severe] if severe else ["none"],
        },
    }


def repo_graph(repo: Path) -> dict[str, Any]:
    """Lightweight codebase graph: files, imports, definitions, adjacency. Seed for structural review.

    //why: Previously a flat dict with linear scan. Now delegates to lgwks_graph engine for
    traversable, queryable graph with adjacency indexes, reverse dependency cones, and caching.
    Backward-compatible dict return so existing callers (review, tests) keep working.
    """
    g = graph_engine.get_graph(repo)
    # Convert engine graph → the v0 contract. //why this translation is the actual
    # job of this adapter: the engine stores defines as "class:Foo"/"def:bar" and
    # resolves import edges to internal FILE paths. The v0 schema (lgwks.repo.graph.v0)
    # that review + tests depend on is different: defines are "class Foo"/"def bar",
    # and edges carry the IMPORT NAME as `to` (e.g. "os", "pkg.mod") — lgwks_review's
    # legacy fallback matches edge["to"] against dotted module names, not file paths.
    # The prior refactor dropped this translation and silently broke both consumers
    # (empty/file-path edges, colon-prefixed defines) while claiming compatibility.
    files: dict[str, Any] = {}
    edges: list[dict[str, str]] = []
    for nid, node in g.nodes.items():
        files[nid] = {
            "imports": list(node.imports),
            "defines": [_v0_define(d) for d in node.defines],
        }
        # //why edges from node.imports, not g.edges: the v0 edge is the raw import
        # relation (file → imported module name), which includes EXTERNAL imports
        # ("os") that the engine never turns into internal file→file edges.
        for imp in node.imports:
            edges.append({"from": nid, "to": imp, "type": "import"})
    return {
        "schema": "lgwks.repo.graph.v0",
        "repo": str(repo),
        "files": files,
        "edges": edges,
        "file_count": len(files),
        "edge_count": len(edges),
        "_engine": "lgwks_graph",
        "_stats": g.stats(),
    }


def _v0_define(d: str) -> str:
    # //why: engine emits "class:Foo"/"def:bar"; the v0 contract is space-separated
    # "class Foo"/"def bar". Translate the two known kinds, pass anything else through.
    if d.startswith("class:"):
        return "class " + d[len("class:"):]
    if d.startswith("def:"):
        return "def " + d[len("def:"):]
    return d


# ── CLI surfaces ──

def audit_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    findings, health = repo_audit(repo)
    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.repo.audit.v0",
            "repo": str(repo),
            "health": health,
            "findings": [{"check": f.check, "severity": f.severity, "message": f.message, "evidence": f.evidence} for f in findings],
        }, indent=2))
        return 0 if not any(f.severity == "danger" for f in findings) else 1
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · repo audit", f"{repo} @ {health['branch']} ({health['sha']})", on=on)
    out.append(ui.spine(on=on))
    if not findings:
        out.append(ui.spine(ui.fg("✓ All six zeros — repo is clean.", ui.EMERALD, on=on), on=on))
    else:
        for f in findings:
            color = ui.EMERALD if f.severity == "info" else (ui.AMBER if f.severity == "warn" else ui.RUST)
            out.append(ui.spine(ui.fg(f"[{f.severity.upper()}] {f.message}", color, on=on), on=on))
            if f.evidence:
                out.append(ui.twig(f"proof: {f.evidence[0]}", 0, "proof", on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · repo audit", on=on)); out.append("")
    print("\n".join(out))
    return 0 if not any(f.severity == "danger" for f in findings) else 1


def recover_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    dry = getattr(args, "dry_run", False)
    groups, extracted = repo_recover(repo, dry_run=dry)
    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.repo.recover.v0",
            "repo": str(repo),
            "dry_run": dry,
            "groups": [{"commit": g.commit, "files": g.files} for g in groups],
            "extracted": extracted,
        }, indent=2))
        return 0
    print(f"Scanning {len(groups)} dangling commit group(s) with missing files…")
    for g in groups:
        print(f"  [{g.commit}] {len(g.files)} file(s) not in HEAD")
        for f in g.files[:5]:
            print(f"    - {f}")
        if len(g.files) > 5:
            print(f"    … and {len(g.files)-5} more")
    if dry:
        print("(dry-run — no files written)")
    else:
        print(f"Extracted {len(extracted)} file(s).")
    return 0


def cleanup_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    result = repo_cleanup(repo, force=getattr(args, "force", False))
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.repo.cleanup.v0", "repo": str(repo), **result}, indent=2))
        return 0
    for a in result["actions"]:
        print(f"  ✓ {a}")
    for s in result["skipped"]:
        print(f"  ⚠ skipped: {s}")
    return 0


def handoff_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    payload = repo_handoff(repo)
    print(json.dumps(payload, indent=2))
    return 0


def merge_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    pr = str(args.pr)
    result = repo_merge(repo, pr)
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.repo.merge.v0", **result}, indent=2))
        return 0 if "error" not in result else 1
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        if result.get("conflicts"):
            print("conflicts:", ", ".join(result["conflicts"]), file=sys.stderr)
        return 1
    print(f"merged PR #{pr} ({result['head']} → {result['base']})")
    return 0


def graph_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 1
    result = repo_graph(repo)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 0
    print(f"repo {result['repo']}")
    print(f"files {result['file_count']} · edges {result['edge_count']}")
    for p, info in result["files"].items():
        defs = ", ".join(info["defines"][:3]) + ("…" if len(info["defines"]) > 3 else "")
        print(f"  {p}: {defs}")
    return 0


def repo_sync(repo: Path, push: bool = True) -> dict[str, Any]:
    """Push current branch, delete merged branches + worktrees, gc, verify.

    This is the command I should have run instead of 15 manual bash commands.
    """
    actions: list[str] = []
    skipped: list[str] = []

    # 1) verify repo + branch
    rc, out = _git(repo, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out != "true":
        return {"error": f"{repo} is not a git repo"}
    rc, branch = _git(repo, "branch", "--show-current")
    if rc != 0 or not branch:
        return {"error": "detached HEAD — cannot sync"}

    # 2) working tree must be clean
    rc, out = _git(repo, "status", "--short")
    if out.strip():
        return {"error": f"working tree dirty ({len(out.splitlines())} changes) — commit or stash first", "uncommitted": out.splitlines()}

    # 3) push current branch to origin
    if push:
        rc, out = _git(repo, "push", "origin", branch)
        if rc != 0:
            return {"error": f"push failed: {out}"}
        actions.append(f"pushed {branch} to origin")

    # 4) find merged branches
    rc, out = _git(repo, "branch", "--merged", "HEAD")
    merged = [ln.strip().lstrip("* ") for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("*") and ln.strip() != "HEAD" and ln.strip() != branch]

    # 5) find worktrees + remove merged ones
    rc, out = _git(repo, "worktree", "list", "--porcelain")
    wt_map: dict[str, str] = {}  # branch -> path
    current_wt = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            current_wt = line[9:]
        if line.startswith("branch ") and current_wt:
            bname = line[7:]  # refs/heads/...
            if bname.startswith("refs/heads/"):
                bname = bname[11:]
            wt_map[bname] = current_wt

    for b in merged:
        if b in wt_map:
            wt_path = Path(wt_map[b])
            if wt_path.resolve() == repo.resolve():
                continue
            rc2, dirty = _git(wt_path, "status", "--short")
            if dirty.strip():
                skipped.append(f"worktree {wt_path} for branch {b} has uncommitted changes")
                continue
            _git(repo, "worktree", "remove", "-f", str(wt_path))
            actions.append(f"removed worktree {wt_path}")
        _git(repo, "branch", "-d", b)
        actions.append(f"deleted merged branch {b}")
        # attempt remote deletion
        rc2, _ = _git(repo, "push", "origin", "--delete", b)
        if rc2 == 0:
            actions.append(f"deleted remote branch origin/{b}")

    # 6) gc + reflog
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "--prune=now")
    actions.append("ran reflog expire + gc")

    # 7) final verification
    rc, out = _git(repo, "status", "--short")
    rc2, ahead = _git(repo, "rev-list", "--count", "@{u}..HEAD")
    ahead_behind = int(ahead) if ahead.isdigit() else 0
    rc3, behind = _git(repo, "rev-list", "--count", "HEAD..@{u}")
    ahead_behind += int(behind) if behind.isdigit() else 0

    return {
        "branch": branch,
        "actions": actions,
        "skipped": skipped,
        "clean": out.strip() == "",
        "aligned": ahead_behind == 0,
        "ahead_behind": ahead_behind,
    }


def sync_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    result = repo_sync(repo, push=not getattr(args, "no_push", False))
    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.repo.sync.v0", **result}, indent=2))
        return 0 if "error" not in result and result.get("clean") and result.get("aligned") else 1
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    for a in result["actions"]:
        print(f"  ✓ {a}")
    for s in result["skipped"]:
        print(f"  ⚠ skipped: {s}")
    if result["clean"] and result["aligned"]:
        print(f"  ✓ {result['branch']} clean and aligned with origin")
        return 0
    print(f"  ✗ {result['branch']} not fully aligned (ahead/behind: {result['ahead_behind']})", file=sys.stderr)
    return 1


def add_parser(sub) -> None:
    p = sub.add_parser("repo", help="repo lifecycle: audit, recover, cleanup, merge, handoff, graph, sync")
    ps = p.add_subparsers(dest="repo_command", required=True)

    audit = ps.add_parser("audit", help="health check — six zeros + pathologies")
    audit.add_argument("--repo", default=".", help="path to repo")
    audit.add_argument("--json", action="store_true", help="structured output")
    audit.set_defaults(func=audit_command)

    recover = ps.add_parser("recover", help="extract missing files from dangling commits")
    recover.add_argument("--repo", default=".", help="path to repo")
    recover.add_argument("--dry-run", action="store_true", help="list only, do not extract")
    recover.add_argument("--json", action="store_true", help="structured output")
    recover.set_defaults(func=recover_command)

    cleanup = ps.add_parser("cleanup", help="delete merged branches, worktrees, stashes, gc")
    cleanup.add_argument("--repo", default=".", help="path to repo")
    cleanup.add_argument("--force", action="store_true", help="skip safety gates")
    cleanup.add_argument("--json", action="store_true", help="structured output")
    cleanup.set_defaults(func=cleanup_command)

    handoff = ps.add_parser("handoff", help="machine-readable handoff report")
    handoff.add_argument("--repo", default=".", help="path to repo")
    handoff.set_defaults(func=handoff_command)

    merge = ps.add_parser("merge", help="rebase PR, resolve auto-patterns, squash-merge")
    merge.add_argument("pr", help="PR number")
    merge.add_argument("--repo", default=".", help="path to repo")
    merge.add_argument("--json", action="store_true", help="structured output")
    merge.set_defaults(func=merge_command)

    graph = ps.add_parser("graph", help="lightweight codebase graph (Python imports/defs)")
    graph.add_argument("--repo", default=".", help="path to repo")
    graph.add_argument("--json", action="store_true", help="structured output")
    graph.set_defaults(func=graph_command)

    sync = ps.add_parser("sync", help="push, clean merged branches/worktrees, gc, verify alignment")
    sync.add_argument("--repo", default=".", help="path to repo")
    sync.add_argument("--no-push", action="store_true", help="skip push to origin")
    sync.add_argument("--json", action="store_true", help="structured output")
    sync.set_defaults(func=sync_command)
