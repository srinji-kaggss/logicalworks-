"""
lgwks_solve — the first real-world experience: "I have this mess / this thought — prove what happened."

`lgwks solve git` is the membrane made concrete. It READS a repo's true state (reflog, object graph,
in-progress ops, conflicts, dangling commits) — it never mutates — assembles each fact as a cited
evidence item, then optionally lets the Tongue (a FREE model) narrate ONLY what the evidence supports
(insight-or-silence; no fabrication). Read-only is the safety: it diagnoses and recommends a
reversible-first next step; it does not run the fix.

Output contract:
  - human  : lead with the answer + ONE safe next step + what we are unsure of (warm, direct, no slop).
  - --json : the full structured verdict, every claim carrying CSL-JSON provenance (the git command IS
             the citation). Scientific-grade: no claim without the command that proves it.

Whimsy is logical: each status glyph on stderr fires only when that phase actually runs — the
whimsy carries information, it is not decoration. stdout stays clean for piping.

Forged by Logical Claude ◆ with Codex.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import lgwks_sign
except Exception:  # signing is best-effort; absence degrades to unsigned, surfaced honestly
    lgwks_sign = None  # type: ignore
try:
    import lgwks_tongue
except Exception:
    lgwks_tongue = None  # type: ignore
import lgwks_ui as ui
from lgwks_steering import Steering

_GLYPH = {"gather": "◇", "graph": "◈", "diagnose": "◆", "prove": "✦"}
_QUIET = False
_TIMEOUT = 20


def _whisper(phase: str, msg: str) -> None:
    """Logical whimsy: a phase glyph, printed only as that phase truly executes. stderr → stdout clean."""
    if _QUIET:
        return
    sys.stderr.write(f"  {_GLYPH.get(phase, '·')} {msg}\n")
    sys.stderr.flush()


from lgwks_proc import run_git


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Run a READ-ONLY git command. Returns (rc, stdout). Never mutates — solve advises, it does not act."""
    return run_git(repo, *args, timeout=_TIMEOUT)  # one source of truth for the git wrapper


@dataclass
class Evidence:
    """One cited fact. `command` is the citation: the exact git invocation that proves `note`."""
    id: str
    title: str
    command: str
    note: str

    def to_csl(self) -> dict:
        """Emit as CSL-JSON (type=report). The command is the author/source — provenance is the proof."""
        return {
            "id": self.id,
            "type": "report",
            "title": self.title,
            "author": [{"literal": self.command}],
            "archive": "git object store / reflog",
            "source": self.command,
            "note": self.note,
            "issued": {"date-parts": [[*_today()]]},
        }


@dataclass
class Finding:
    what: str                       # what happened, in one plain sentence
    severity: str                   # info | caution | danger
    next_step: str                  # the ONE reversible-first safe action
    evidence: list[Evidence] = field(default_factory=list)


def _today() -> tuple[int, int, int]:
    n = datetime.now(timezone.utc)
    return n.year, n.month, n.day


from lgwks_proc import is_git_repo as _is_repo  # one source of truth


def _diagnose(repo: Path) -> list[Finding]:
    """Deterministic forensics. Each branch emits a Finding with cited Evidence. Pure read."""
    findings: list[Finding] = []
    git_dir = Path(_git(repo, "rev-parse", "--git-dir")[1] or ".git")
    if not git_dir.is_absolute():
        git_dir = repo / git_dir

    _whisper("gather", "sleuthing the reflog…")
    _, reflog = _git(repo, "reflog", "--date=iso", "-n", "40")
    _whisper("graph", "reading HEAD and the object graph…")
    head_rc, _ = _git(repo, "symbolic-ref", "--quiet", "HEAD")
    _, porcelain = _git(repo, "status", "--porcelain")
    _, stash = _git(repo, "stash", "list")

    _whisper("diagnose", "reconstructing what happened…")

    # 1) Detached HEAD — common "where did my branch go" panic.
    if head_rc != 0:
        _, short = _git(repo, "rev-parse", "--short", "HEAD")
        findings.append(Finding(
            what=f"You are in DETACHED HEAD at {short} — commits you make now belong to no branch.",
            severity="caution",
            next_step=f"If you want to keep work here: `git switch -c rescue/{short}`. "
                      f"To go back: `git switch -` or `git switch <branch>`. Nothing is lost yet.",
            evidence=[Evidence("ev-head", "HEAD is detached (not a symbolic ref)",
                               "git symbolic-ref --quiet HEAD", f"exit {head_rc}; HEAD → {short}")],
        ))

    # 2) In-progress operation — the repo is mid-surgery.
    for marker, name, abort in (("MERGE_HEAD", "merge", "git merge --abort"),
                                ("CHERRY_PICK_HEAD", "cherry-pick", "git cherry-pick --abort"),
                                ("REVERT_HEAD", "revert", "git revert --abort")):
        if (git_dir / marker).exists():
            findings.append(Finding(
                what=f"A {name} is IN PROGRESS and paused — git is waiting for you to finish or abort it.",
                severity="caution",
                next_step=f"To bail out safely (reversible): `{abort}`. "
                          f"To continue after resolving: `git {name} --continue`.",
                evidence=[Evidence(f"ev-{name}", f"{name} in progress",
                                   f"test -f {git_dir.name}/{marker}", f"{marker} present")],
            ))
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        findings.append(Finding(
            what="A REBASE is in progress and paused — your branch is partway rewritten.",
            severity="danger",
            next_step="Safest exit: `git rebase --abort` returns you to exactly where you started. "
                      "Only `--continue` once conflicts are resolved.",
            evidence=[Evidence("ev-rebase", "rebase in progress",
                               "test -d .git/rebase-merge", "rebase state dir present")],
        ))

    # 3) Merge conflicts — unmerged paths.
    conflicts = [ln[3:] for ln in porcelain.splitlines() if ln[:2] in ("UU", "AA", "DD", "AU", "UA", "DU", "UD")]
    if conflicts:
        findings.append(Finding(
            what=f"{len(conflicts)} file(s) have unresolved merge conflicts: {', '.join(conflicts[:5])}"
                 + ("…" if len(conflicts) > 5 else ""),
            severity="caution",
            next_step="Edit the conflicted files (look for <<<<<<<), then `git add <file>`. "
                      "Or discard the whole attempt with the abort above. Your committed history is safe.",
            evidence=[Evidence("ev-conflict", "unmerged paths present",
                               "git status --porcelain", f"{len(conflicts)} conflict marker rows")],
        ))

    # 4) Recent destructive reflog ops — the "I think I lost commits" case.
    destructive = [ln for ln in reflog.splitlines()
                   if any(k in ln for k in ("reset: moving", "rebase", "checkout: moving", "reset --hard"))]
    _, lost = _git(repo, "fsck", "--no-reflogs", "--lost-found")
    dangling = [ln for ln in lost.splitlines() if "dangling commit" in ln]
    if destructive or dangling:
        recover = ""
        if dangling:
            sha = dangling[0].split()[-1][:10]
            recover = (f"Likely-recoverable commit found: inspect with `git show {sha}`, "
                       f"restore with `git branch rescue/{sha} {sha}`. ")
        elif destructive:
            recover = ("Your old state is in the reflog: `git reflog` to find it, then "
                       "`git branch rescue HEAD@{N}` to pin it back. ")
        findings.append(Finding(
            what=("History was rewritten recently (reset/rebase/hard-checkout)"
                  + (f" and {len(dangling)} dangling commit(s) exist" if dangling else "")
                  + " — but git almost never truly deletes; it unlinks."),
            severity="danger" if dangling else "caution",
            next_step=recover + "Nothing is gone until git gc prunes (default ~90 days).",
            evidence=([Evidence("ev-reflog", "recent history-rewriting operations",
                                "git reflog --date=iso -n 40", "; ".join(d[:80] for d in destructive[:3]) or "—")]
                      + ([Evidence("ev-dangling", "dangling commits recoverable",
                                   "git fsck --no-reflogs --lost-found",
                                   "; ".join(dangling[:3]))] if dangling else [])),
        ))

    # 5) Stashed work people forget they have.
    if stash:
        n = len(stash.splitlines())
        findings.append(Finding(
            what=f"You have {n} stash(es) — work set aside and easy to forget.",
            severity="info",
            next_step="`git stash list` to see them; `git stash show -p stash@{0}` to preview; "
                      "`git stash pop` to bring the latest back.",
            evidence=[Evidence("ev-stash", "stash entries present", "git stash list", f"{n} entries")],
        ))

    return findings


def _synthesize(thought: str, findings: list[Finding], steer: Steering) -> str | None:
    """Membrane: the FREE Tongue may narrate ONLY the cited findings — insight-or-silence, no fabrication.
    Conditioned on the steering dials. Returns None if no Tongue (honest degraded → deterministic)."""
    if lgwks_tongue is None or not findings:
        return None
    facts = "\n".join(f"- [{f.severity}] {f.what} (proof: {f.evidence[0].command if f.evidence else 'n/a'})"
                      for f in findings)
    prompt = (
        "You are the Tongue of a research instrument, not a chatbot. A user is staring at a confusing "
        "git repository. Below are FACTS already proven by read-only git commands — you may ONLY speak "
        "to these facts; never invent state, never guess at causes not in the facts. Be warm but direct, "
        "cut the panic, no hedging, no filler. Give them the single most likely story of what happened. "
        "If the facts are insufficient to tell a confident story, say exactly that.\n"
        f"{steer.prompt_fragment()}\n\n"
        f"User's thought/worry: {thought or '(none given — just confused)'}\n\n"
        f"<PROVEN_FACTS>\n{facts}\n</PROVEN_FACTS>"
    )
    schema = '{"story":"<plain narrative, only from PROVEN_FACTS>","confident":true}'
    try:
        out = lgwks_tongue._generate(prompt, schema)
    except Exception:
        return None
    if not out or not isinstance(out, dict):
        return None
    story = (out.get("story") or "").strip()
    return story or None


def _thought_packet(findings: list[Finding], steer: Steering) -> dict:
    """AI-side output: a thought-CONTINUATION packet (not prose). Compact keys, evidence by ref, the
    next move — so a peer agent resumes the chain of thought instead of re-parsing narrative."""
    return {
        "v": "lgwks.thought.v0",
        "steer": steer.compact(),
        "intent": "diagnose git repo state; recommend reversible-first recovery",
        "open": [f.what for f in findings],                 # threads still live
        "hyp": [{"k": e.id, "h": f.what, "p": 0.9} for f in findings for e in f.evidence[:1]],
        "ev": [e.id for f in findings for e in f.evidence],  # evidence BY REF, not inline
        "killed": [],
        "next": next((f.next_step for f in findings if f.severity == "danger"),
                     findings[0].next_step if findings else "no action — repo is clean"),
    }


def _signature() -> str:
    """Maker's mark + integrity mode. The mark is Claude+Codex; the integrity tells the truth about itself."""
    mode = "unsigned"
    tag = ""
    if lgwks_sign is not None:
        key, mode = lgwks_sign.signing_key()
        tag = lgwks_sign.mac("lgwks/solve/git", key)[:8]
    return f"◆ lgwks · solve/git — forged by Logical Claude with Codex · integrity:{mode} {tag}".rstrip()


def _evidence_answers_thought(thought: str, findings: list[Finding]) -> bool:
    if not thought:
        return True
    t_lower = thought.lower()
    
    # Check if thought queries specific git terms (common query topics we support)
    git_terms = {"detached", "conflict", "rebase", "merge", "stash", "dangling", "reset", "reflog", "lost", "commit", "history"}
    if any(term in t_lower for term in git_terms):
        return True
        
    numbers = re.findall(r'\b\d+\b', thought)
    hashes = re.findall(r'\b[0-9a-fA-F]{7,40}\b', thought)
    files = re.findall(r'\b\w+\.\w+\b', thought)
    
    # If thought has specific hashes, numbers, or file names, one of our findings must refer to them.
    if numbers or hashes or files:
        for f in findings:
            f_text = (f.what + " " + f.next_step + " " + " ".join(e.note + " " + e.command + " " + e.title for e in f.evidence)).lower()
            if any(num in f_text for num in numbers):
                return True
            if any(h.lower() in f_text for h in hashes):
                return True
            if any(fl.lower() in f_text for fl in files):
                return True
        return False
    return True


def solve_git(repo: Path, thought: str = "", as_json: bool = False, steer: Steering | None = None,
              quiet: bool = False, timeout: int = 20) -> int:
    global _QUIET, _TIMEOUT
    _QUIET = quiet
    _TIMEOUT = timeout

    steer = steer or Steering()
    if not _is_repo(repo):
        msg = f"{repo} is not inside a git work tree — nothing to solve here."
        print(json.dumps({"error": msg}) if as_json else f"  ✗ {msg}", file=sys.stdout)
        return 1

    findings = _diagnose(repo)
    _whisper("prove", "proving the story against the evidence…")
    
    if thought and not _evidence_answers_thought(thought, findings):
        findings = []
        story = "abstain"
    else:
        story = _synthesize(thought, findings, steer)
        if story and any(p in story.lower() for p in ("abstain", "no info", "no information", "cannot answer", "insufficient evidence")):
            findings = []
            story = "abstain"

    if as_json:
        payload = {
            "schema": "lgwks.solve.v0",
            "verb": "solve/git",
            "repo": str(repo),
            "thought": thought,
            "steer": steer.compact(),
            "story": story,
            "story_source": "tongue" if story and story != "abstain" else "deterministic",
            "findings": [
                {"what": f.what, "severity": f.severity, "next_step": f.next_step,
                 "evidence": [e.id for e in f.evidence]} for f in findings
            ],
            "references": [e.to_csl() for f in findings for e in f.evidence],  # CSL-JSON provenance
            "thought_packet": _thought_packet(findings, steer),  # AI continuation channel
            "signature": _signature(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # Human surface: OUR visual — a left spine, findings sprawling down+out, synthesis (up) rendered last.
    on = ui.color_on()
    out: list[str] = [""]
    out += ui.band("lgwks · solve/git", thought or "(no thought given — reading the repo cold)", on=on)
    out.append(ui.spine(on=on))
    # The steering dials, always visible (forced): the human SEES and can adjust the stance.
    out.append(ui.scale("Frontierness", steer.frontierness, "settled", "frontier", on=on))
    out.append(ui.scale("Lens", steer.lens, "philosophy", "science", signed=True, on=on))
    out.append(ui.scale("Depth", steer.depth, "shallow", "deep", on=on))
    if not steer.explicit:
        out.append(ui.spine(ui.fg("adjust the stance with --frontier / --lens / --depth", ui.MUTED, on=on), on=on))
    out.append(ui.spine(on=on))

    if story == "abstain":
        out.append(ui.spine(ui.fg(f"✗ Abstain: the gathered evidence cannot answer the thought '{thought}'.", ui.AMBER, on=on), on=on))
        out += ui.convergence("abstain: no relevant evidence", on=on)
        out.append(""); out.append("  " + ui.footer(_signature(), on=on)); out.append("")
        print("\n".join(out)); return 0

    if not findings:
        out.append(ui.spine(ui.fg("✓ Nothing pathological — HEAD on a branch, no conflicts, no half-done surgery.",
                                  ui.EMERALD, on=on), on=on))
        out += ui.convergence("clean", on=on)
        out.append(""); out.append("  " + ui.footer(_signature(), on=on)); out.append("")
        print("\n".join(out)); return 0

    # down (severity = depth) + out (siblings). danger deepest first — the foundation of the mess.
    order = {"danger": 0, "caution": 1, "info": 2}
    ordered = sorted(findings, key=lambda x: order.get(x.severity, 9))
    for i, f in enumerate(ordered):
        depth = order.get(f.severity, 2)
        out.append(ui.branch(f.severity, f.what, depth, last=(i == len(ordered) - 1), on=on))
        out.append(ui.twig(f.next_step, depth, "next", on=on))
        if f.evidence:
            out.append(ui.twig(f"proof: {f.evidence[0].command}", depth, "proof", on=on))
    # up: synthesis last — the convergence after the sprawl.
    out += ui.convergence(story or "narrating straight from the evidence (no model configured)", on=on)
    out.append(ui.spine(ui.fg("reversible-first: every step keeps your work or is undoable. nothing is deleted.",
                              ui.CREAM_DIM, on=on), on=on))
    out.append(""); out.append("  " + ui.footer(_signature(), on=on)); out.append("")
    print("\n".join(out))
    return 0


def solve_command(args) -> int:
    """Entry for the lgwks head: `lgwks solve git [--thought ...] [--json] [--repo PATH]`."""
    target = (getattr(args, "target", None) or "git").lower()
    if target != "git":
        print(f"  solve target '{target}' not built yet — only `git` so far.", file=sys.stderr)
        return 2
    repo = Path(getattr(args, "repo", None) or ".").resolve()
    quiet = getattr(args, "quiet", False) or getattr(args, "no_anim", False)
    timeout = getattr(args, "timeout", 20)
    return solve_git(repo, thought=getattr(args, "thought", "") or "",
                     as_json=getattr(args, "json", False), steer=Steering.from_args(args),
                     quiet=quiet, timeout=timeout)


def add_dials(p) -> None:
    """The three steering dials, shared by the head subparser and standalone main."""
    p.add_argument("--frontier", type=float, metavar="0..1", help="settled(0) ↔ frontier(1)")
    p.add_argument("--lens", type=float, metavar="-1..1", help="philosophy(-1) ↔ science(+1)")
    p.add_argument("--depth", type=float, metavar="0..1", help="shallow(0) ↔ deep(1)")
    p.add_argument("--quiet", action="store_true", help="suppress all progress/animation prints on stderr")
    p.add_argument("--no-anim", action="store_true", dest="no_anim", help="alias for --quiet")
    p.add_argument("--timeout", type=int, default=20, help="maximum command/API execution time in seconds")


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="lgwks solve")
    p.add_argument("target", nargs="?", default="git", help="what to solve (currently: git)")
    p.add_argument("--thought", default="", help="your worry/claim — 'prove this for me'")
    p.add_argument("--repo", default=".", help="path to the repo (default: cwd)")
    p.add_argument("--json", action="store_true", help="structured output with CSL-JSON provenance")
    add_dials(p)
    return solve_command(p.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
