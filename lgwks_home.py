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


# ── spec: home quick hints derived from live parser ─────────────────────────────
# L0 intent: the home launcher's `quick` block must show what `lgwks` can actually do — no curated
#            list that drifts from the parser (e.g. suggesting `lgwks-akinator`, a separate binary).
# L1 reality gap: hand-maintained hints will lie the first time a verb is added/renamed/removed.
#            the binary already advertises itself via `build_parser()`; the home launcher must read
#            the same source of truth and never invent a verb that doesn't exist in `lgwks --help`.
# L4 invariant:  for every verb shown in the `quick` block, `lgwks <verb> --help` succeeds; the block
#            is empty (not an error) when introspection fails; hint order = read-only → mutate →
#            orchestrators; cap at 6; no `lgwks-akinator` (separate binary) ever appears.
# L5 parallel:   `kubectl`/plugin discovery — the surface area is derived from registered plugins
#            at runtime, not curated in a separate help text. The launcher becomes a window onto
#            the real registry, not a marketing list that goes stale.
# ─────────────────────────────────────────────────────────────────────────────────

# verb → bucket; "orchestrator" means "coordinates sub-verbs" and is rendered last so the
# read/mutate verbs the user is most likely to type first stay on top. //why a hardcoded map
# rather than a runtime classifier: the cost of being wrong is cosmetic (order), and a
# runtime classifier would have to introspect each verb's flags — a much bigger surface to
# maintain. New verbs default to "mutate" so they appear, not silently disappear.
_READ_FIRST = ["manifest", "extract", "convert", "refine", "store", "login", "memory", "public", "embed"]
_MUTATE_NEXT = ["jarvis", "x", "geo"]
_ORCHESTRATORS_LAST = ["solve", "project"]
_MAX_HINTS = 6


def _bucket_order(verb: str) -> tuple[int, str]:
    if verb in _READ_FIRST:
        return (0, verb)
    if verb in _MUTATE_NEXT:
        return (1, verb)
    if verb in _ORCHESTRATORS_LAST:
        return (2, verb)
    return (1, verb)  # unknown verbs render in the mutate band — visible, not hidden


def _live_hints() -> list[tuple[str, str]]:
    # //why: the only source of truth is the live parser; if we can't read it, emit nothing
    # (no fake hints that drift again). `lgwks` is a script (no .py suffix), so load it via
    # SourceFileLoader and register the module in sys.modules BEFORE exec (Python 3.14
    # dataclass() needs sys.modules[__name__] for @dataclass-decorated classes).
    try:
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path as _P
        loader = SourceFileLoader("lgwks_cli", str(_P(__file__).resolve().parent / "lgwks"))
        spec = importlib.util.spec_from_loader("lgwks_cli", loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("lgwks_cli", mod)
        loader.exec_module(mod)
        parser = mod.build_parser()
    except Exception:
        return []
    sub_action = None
    for action in parser._actions:
        if action.dest == "command":
            sub_action = action
            break
    if sub_action is None or not getattr(sub_action, "choices", None):
        return []
    # //why: argparse keeps the per-verb help on the subparser action (`_choices_actions`),
    # not on the inner ArgumentParser objects (their `description` is None when only `help=`
    # was passed). Build a name→help map once, then iterate `sub_action.choices` for the
    # actual subparser instances (some callers may rely on those being real parsers).
    help_by_name: dict[str, str] = {ca.dest: (ca.help or "").strip() for ca in sub_action._choices_actions}
    ordered: list[tuple[str, str]] = []
    for name in sorted(sub_action.choices.keys(), key=_bucket_order):
        help_text = help_by_name.get(name, "")
        # //why: descriptions are written for the agent manifest ("machine-readable contract...") and
        # contain em-dashes / arrows that read fine in --help. Trim to the first sentence for the
        # quick block, capped at ~64 chars so the spine doesn't wrap on 80-col TTYs.
        if "." in help_text:
            help_text = help_text.split(".", 1)[0]
        if len(help_text) > 64:
            help_text = help_text[:61].rstrip() + "..."
        ordered.append((name, help_text))
    return ordered[:_MAX_HINTS]


def _commands(on: bool, anim: bool) -> None:
    hints = _live_hints()
    if not hints:
        return  # //why: never invent a hint that isn't in the live parser — silence is honest
    # //why: skip the section header too if we have nothing to put under it — an empty "quick — what
    # you can do today" block with zero lines below it is worse than no block at all (the user reads
    # the header as a promise the body can't keep).
    _emit(ui.spine(fg("quick", EMERALD_DIM, on=on) + fg("  — what you can do today", CREAM_DIM, on=on), on=on), anim)
    for name, why in hints:
        _emit(ui.spine("  " + fg(f"lgwks {name}", EMERALD, on=on)
                       + fg(f"   {why}", CREAM_DIM, on=on), on=on), anim)


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
    return _browser_entryway(on)


# ── command browser: hierarchical navigation over the full parser surface ──────────────────────
# Invariant: every registered subcommand must be reachable through the browser. No command may be
# hidden behind "type an intent" as the only path. The browser is the human discovery layer.
#
# Architecture:
#   _build_command_tree()  → introspects the live parser (same source-of-truth as _live_hints)
#   _domain_for()          → static verb→domain map; unknown verbs land in "Other" (never hidden)
#   _render_home_browser() → domain grid + quick actions + intent input
#   _render_domain()       → commands in a domain with 1-line help
#   _render_command()      → command detail: help, flags, subcommands, run/help/back options
#   _browser_entryway()    → stack-based navigation loop (home → domain → command → subcommand)

# ── repo context detection ────────────────────────────────────────────────────
# The browser must establish WHERE the user is before asking WHAT they want to do.
# This is the "navigate my repos" experience: detect the current repo, scan for
# nearby repos if not in one, and surface context-relevant commands first.

_MAX_NEARBY_SCAN_DEPTH = 3
_MAX_NEARBY_RESULTS = 10
_NEARBY_SCAN_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "target", "build", "dist"}


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").is_dir()


def _scan_nearby_repos(start: Path | None = None, max_depth: int = _MAX_NEARBY_SCAN_DEPTH, max_results: int = _MAX_NEARBY_RESULTS) -> list[Path]:
    """Scan from start (default: home) for .git directories. Skip common noise dirs.
    Returns sorted by path depth (shallower first), then name."""
    root = start or Path.home()
    found: list[Path] = []
    for depth in range(max_depth + 1):
        if len(found) >= max_results:
            break
        pattern = "/".join(["*"] * depth)
        if depth == 0:
            candidates = [root]
        else:
            candidates = root.glob(pattern)
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            if candidate.name.startswith(".") and candidate.name != ".lgwks":
                continue
            if candidate.name in _NEARBY_SCAN_SKIP:
                continue
            if _is_git_repo(candidate):
                found.append(candidate.resolve())
            if len(found) >= max_results:
                break
    # Deduplicate and sort by depth then name
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    unique.sort(key=lambda p: (len(p.parts), p.name.lower()))
    return unique


def _detect_repo_context() -> tuple[Path | None, list[Path]]:
    """Returns (current_repo_or_None, nearby_repos_list).
    If cwd is a git repo, returns (cwd, []). If not, scans for nearby repos."""
    cwd = Path.cwd().resolve()
    if _is_git_repo(cwd):
        return cwd, []
    nearby = _scan_nearby_repos()
    # Filter out cwd if it somehow snuck in
    nearby = [p for p in nearby if p != cwd]
    return None, nearby


def _repo_status_line(repo: Path) -> str:
    """Return a one-line human-readable status for the repo."""
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode == 0:
            lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
            if lines:
                return f"{len(lines)} uncommitted change{'s' if len(lines) != 1 else ''}"
            return "clean"
    except Exception:
        pass
    return ""


def _repo_for_command(verb: str, repo: Path | None) -> list[str]:
    """Return extra argv for commands that benefit from --repo context."""
    if repo is None:
        return []
    # Only inject --repo for commands that actually accept it
    repo_aware = {"gh", "repo", "review", "session", "graph", "solve", "debug", "intent", "entity-graph"}
    if verb in repo_aware:
        return ["--repo", str(repo)]
    return []


_DOMAINS: dict[str, list[str]] = {
    # Primary product — the subconscious loop and operator surface
    "Subconscious": ["map", "engine", "session", "solve", "debug", "intent", "doctor",
                     "spawn", "portal", "do", "agent-os"],
    # Research and knowledge work — the conscious-layer tools
    "Research":  ["jarvis", "fetch", "refine", "preview", "extract", "convert",
                  "x", "manifest", "login", "cohere", "comprehend", "geo", "public",
                  "akinator", "run", "context", "model-hub", "capture", "jepa",
                  "workflow"],
    "GitHub":    ["gh"],
    "DevOps":    ["repo", "review", "project", "batch", "refactor", "hooks"],
    "System":    ["repl", "initialize", "auth", "keyvault", "foundation",
                  "aup", "schema", "route", "codebase"],
    # L0 substrate — ingestion, vector store, contracts (foundational, not the product)
    "Substrate": ["store", "memory", "embed", "axiom", "pipeline", "waste",
                  "entity-graph", "graph", "substrate", "score", "rank", "inbound",
                  "admission", "capability", "crdt", "viz-project"],
}


def _quick_actions_for_repo(repo: Path | None) -> list[tuple[str, str, str, list[str]]]:
    """Return quick actions tailored to repo context."""
    actions: list[tuple[str, str, str, list[str]]] = [
        ("s", "solve git", "prove what happened (read-only)", ["lgwks", "solve", "git"]),
    ]
    if repo:
        actions.append(("g", "gh issues", "open issues on GitHub", ["lgwks", "gh", "issues", "--repo", str(repo)]))
        actions.append(("v", "viz", "open graph visualization", []))
        actions.append(("r", "repl", "interactive harness", []))
    else:
        actions.append(("r", "repl", "interactive harness", []))
    actions.append(("d", "doctor", "what's wired on this machine", []))
    return actions


def _build_command_tree() -> dict[str, dict[str, Any]]:
    """Introspect the live parser and return {verb: {"help": ..., "subcommands": {...}}}.
    Subcommands are only captured one level deep — that's the lgwks CLI structure."""
    try:
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path as _P
        loader = SourceFileLoader("lgwks_cli", str(_P(__file__).resolve().parent / "lgwks"))
        spec = importlib.util.spec_from_loader("lgwks_cli", loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("lgwks_cli", mod)
        loader.exec_module(mod)
        parser = mod.build_parser()
    except Exception:
        return {}

    # Find top-level subparsers
    sub_action = None
    for action in parser._actions:
        if action.dest == "command":
            sub_action = action
            break
    if sub_action is None or not getattr(sub_action, "choices", None):
        return {}

    help_by_name: dict[str, str] = {ca.dest: (ca.help or "").strip() for ca in sub_action._choices_actions}
    tree: dict[str, dict[str, Any]] = {}

    for name, subparser in sub_action.choices.items():
        help_text = help_by_name.get(name, "")
        # Skip aliases (e.g. crawl is an alias for fetch). Aliases have empty help text.
        if not help_text:
            continue
        node: dict[str, Any] = {"help": help_text}
        # Detect sub-subparsers (e.g. jarvis → crawl, gh → issue).
        # //why: argparse uses `choices` for both subparsers AND --choices flags. The only
        # reliable discriminator is `_choices_actions`, which exists exclusively on _SubParsersAction.
        sub_sub = None
        for a in subparser._actions:
            if getattr(a, "dest", None) and hasattr(a, "_choices_actions") and hasattr(a, "choices") and a.choices:
                sub_sub = a
                break
        if sub_sub:
            sub_help = {ca.dest: (ca.help or "").strip() for ca in getattr(sub_sub, "_choices_actions", [])}
            choices = sub_sub.choices
            if isinstance(choices, dict):
                choice_keys = choices.keys()
            else:
                choice_keys = choices
            node["subcommands"] = {
                sc_name: {"help": sub_help.get(sc_name, "")}
                for sc_name in choice_keys
            }
        tree[name] = node
    return tree


def _domain_for(verb: str) -> str:
    for domain, verbs in _DOMAINS.items():
        # exact match first
        if verb in verbs:
            return domain
        # prefix match for nested verbs (e.g. "agent-os bootstrap" → "agent-os")
        for v in verbs:
            if verb.startswith(v + " "):
                return domain
    return "Other"


def _ask(prompt: str, on: bool) -> str:
    try:
        return input("  " + fg("❯ ", EMERALD, on=on, bold=True) + prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def _run(argv: list[str]) -> None:
    """Route into a sibling verb in its own process (clean stdout, isolated failure)."""
    cmd = [sys.executable, str(ROOT / argv[0]), *argv[1:]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            err = (result.stderr or "<no stderr>").strip()
            print(fg(f"  · {argv[0]} exited {result.returncode}", AMBER, on=ui.color_on()))
            if err:
                for line in err.splitlines():
                    print(fg(f"    {line}", AMBER, on=ui.color_on()))
    except Exception as e:
        print(fg(f"  · couldn't launch {argv[0]}: {type(e).__name__}", AMBER, on=ui.color_on()))


def _pause(on: bool) -> None:
    """Hold so the user can read subprocess output before the menu re-renders over it."""
    try:
        input("  " + fg("— press Enter to continue —", CREAM_DIM, on=on))
    except (EOFError, KeyboardInterrupt):
        pass


def _intent_flow(intent: str, on: bool) -> None:
    """The first question set, now driven by the Machine (build #3): it classifies the intent, detects
    which slots are missing, and asks leading questions for each gap until specific enough — then a
    grounded run. The Machine ABSTAINS (bounces) rather than guess; the human answers fill the gaps."""
    try:
        import lgwks_machine as machine
    except Exception:
        machine = None
    purpose = ""
    if machine:
        r = machine.refine(intent, actor="human")
        cls = r["intent_class"]
        print(ui.spine(fg(f"machine read: {cls}", EMERALD_DIM, on=on)
                       + fg(f"  specificity {r['specificity']:.2f}/{r['threshold']:.2f}"
                            + (f"  · {', '.join(r['entities'][:3])}" if r["entities"] else ""), CREAM_DIM, on=on), on=on))
        answers = []
        for q in r["questions"]:   # one leading question per gap (the refinement chain)
            a = _ask(fg(q + "  ", CREAM_DIM, on=on), on)
            if a:
                answers.append(a)
        purpose = " · ".join(answers) if answers else _ask(fg("the question behind it (why)?  ", CREAM_DIM, on=on), on)
        if r["abstain"] and not answers and not purpose:
            print(ui.spine(fg("too thin to spend tokens — bounced back to you (the Machine won't guess)", AMBER, on=on), on=on))
            return
    else:
        purpose = _ask(fg("the question behind it (why)?  ", CREAM_DIM, on=on), on)
        if not purpose:
            print(ui.spine(fg("need the why to spend tokens — bouncing back to you", AMBER, on=on), on=on))
            return
    print(ui.spine(fg("this runs a grounded research pass — it spends Tongue tokens.", CREAM_DIM, on=on), on=on))
    if _ask(fg("go? [y/N]  ", CREAM_DIM, on=on), on).lower() not in ("y", "yes"):
        print(ui.spine(fg("held.", CREAM_DIM, on=on), on=on))
        return
    _run(["lgwks-akinator", intent, "--purpose", purpose, "--auto", "--crawl", "ground"])


def _print_doctor(on: bool) -> None:
    try:
        import lgwks_capabilities as cap
        for r in cap.doctor():
            mark = fg(r["chosen"], EMERALD, on=on) if r.get("chosen") else fg("MISSING", AMBER, on=on)
            tail = "" if r.get("chosen") else fg(f"  → {r.get('install','')}", CREAM_DIM, on=on)
            print(ui.spine(fg(f"{r['capability']:<9}", CREAM, on=on) + mark + tail, on=on))
    except Exception as e:
        print(ui.spine(fg(f"doctor unavailable: {type(e).__name__}", AMBER, on=on), on=on))


# ── browser renderers ─────────────────────────────────────────────────────────

def _render_home_browser(tree: dict[str, dict[str, Any]], on: bool, *, repo: Path | None = None) -> None:
    """Context-aware home: shows repo context first, then domain grid + quick actions."""
    if repo:
        status = _repo_status_line(repo)
        status_tag = fg(f"  ({status})", CREAM_DIM, on=on) if status else ""
        print(ui.spine(fg("▸ current project", EMERALD_DIM, on=on)
                       + fg(f"   {repo.name}", CREAM, on=on, bold=True)
                       + status_tag, on=on))
        print(ui.spine(fg("   What do you want to do with this repo?", CREAM_DIM, on=on), on=on))
    else:
        print(ui.spine(fg("where to?", EMERALD_DIM, on=on)
                       + fg("   — navigate by domain, or type an intent", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))

    # Group commands by domain
    by_domain: dict[str, list[str]] = {}
    for verb in sorted(tree.keys()):
        domain = _domain_for(verb)
        by_domain.setdefault(domain, []).append(verb)

    # Render domain grid
    domains = [d for d in list(_DOMAINS.keys()) + ["Other"] if d in by_domain]
    for i, domain in enumerate(domains, 1):
        verbs = by_domain[domain]
        line = ("  " + fg(f"{i} ", EMERALD, on=on, bold=True)
                + fg(f"{domain:<13}", CREAM, on=on)
                + fg(f"{len(verbs)} command{'s' if len(verbs) != 1 else ''} ", CREAM_DIM, on=on)
                + fg(", ".join(verbs[:4]), CREAM_DIM, on=on)
                + (fg("…", CREAM_DIM, on=on) if len(verbs) > 4 else ""))
        print(ui.spine(line, on=on))

    print(ui.spine(on=on))

    # Quick actions (context-aware)
    quick_actions = _quick_actions_for_repo(repo)
    for key, label, why, _argv in quick_actions:
        line = ("  " + fg(f"{key} ", EMERALD, on=on, bold=True)
                + fg(f"{label:<13}", CREAM, on=on)
                + (fg(why, CREAM_DIM, on=on) if why else ""))
        print(ui.spine(line, on=on))

    # Intent input
    print(ui.spine("  " + fg("› ", EMERALD, on=on, bold=True)
                   + fg("your intent", CREAM, on=on)
                   + fg("   research it — I'll ask the question behind it", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))
    nav = "q quit  ·  b back  ·  [number/letter] pick"
    if repo:
        nav += "  ·  p pick another project"
    print(ui.spine(fg(nav, CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))


def _render_no_repo_home(on: bool, nearby: list[Path]) -> None:
    """When not in a git repo and no context established: show nearby projects + options."""
    cwd = Path.cwd().resolve()
    print(ui.spine(fg("▸ not in a git repo", AMBER, on=on)
                   + fg(f"   {cwd}", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))

    if nearby:
        print(ui.spine(fg("nearby projects", EMERALD_DIM, on=on), on=on))
        for i, p in enumerate(nearby, 1):
            rel = p.name
            if p.parent != cwd.parent and p.parent != Path.home():
                rel = f"{p.parent.name}/{p.name}"
            line = ("  " + fg(f"{i} ", EMERALD, on=on, bold=True)
                    + fg(f"{rel:<20}", CREAM, on=on)
                    + fg(str(p), CREAM_DIM, on=on))
            print(ui.spine(line, on=on))
        print(ui.spine(on=on))
    else:
        print(ui.spine(fg("no git repos found nearby", CREAM_DIM, on=on), on=on))
        print(ui.spine(on=on))

    print(ui.spine("  " + fg("c ", EMERALD, on=on, bold=True)
                   + fg("create repo here", CREAM, on=on)
                   + fg("   git init + set origin", CREAM_DIM, on=on), on=on))
    print(ui.spine("  " + fg("i ", EMERALD, on=on, bold=True)
                   + fg("initialize", CREAM, on=on)
                   + fg("   first-time lgwks setup", CREAM_DIM, on=on), on=on))
    print(ui.spine("  " + fg("n ", EMERALD, on=on, bold=True)
                   + fg("continue", CREAM, on=on)
                   + fg("   browse all commands without a project", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))
    print(ui.spine(fg("q quit  ·  [number/letter] pick", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))


def _render_project_picker(nearby: list[Path], on: bool) -> None:
    """Show the project picker when user presses 'p' from a repo context."""
    print(ui.spine(fg("switch project", EMERALD_DIM, on=on), on=on))
    print(ui.spine(on=on))
    for i, p in enumerate(nearby, 1):
        rel = p.name
        if p.parent != Path.home():
            rel = f"{p.parent.name}/{p.name}"
        line = ("  " + fg(f"{i} ", EMERALD, on=on, bold=True)
                + fg(f"{rel:<20}", CREAM, on=on)
                + fg(str(p), CREAM_DIM, on=on))
        print(ui.spine(line, on=on))
    print(ui.spine(on=on))
    print(ui.spine(fg("b back  ·  q quit  ·  [number] pick", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))


def _render_domain_browser(domain: str, verbs: list[str], tree: dict[str, dict[str, Any]], on: bool) -> None:
    """List commands in a domain."""
    print(ui.spine(fg(f"▸ {domain}", EMERALD_DIM, on=on)
                   + fg(f"   — {len(verbs)} command{'s' if len(verbs) != 1 else ''}", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))
    for i, verb in enumerate(verbs, 1):
        node = tree.get(verb, {})
        help_text = node.get("help", "")
        if "." in help_text:
            help_text = help_text.split(".", 1)[0]
        if len(help_text) > 56:
            help_text = help_text[:53].rstrip() + "..."
        has_sub = "subcommands" in node
        badge = fg("▸", EMERALD_DIM, on=on) if has_sub else fg("·", MUTED, on=on)
        line = ("  " + fg(f"{i} ", EMERALD, on=on, bold=True)
                + fg(f"{verb:<15}", CREAM, on=on)
                + badge + " "
                + fg(help_text, CREAM_DIM, on=on))
        print(ui.spine(line, on=on))
    print(ui.spine(on=on))
    print(ui.spine(fg("q quit  ·  b back  ·  [number] pick", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))


def _render_command_detail(verb: str, node: dict[str, Any], on: bool) -> None:
    """Show command details: help text, subcommands if any, and action options."""
    help_text = node.get("help", "")
    print(ui.spine(fg(f"▸ {verb}", EMERALD_DIM, on=on)
                   + (fg(f"   {help_text}", CREAM_DIM, on=on) if help_text else ""), on=on))
    print(ui.spine(on=on))

    subcommands = node.get("subcommands", {})
    if subcommands:
        print(ui.spine(fg("subcommands", EMERALD_DIM, on=on), on=on))
        for i, (sc_name, sc_node) in enumerate(sorted(subcommands.items()), 1):
            sc_help = sc_node.get("help", "")
            if "." in sc_help:
                sc_help = sc_help.split(".", 1)[0]
            if len(sc_help) > 50:
                sc_help = sc_help[:47].rstrip() + "..."
            line = ("  " + fg(f"{i} ", EMERALD, on=on, bold=True)
                    + fg(f"{sc_name:<15}", CREAM, on=on)
                    + fg(sc_help, CREAM_DIM, on=on))
            print(ui.spine(line, on=on))
        print(ui.spine(on=on))
        print(ui.spine(fg("r run  ·  h help  ·  b back  ·  q quit  ·  [number] pick subcommand", CREAM_DIM, on=on), on=on))
    else:
        print(ui.spine(fg("r run", EMERALD, on=on) + fg("   run with no args (Phase-3: prompt for args)", CREAM_DIM, on=on), on=on))
        print(ui.spine(fg("h help", EMERALD, on=on) + fg("   show full help", CREAM_DIM, on=on), on=on))
        print(ui.spine(on=on))
        print(ui.spine(fg("b back  ·  q quit", CREAM_DIM, on=on), on=on))
    print(ui.spine(on=on))


def _run_with_help(argv: list[str]) -> None:
    """Run a command with --help to show usage."""
    _run(argv + ["--help"])


# ── browser navigation loop ───────────────────────────────────────────────────

def _browser_entryway(on: bool) -> int:
    if not sys.stdin.isatty():
        return 0   # piped / non-interactive — dashboard only, never block on input

    tree = _build_command_tree()
    if not tree:
        print(ui.spine(fg("browser unavailable — parser introspection failed", AMBER, on=on), on=on))
        print(ui.spine(fg("fallback: type an intent directly, or q to quit", CREAM_DIM, on=on), on=on))
        while True:
            choice = _ask("", on)
            low = choice.lower()
            if low in ("q", "quit", "exit", ""):
                print(ui.spine(fg("← stay curious.", EMERALD_DIM, on=on), on=on))
                return 0
            _intent_flow(choice, on)
            print(ui.spine(on=on))

    # Detect repo context on launch
    current_repo, nearby_repos = _detect_repo_context()
    selected_repo: Path | None = current_repo
    showing_no_repo = current_repo is None

    # Group by domain
    by_domain: dict[str, list[str]] = {}
    for verb in sorted(tree.keys()):
        domain = _domain_for(verb)
        by_domain.setdefault(domain, []).append(verb)
    domains = [d for d in list(_DOMAINS.keys()) + ["Other"] if d in by_domain]

    # Navigation stack supports:
    #   ("home",) | ("domain", name) | ("command", verb) | ("picker",) | ("no_repo",)
    stack: list[tuple[str, ...]] = []

    def _render_current() -> None:
        frame = stack[-1]
        if frame[0] == "home":
            _render_home_browser(tree, on, repo=selected_repo)
        elif frame[0] == "domain":
            domain = frame[1]
            verbs = by_domain.get(domain, [])
            _render_domain_browser(domain, verbs, tree, on)
        elif frame[0] == "command":
            verb = frame[1]
            node = tree.get(verb, {})
            _render_command_detail(verb, node, on)
        elif frame[0] == "picker":
            _render_project_picker(nearby_repos, on)
        elif frame[0] == "no_repo":
            _render_no_repo_home(on, nearby_repos)

    def _resolve_argv(base_argv: list[str]) -> list[str]:
        """Auto-inject --repo for commands that accept it when a repo is selected."""
        if not selected_repo or len(base_argv) < 2:
            return base_argv
        verb = base_argv[1]
        extra = _repo_for_command(verb, selected_repo)
        if extra:
            return base_argv + extra
        return base_argv

    # Initial screen: context-aware home, or no-repo screen if not in a repo
    if showing_no_repo:
        stack.append(("no_repo",))
    else:
        stack.append(("home",))

    _render_current()

    while True:
        choice = _ask("", on)
        low = choice.lower()

        if low in ("q", "quit", "exit"):
            print(ui.spine(fg("← stay curious.", EMERALD_DIM, on=on), on=on))
            return 0

        if low == "b" or low == "back":
            if len(stack) > 1:
                stack.pop()
                print(ui.spine(on=on))
                _render_current()
            else:
                print(ui.spine(fg("already at home", CREAM_DIM, on=on), on=on))
            continue

        frame = stack[-1]
        frame_type = frame[0]

        # ── no-repo screen ──────────────────────────────────────────────────────
        if frame_type == "no_repo":
            if low == "c":
                # Create repo here
                cwd = Path.cwd().resolve()
                try:
                    subprocess.run(["git", "init"], capture_output=True, text=True, timeout=10)
                    selected_repo = cwd
                    nearby_repos = []
                    showing_no_repo = False
                    print(ui.spine(fg(f"✓ git init in {cwd.name}", EMERALD, on=on), on=on))
                    stack[-1] = ("home",)
                    _render_current()
                except Exception as e:
                    print(ui.spine(fg(f"git init failed: {type(e).__name__}", AMBER, on=on), on=on))
                continue
            elif low == "i":
                _run(["lgwks", "initialize"])
                _pause(on)
                print(ui.spine(on=on))
                _render_current()
                continue
            elif low == "n":
                # Continue without a repo — show the full browser
                stack[-1] = ("home",)
                print(ui.spine(on=on))
                _render_current()
                continue
            elif low.isdigit():
                idx = int(low) - 1
                if 0 <= idx < len(nearby_repos):
                    selected_repo = nearby_repos[idx]
                    showing_no_repo = False
                    stack[-1] = ("home",)
                    print(ui.spine(fg(f"▸ switched to {selected_repo.name}", EMERALD, on=on), on=on))
                    _render_current()
                    continue
            elif low:
                # Intent typed from no-repo screen
                _intent_flow(low, on)
                print(ui.spine(on=on))
                _render_current()
                continue
            continue

        # ── home screen ─────────────────────────────────────────────────────────
        if frame_type == "home":
            if low == "p":
                if nearby_repos:
                    stack.append(("picker",))
                    print(ui.spine(on=on))
                    _render_current()
                else:
                    print(ui.spine(fg("no other projects found", CREAM_DIM, on=on), on=on))
                continue
            if low.isdigit():
                idx = int(low) - 1
                if 0 <= idx < len(domains):
                    stack.append(("domain", domains[idx]))
                    print(ui.spine(on=on))
                    _render_current()
                    continue
            # Quick action key?
            quick_actions = _quick_actions_for_repo(selected_repo)
            quick_map = {qa[0]: qa for qa in quick_actions}
            if low in quick_map:
                _, label, _why, argv = quick_map[low]
                if label == "repl":
                    try:
                        import lgwks_repl
                        # Build a welcome hint that bridges browser → REPL mental model:
                        # show the same quick actions the user just saw, translated to REPL syntax.
                        hint_cmds: list[str] = []
                        for k, lbl, _why, _argv in quick_actions:
                            if lbl in ("repl",):
                                continue
                            hint_cmds.append(f"{lbl}")
                        hint = f"commands: {', '.join(hint_cmds[:4])} … type .help for all" if hint_cmds else "type .help for commands"
                        lgwks_repl.run_repl(
                            repo_path=str(selected_repo) if selected_repo else ".",
                            welcome_hint=hint,
                        )
                    except Exception as e:
                        print(fg(f"  · repl error: {type(e).__name__}: {e}", AMBER, on=on), file=sys.stderr)
                elif label == "doctor":
                    _print_doctor(on)
                    _pause(on)
                elif label == "viz":
                    try:
                        import lgwks_graph as gmod
                        import lgwks_graph_viz as viz
                        graph = gmod.get_graph(selected_repo)
                        browser = viz.GraphBrowser(graph, on=on)
                        browser.run()
                    except Exception as e:
                        print(fg(f"  · viz error: {type(e).__name__}: {e}", AMBER, on=on), file=sys.stderr)
                        _pause(on)
                elif argv:
                    _run(_resolve_argv(argv))
                    _pause(on)
                print(ui.spine(on=on))
                _render_current()
                continue
            # Anything else = intent
            if low:
                _intent_flow(low, on)
                print(ui.spine(on=on))
                _render_current()
                continue

        # ── picker screen ───────────────────────────────────────────────────────
        if frame_type == "picker":
            if low.isdigit():
                idx = int(low) - 1
                if 0 <= idx < len(nearby_repos):
                    selected_repo = nearby_repos[idx]
                    print(ui.spine(fg(f"▸ switched to {selected_repo.name}", EMERALD, on=on), on=on))
                    stack.pop()
                    _render_current()
                    continue
            elif low == "b":
                stack.pop()
                print(ui.spine(on=on))
                _render_current()
                continue
            continue

        # ── domain screen ───────────────────────────────────────────────────────
        if frame_type == "domain":
            domain = frame[1]
            verbs = by_domain.get(domain, [])
            if low.isdigit():
                idx = int(low) - 1
                if 0 <= idx < len(verbs):
                    verb = verbs[idx]
                    node = tree.get(verb, {})
                    if "subcommands" in node:
                        stack.append(("command", verb))
                    else:
                        _run(_resolve_argv(["lgwks", verb]))
                        _pause(on)
                    print(ui.spine(on=on))
                    _render_current()
                    continue

        # ── command detail screen ───────────────────────────────────────────────
        if frame_type == "command":
            verb = frame[1]
            node = tree.get(verb, {})
            subcommands = node.get("subcommands", {})
            sc_list = sorted(subcommands.keys())

            if low == "r":
                _run(_resolve_argv(["lgwks", verb]))
                _pause(on)
                print(ui.spine(on=on))
                _render_current()
                continue
            elif low == "h":
                _run_with_help(_resolve_argv(["lgwks", verb]))
                _pause(on)
                print(ui.spine(on=on))
                _render_current()
                continue
            elif low.isdigit() and subcommands:
                idx = int(low) - 1
                if 0 <= idx < len(sc_list):
                    sc_name = sc_list[idx]
                    _run(_resolve_argv(["lgwks", verb, sc_name]))
                    _pause(on)
                    print(ui.spine(on=on))
                    _render_current()
                    continue

        # Unknown input
        print(ui.spine(fg(f"unknown choice: {choice!r}", AMBER, on=on), on=on))
        print(ui.spine(on=on))
        _render_current()


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
