"""
lgwks_multiply — the `x` verb: multiply intent instead of issuing it N times.

Instead of running 6 commands by hand, you declare ONE product expression and lgwks expands it into a
command chain, shows it in plain text, you confirm ONCE (same model as Claude's tool approvals today),
and it runs them. The AI declares the whole product up front in one call — that is the token save
(one declaration, not N round-trips).

  lgwks x 'git {status, log -1, diff --stat}'        → 3 commands (one brace = one axis)
  lgwks x 'git show {HEAD,HEAD~1} --stat'            → 2 commands
  lgwks x 'git {add,reset} {a.py,b.py}'              → 4 commands (cartesian product of two axes)

Safety (T0): commands run WITHOUT a shell (no pipes/redirect/glob injection surface — each expanded
item is argv, split by shlex). Every command is classified read|mutate|destructive|unknown and shown
with a risk mark; the human approval IS the gate. Non-interactive callers (agents) must pass --yes, and
destructive commands are refused without an explicit --force. Read-only chains can auto-run with --yes.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from itertools import product

# Heuristic risk classes. Conservative: anything that could lose work is 'destructive'; unknown verbs are
# never silently auto-run. //why heuristic not allowlist: the human gate is the real authority (claude model).
_DESTRUCTIVE = re.compile(r"\b(rm|rmdir|--force\b|-f\b|--hard|push\s+--force|push\s+-f|reset\s+--hard|"
                          r"clean\s+-[a-z]*f|branch\s+-D|drop|truncate|delete|checkout\s+--|stash\s+drop)\b")
_MUTATE = re.compile(r"\b(git\s+(add|commit|push|merge|rebase|stash|tag|mv|restore|checkout|switch)|"
                     r"mv|cp|mkdir|touch|chmod|chown|npm\s+(install|i)|pip\s+install|git\s+reset)\b")
_READ = re.compile(r"\b(git\s+(status|log|diff|show|blame|branch|remote|describe|rev-parse|ls-files|"
                   r"shortlog|reflog)|ls|cat|grep|head|tail|wc|find|pwd|echo|which)\b")

_RISK_ORDER = {"read": 0, "mutate": 1, "unknown": 2, "destructive": 3}


def _expand_braces(expr: str) -> list[str]:
    """Cartesian product of {a,b,c} axes. Multiple braces multiply; comma-separated, whitespace trimmed.
    Flat braces only (no nesting — documented). 'git {a,b} {x,y}' → 4 commands."""
    last = 0
    parts: list = []   # sequence of (kind, value): ('lit', str) | ('grp', [options])
    for m in re.finditer(r"\{([^{}]*)\}", expr):
        parts.append(("lit", expr[last:m.start()]))
        opts = [o.strip() for o in m.group(1).split(",")]
        parts.append(("grp", [o for o in opts if o != ""] or [""]))
        last = m.end()
    parts.append(("lit", expr[last:]))
    # build the product across only the group axes
    axes = [p[1] for p in parts if p[0] == "grp"]
    if not axes:
        return [re.sub(r"\s+", " ", expr).strip()]
    out = []
    for combo in product(*axes):
        s, gi = "", 0
        for kind, val in parts:
            if kind == "lit":
                s += val
            else:
                s += combo[gi]; gi += 1
        out.append(re.sub(r"\s+", " ", s).strip())
    # de-dup, preserve order
    seen, uniq = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def _classify(cmd: str) -> str:
    if _DESTRUCTIVE.search(cmd):
        return "destructive"
    if _MUTATE.search(cmd):
        return "mutate"
    if _READ.search(cmd):
        return "read"
    return "unknown"


def _run_one(cmd: str, timeout: int = 60) -> dict:
    """Run one command WITHOUT a shell (argv via shlex — no pipe/redirect/glob injection). Bounded output."""
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return {"cmd": cmd, "rc": 2, "out": f"unparseable: {e}", "ok": False}
    if not argv:
        return {"cmd": cmd, "rc": 2, "out": "empty", "ok": False}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return {"cmd": cmd, "rc": p.returncode, "out": out[:4000], "ok": p.returncode == 0}
    except FileNotFoundError:
        return {"cmd": cmd, "rc": 127, "out": f"command not found: {argv[0]}", "ok": False}
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "rc": 124, "out": "timed out", "ok": False}


def _ui():
    try:
        import lgwks_ui as ui
        return ui, ui.color_on()
    except Exception:
        return None, False


def _show_chain(cmds: list[str], risks: list[str], ui, on: bool) -> None:
    marks = {"read": ("·", getattr(ui, "MUTED", 0)), "mutate": ("▲", getattr(ui, "AMBER", 0)),
             "destructive": ("✗", getattr(ui, "RUST", 0)), "unknown": ("?", getattr(ui, "AMBER", 0))}
    header = f"multiply → {len(cmds)} command{'s' if len(cmds) != 1 else ''}"
    if ui:
        for ln in ui.band("x", header, on=on):
            print(ln)
    else:
        print(header)
    for cmd, risk in zip(cmds, risks):
        glyph, code = marks.get(risk, ("·", 0))
        if ui:
            print(ui.spine("  " + ui.fg(f"{glyph} ", code, on=on, bold=True)
                           + ui.fg(cmd, getattr(ui, "CREAM", 0), on=on)
                           + ui.fg(f"   [{risk}]", getattr(ui, "SLATE_DIM", 0), on=on), on=on))
        else:
            print(f"  {glyph} {cmd}   [{risk}]")


def multiply_command(args) -> int:
    cmds = _expand_braces(args.expr)
    risks = [_classify(c) for c in cmds]
    worst = max((_RISK_ORDER[r] for r in risks), default=0)
    ui, on = _ui()

    if getattr(args, "dry_run", False) or getattr(args, "json", False) and getattr(args, "plan_only", False):
        payload = {"expr": args.expr, "commands": [{"cmd": c, "risk": r} for c, r in zip(cmds, risks)],
                   "worst_risk": [k for k, v in _RISK_ORDER.items() if v == worst][0]}
        print(json.dumps(payload, indent=2))
        return 0

    _show_chain(cmds, risks, ui, on)

    # approval gate — the human is the authority (claude model). agents pass --yes; destructive needs --force.
    interactive = sys.stdin.isatty() and not getattr(args, "yes", False)
    has_destructive = any(r == "destructive" for r in risks)
    has_risky = any(r in ("mutate", "destructive", "unknown") for r in risks)

    if not interactive:
        if not getattr(args, "yes", False):
            print("refusing: non-interactive run needs --yes (and --force for destructive)", file=sys.stderr)
            return 2
        if any(r == "unknown" for r in risks) and not getattr(args, "allow_unknown", False):
            print("refusing: unknown commands in non-interactive chain need --allow-unknown", file=sys.stderr)
            return 2
        if has_destructive and not getattr(args, "force", False):
            print("refusing: destructive commands in chain need --force", file=sys.stderr)
            return 2
    else:
        prompt = "run all? "
        if has_destructive:
            prompt = "chain contains DESTRUCTIVE commands — type 'yes' to run all: "
        try:
            ans = input("  ❯ " + prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
        ok = (ans == "yes") if has_destructive else (ans in ("y", "yes"))
        if not ok:
            print("  held.", file=sys.stderr)
            return 1

    results = []
    for cmd in cmds:
        r = _run_one(cmd)
        results.append(r)
        if getattr(args, "json", False):
            continue
        head = f"$ {cmd}"
        print(("\n" + head) if not ui else "\n" + (ui.fg(head, ui.EMERALD, on=on) if on else head))
        if r["out"]:
            print(r["out"])
        if not r["ok"]:
            print(f"  (exit {r['rc']})", file=sys.stderr)
            if not getattr(args, "keep_going", False) and has_risky:
                print("  stopping chain after failure (use --keep-going to continue)", file=sys.stderr)
                break

    if getattr(args, "json", False):
        print(json.dumps({"expr": args.expr, "results": results,
                          "all_ok": all(x["ok"] for x in results)}, indent=2))
    failed = [x for x in results if not x["ok"]]
    return 1 if failed else 0
