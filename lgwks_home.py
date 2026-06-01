"""
lgwks_home — the launcher. Type `lgwks` (bare) and the whole thing pops up.

Not a help dump: a LIVING home, our own identity (spine · slate/cream/emerald · down-then-out · never a
chat stream, never orange — SPEC-lgwks-experience §3). Goal: canvas-widget parity on the terminal.

It renders the system as a RELATIONAL GRAPH WITH DEPTH (think in 3D, not lists):
  • the two actors — the Machine (intent, not AI) ⟷ the curious AI (teacher) — as connected nodes.
  • the three tiers as z-layers; brightness encodes depth (front bright → deep dim).
  • live capability state (the resolver truth), steering dials, recent runs, what it's curious about.

Whimsy licensed (Director): a reveal animation, the Machine's evolution stage (champion/challenger as a
pokemon-style evolve), coder lore — all in-palette, TTY-aware. The machine surface (pipes/--json) stays
clean: animation + colour auto-off when not a TTY or NO_COLOR.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import lgwks_ui as ui
from lgwks_ui import (CREAM, CREAM_DIM, EMERALD, EMERALD_DIM, MUTED, SLATE, SLATE_DIM, AMBER, fg)

ROOT = Path(__file__).resolve().parent

# Curiosity lines rotate by run-count (deterministic — no RNG in a pure path). Coder lore + research grain.
_CURIOSITY = [
    "what does this human actually want — before I spend a token finding out?",
    "every refinement you make is a lesson the Machine keeps. teach me.",
    "a hypothesis with no contradictor isn't proven — it's just unchallenged.",
    "// it grounds, therefore it claims. no source, no sentence.",
    "the skeptic is in the room. cite everything.",
]
_LORE = [
    "rm -rf doubt",
    "// works on my evidence",
    "ground truth > vibes",
    "no blackbox we can't revert",
]


def _anim_on(stream, no_anim: bool) -> bool:
    return ui.color_on(stream) and not no_anim


def _sleep(ms: int, anim: bool) -> None:
    if anim:
        time.sleep(ms / 1000.0)


def _emit(line: str, anim: bool, ms: int = 18) -> None:
    print(line)
    _sleep(ms, anim)


def _type(prefix: str, text: str, code: int, *, on: bool, anim: bool) -> None:
    """Typewriter reveal for one accent line (the curiosity prompt). Plain print when not animating."""
    sys.stdout.write(prefix)
    if not anim:
        sys.stdout.write(fg(text, code, on=on) + "\n")
        return
    for ch in text:
        sys.stdout.write(fg(ch, code, on=on))
        sys.stdout.flush()
        time.sleep(0.009)
    sys.stdout.write("\n")


def _banner(on: bool, anim: bool) -> None:
    """The mark draws in: phase glyphs sweep, then the wordmark settles."""
    if anim:
        for frame in ("◇", "◇◈", "◇◈◆", "◇◈◆✦"):
            sys.stdout.write("\r  " + fg(frame, EMERALD, on=on, bold=True) + "      ")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r")
    print("  " + fg("◇◈◆✦", EMERALD, on=on, bold=True)
          + fg("  Logical Works", CREAM, on=on, bold=True)
          + fg("  · research co-processor", CREAM_DIM, on=on))
    _sleep(40, anim)


def _z(text: str, depth: int, on: bool) -> str:
    """z-depth: front layer bright cream, deeper layers dim → the 3D feel without a 3D engine."""
    code = (CREAM, CREAM_DIM, MUTED, SLATE_DIM)[min(depth, 3)]
    return fg(text, code, on=on)


def _actors(on: bool, anim: bool) -> None:
    sp = lambda t="": ui.spine(t, on=on)
    _emit(sp(), anim)
    _emit(sp(fg("the two actors", EMERALD_DIM, on=on)
             + fg("   — a machine, and the ai that teaches it", CREAM_DIM, on=on)), anim)
    _emit(sp(), anim)
    machine = fg("◆ the machine", CREAM, on=on, bold=True)
    link = fg(" ⟷ ", EMERALD, on=on, bold=True)
    aimind = fg("✦ the curious ai", CREAM, on=on, bold=True)
    _emit(sp(machine + fg("  intent · desire · goal", CREAM_DIM, on=on) + link + aimind), anim)
    _emit(sp("  " + _z("not ai · discriminative · learning", 2, on)
             + "     " + _z("free · harnessed · insight-or-silence", 2, on)), anim)
    _emit(sp(fg("       │ ", SLATE, on=on) + _z("refines your intent", 1, on)
             + fg("            │ ", SLATE, on=on) + _z("distills into the machine", 1, on)), anim)
    _emit(sp(fg("       ▾", EMERALD, on=on) + "                    " + fg("▾", EMERALD, on=on)), anim)


_STAGES = ["dormant", "stage I", "stage II", "inflection"]


def _machine_stage(on: bool) -> str:
    """The Machine evolves as the cognition-log corpus grows (champion/challenger as a pokemon evolve).
    Honest: dormant until build #2 gives it a corpus to learn from."""
    stage = 0  # //why dormant: no cognition-log yet (build #2). lights up when the corpus exists.
    pips = "".join("◆" if i <= stage else "◇" for i in range(4))
    bar = fg(pips, EMERALD if stage else SLATE_DIM, on=on)
    note = fg(f"{_STAGES[stage]} — awaiting corpus (build #2 feeds it)", CREAM_DIM, on=on)
    return ui.spine("  " + fg("evolve ", MUTED, on=on) + bar + "  " + note, on=on)


def _tiers(on: bool, anim: bool) -> None:
    rows = [
        ("tier G", "generative", "the tongue", "ready", "openrouter → ollama", EMERALD, 0),
        ("tier E", "evaluator", "the machine", "coming", "build #3 · distilled", AMBER, 1),
        ("tier A", "sandbox", "the offense", "sealed", "scoped · later", SLATE_DIM, 2),
    ]
    for name, role, who, state, note, scode, depth in rows:
        dot = fg("▾", scode, on=on)
        head = (fg(f"{name:<7}", EMERALD_DIM, on=on) + _z(f"{role:<11}", depth, on)
                + _z(f"{who:<13}", depth, on))
        tag = fg(f"[{state}", scode, on=on) + fg(f" · {note}]", CREAM_DIM, on=on)
        _emit(ui.spine(f"{dot} {head}{tag}", on=on), anim)


def _capabilities(on: bool, anim: bool) -> None:
    try:
        import lgwks_capabilities as cap
        d = {r["capability"]: r for r in cap.doctor()}
    except Exception:
        d = {}
    def chosen(c: str) -> str:
        r = d.get(c)
        if not r or not r.get("chosen"):
            return fg("missing", AMBER, on=on)
        return fg(r["chosen"], EMERALD, on=on)
    # search is reported by the search module itself (the real floor), not the resolver's presence guess.
    try:
        import lgwks_search
        search_now = fg(lgwks_search.active_provider() + " (floor)", EMERALD, on=on)
    except Exception:
        search_now = chosen("search")
    _emit(ui.spine(fg("▸ eyes  ", EMERALD_DIM, on=on)
                   + _z("search ", 1, on) + search_now
                   + _z("   read ", 1, on) + chosen("extract")
                   + _z("   fetch ", 1, on) + chosen("fetch")
                   + _z("   browser ", 1, on) + chosen("browser"), on=on), anim)


def _recent_runs(on: bool, anim: bool) -> None:
    runs = sorted((ROOT / "runs").glob("*/"), key=lambda p: p.name, reverse=True) if (ROOT / "runs").exists() else []
    if not runs:
        _emit(ui.spine(fg("▸ runs  ", EMERALD_DIM, on=on) + _z("none yet — type an intent to begin", 2, on), on=on), anim)
        return
    _emit(ui.spine(fg("▸ runs  ", EMERALD_DIM, on=on) + _z(f"{len(runs)} on disk", 1, on)
                   + fg("  latest: ", CREAM_DIM, on=on) + fg(runs[0].name[:38], CREAM, on=on), on=on), anim)


def _dials(on: bool, anim: bool) -> None:
    try:
        import lgwks_steering as st
        s = st.Steering()
    except Exception:
        return
    _emit(ui.spine(fg("steering", EMERALD_DIM, on=on) + fg("  — you set how hard it pushes", CREAM_DIM, on=on), on=on), anim)
    _emit(ui.scale("frontierness", s.frontierness, "settled", "frontier", on=on), anim)
    _emit(ui.scale("lens", s.lens, "philosophy", "science", signed=True, on=on), anim)
    _emit(ui.scale("depth", s.depth, "shallow", "deep", on=on), anim)


def _commands(on: bool, anim: bool) -> None:
    cmds = [
        ("lgwks solve git", "prove what happened in a repo"),
        ("lgwks-akinator --demo", "watch the full loop, offline, no tokens"),
        ('lgwks-akinator "<intent>" --purpose "<why>" --auto --crawl ground', "a grounded run"),
    ]
    _emit(ui.spine(fg("quick", EMERALD_DIM, on=on) + fg("  — what you can do today", CREAM_DIM, on=on), on=on), anim)
    for c, why in cmds:
        _emit(ui.spine("  " + fg(c, EMERALD, on=on) + fg(f"   {why}", CREAM_DIM, on=on), on=on), anim)


def render_home(no_anim: bool = False) -> int:
    on = ui.color_on()
    anim = _anim_on(sys.stdout, no_anim)
    print()
    _banner(on, anim)
    runs_dir = ROOT / "runs"
    run_count = len(list(runs_dir.glob("*/"))) if runs_dir.exists() else 0

    _actors(on, anim)
    print(_machine_stage(on))
    _sleep(20, anim)
    print(ui.spine(on=on))
    _tiers(on, anim)
    print(ui.spine(on=on))
    _capabilities(on, anim)
    _recent_runs(on, anim)
    print(ui.spine(on=on))
    _dials(on, anim)
    print(ui.spine(on=on))
    _commands(on, anim)
    print(ui.spine(on=on))

    # the curiosity line — the AI's character, typed in. rotates deterministically by run-count.
    curious = _CURIOSITY[run_count % len(_CURIOSITY)]
    _type("  " + fg("┗━▴ ", EMERALD, on=on) + fg("curious: ", EMERALD, on=on, bold=True),
          curious, CREAM, on=on, anim=anim)

    lore = _LORE[run_count % len(_LORE)]
    print("  " + fg("◆ Logical Works", SLATE_DIM, on=on)
          + fg("  forged by Logical Claude with Codex", SLATE_DIM, on=on)
          + fg(f"   {lore}", SLATE_DIM, on=on))
    print()
    return _entryway(on)


# ── the entryway ─────────────────────────────────────────────────────────────────────────────────
# After the dashboard, drop into the first question set (like `claude` on launch) — an interactive prompt
# that opens the rest of the options. TTY-only: piped/non-interactive callers get the dashboard and exit
# clean (the machine surface is never blocked on input).

def _menu(on: bool) -> None:
    print(ui.spine(fg("where to?", EMERALD_DIM, on=on)
                   + fg("   — type an intent, or pick", CREAM_DIM, on=on), on=on))
    rows = [
        ("›", "your intent", "research it — I'll ask the question behind it, then ground it"),
        ("1", "solve git", "prove what happened in a repo (read-only, no tokens)"),
        ("2", "demo", "watch the full loop, offline, no tokens"),
        ("3", "doctor", "what's wired on this machine"),
        ("q", "quit", ""),
    ]
    for key, name, why in rows:
        line = ("  " + fg(f"{key} ", EMERALD, on=on, bold=True)
                + fg(f"{name:<13}", CREAM, on=on)
                + (fg(why, CREAM_DIM, on=on) if why else ""))
        print(ui.spine(line, on=on))
    print(ui.spine(on=on))


def _ask(prompt: str, on: bool) -> str:
    try:
        return input("  " + fg("❯ ", EMERALD, on=on, bold=True) + prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def _run(argv: list[str]) -> None:
    """Route into a sibling verb in its own process (clean stdout, isolated failure)."""
    try:
        subprocess.run([sys.executable, str(ROOT / argv[0]), *argv[1:]])
    except Exception as e:
        print(fg(f"  · couldn't launch {argv[0]}: {type(e).__name__}", AMBER, on=ui.color_on()))


def _intent_flow(intent: str, on: bool) -> None:
    """The first question set: intent → the question behind it (L1 gate) → confirm → grounded run.
    The human stands in for the not-yet-built Machine refinement (build #3) — same contract, by hand."""
    purpose = _ask(fg("the question behind it (why)?  ", CREAM_DIM, on=on), on)
    try:
        import lgwks_steering as st
        missing = st.require_context({"objective": intent, "purpose": purpose}, ["objective", "purpose"])
    except Exception:
        missing = [] if purpose else ["purpose"]
    if missing:   # honest L1 bounce — don't spend tokens on an underspecified question
        print(ui.spine(fg(f"need {', '.join(missing)} to spend tokens — bouncing back to you", AMBER, on=on), on=on))
        return
    print(ui.spine(fg("this runs a grounded research pass — it spends Tongue tokens.", CREAM_DIM, on=on), on=on))
    if _ask(fg("go? [y/N]  ", CREAM_DIM, on=on), on).lower() not in ("y", "yes"):
        print(ui.spine(fg("held.", CREAM_DIM, on=on), on=on))
        return
    _run(["lgwks-akinator", intent, "--purpose", purpose, "--auto", "--crawl", "ground"])


def _entryway(on: bool) -> int:
    if not sys.stdin.isatty():
        return 0   # piped / non-interactive — dashboard only, never block on input
    _menu(on)
    while True:
        choice = _ask("", on)
        low = choice.lower()
        if low in ("q", "quit", "exit", ""):
            print(ui.spine(fg("← stay curious.", EMERALD_DIM, on=on), on=on))
            return 0
        if low in ("1", "solve", "solve git"):
            _run(["lgwks", "solve", "git"])
        elif low in ("2", "demo"):
            _run(["lgwks-akinator", "--demo"])
        elif low in ("3", "doctor"):
            _print_doctor(on)
        else:
            _intent_flow(choice, on)   # anything else = an intent
        print(ui.spine(on=on))
        _menu(on)


def _print_doctor(on: bool) -> None:
    try:
        import lgwks_capabilities as cap
        for r in cap.doctor():
            mark = fg(r["chosen"], EMERALD, on=on) if r.get("chosen") else fg("MISSING", AMBER, on=on)
            tail = "" if r.get("chosen") else fg(f"  → {r.get('install','')}", CREAM_DIM, on=on)
            print(ui.spine(fg(f"{r['capability']:<9}", CREAM, on=on) + mark + tail, on=on))
    except Exception as e:
        print(ui.spine(fg(f"doctor unavailable: {type(e).__name__}", AMBER, on=on), on=on))


def home_command(args) -> int:
    return render_home(no_anim=getattr(args, "no_anim", False))
