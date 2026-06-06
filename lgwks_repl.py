"""lgwks_repl — interactive readline harness for lgwks.

//why: the home launcher spawns subprocesses per command, which destroys state
and context. A REPL keeps the graph loaded, offers tab completion, and makes
the tool feel like Claude Code / Codex harness — not a menu system.

Design:
- readline with history (~/.lgwks/history)
- tab completion: commands → node IDs → file paths
- inline evaluation: no subprocess spawn (unless !shell escape)
- persistent graph context: repo loaded once, reused across queries
- special commands: .help .quit .history .repo .refresh
"""

from __future__ import annotations

import atexit
import os
import readline
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = Path.home() / ".lgwks" / "repl_history"
HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── dynamic command discovery (single source of truth: the live parser) ─────────
# //why: hardcoding _COMMANDS drifts from the CLI. The browser already introspects
# the parser; the REPL must use the same source of truth or commands disappear
# from tab completion and the help text.

_DOMAINS: dict[str, list[str]] = {
    "Research":  ["jarvis", "fetch", "refine", "preview", "extract", "convert",
                  "x", "manifest", "login", "cohere", "comprehend", "geo", "public",
                  "akinator", "run", "context", "model-hub"],
    "GitHub":    ["gh"],
    "DevOps":    ["repo", "review", "session", "project", "batch", "refactor", "hooks", "agent-os"],
    "System":    ["solve", "debug", "doctor", "intent", "entity-graph", "graph",
                  "substrate", "repl", "initialize", "auth", "keyvault", "foundation"],
    "Data":      ["store", "memory", "embed"],
}


def _domain_for(verb: str) -> str:
    for domain, verbs in _DOMAINS.items():
        if verb in verbs:
            return domain
    return "Other"


def _live_commands() -> list[str]:
    """Introspect the live lgwks parser and return all registered subcommands.
    Falls back to a static list if introspection fails (e.g. lgwks is broken)."""
    try:
        import importlib.util
        from importlib.machinery import SourceFileLoader
        loader = SourceFileLoader("lgwks_cli", str(ROOT / "lgwks"))
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

    help_by_name = {ca.dest: (ca.help or "").strip() for ca in sub_action._choices_actions}
    # Filter out aliases (empty help text) but keep everything else
    return sorted([name for name in sub_action.choices.keys() if help_by_name.get(name)])


_COMMANDS = _live_commands()
# //why: if introspection fails, _COMMANDS is empty — the REPL still works for
# shell escapes and special commands, but every typed command falls through to
# subprocess (which may also fail). An empty list is honest: we don't know.

_GRAPH_OPTIONS = [
    "--repo", "--refresh", "--impact", "--files", "--radius",
    "--complexity", "--path", "--from", "--to", "--neighbors", "--of",
    "--query",
]

_SUBSTRATE_OPTIONS = [
    "--single", "--multi", "--batch", "--output", "--agent", "--verify",
    "--ground", "--frontier", "--lens", "--depth",
]


class ReplCompleter:
    """Tab completer for the REPL. Completes in order: special, command, option, path."""

    def __init__(self):
        self.graph_node_ids: list[str] = []
        self.current_repo: Path | None = None

    def set_graph_nodes(self, nodes: list[str]) -> None:
        self.graph_node_ids = sorted(nodes)

    def complete(self, text: str, state: int) -> str | None:
        line = readline.get_line_buffer()
        tokens = shlex.split(line)
        if not tokens:
            # first token → commands or specials
            candidates = [c + " " for c in _COMMANDS if c.startswith(text)]
            candidates += [s + " " for s in _SPECIALS if s.startswith(text)]
        elif len(tokens) == 1:
            # still first token
            candidates = [c + " " for c in _COMMANDS if c.startswith(text)]
            candidates += [s + " " for s in _SPECIALS if s.startswith(text)]
        elif tokens[0] in ("graph",):
            candidates = self._complete_graph(text, tokens)
        elif tokens[0] in ("substrate",):
            candidates = self._complete_substrate(text, tokens)
        else:
            candidates = []
            # try path completion for anything that looks like a path arg
            if text.startswith((".", "/", "~")) or "/" in text:
                candidates = self._complete_path(text)
            # also suggest graph nodes for --of, --from, --to, --files
            if any(tokens[-1].startswith("--") and tokens[-1] in ("--of", "--from", "--to") for _ in [0]):
                candidates += [n for n in self.graph_node_ids if n.startswith(text)]
            if "--files" in tokens:
                candidates += [n for n in self.graph_node_ids if n.startswith(text)]

        try:
            return candidates[state]
        except IndexError:
            return None

    def _complete_graph(self, text: str, tokens: list[str]) -> list[str]:
        candidates: list[str] = []
        if text.startswith("-"):
            candidates = [o + " " for o in _GRAPH_OPTIONS if o.startswith(text)]
        elif any(t in tokens for t in ("--of", "--from", "--to", "--files")):
            candidates = [n for n in self.graph_node_ids if n.startswith(text)]
        return candidates

    def _complete_substrate(self, text: str, tokens: list[str]) -> list[str]:
        if text.startswith("-"):
            return [o + " " for o in _SUBSTRATE_OPTIONS if o.startswith(text)]
        return []

    def _complete_path(self, text: str) -> list[str]:
        path = Path(text).expanduser()
        if text.endswith("/"):
            base, prefix = path, ""
        else:
            base, prefix = path.parent, path.name
        try:
            entries = list(base.iterdir())
        except Exception:
            return []
        candidates: list[str] = []
        for e in entries:
            name = e.name
            if name.startswith(prefix):
                suffix = "/" if e.is_dir() else " "
                candidates.append(str(base / name) + suffix)
        return candidates


# ── special commands ─────────────────────────────────────────────────────────

_SPECIALS = [".help", ".quit", ".history", ".repo", ".refresh", ".graph"]


def _cmd_help() -> None:
    """Show commands grouped by domain — same mental model as the browser."""
    # Build domain → commands map from live _COMMANDS
    by_domain: dict[str, list[str]] = {}
    for cmd in _COMMANDS:
        by_domain.setdefault(_domain_for(cmd), []).append(cmd)

    lines = ["\n  lgwks REPL — commands by domain"]
    lines.append("  " + "─" * 35)
    for domain in list(_DOMAINS.keys()) + ["Other"]:
        cmds = by_domain.get(domain, [])
        if not cmds:
            continue
        lines.append(f"  {domain:<12}  {', '.join(cmds)}")
    lines.append("")
    lines.append("  Special commands")
    lines.append("  " + "─" * 35)
    for s in _SPECIALS:
        lines.append(f"  {s:<12}  {_SPECIAL_HELP.get(s, '')}")
    lines.append("")
    lines.append("  Examples:")
    lines.append("    >>> graph --complexity")
    lines.append("    >>> solve git")
    lines.append("    >>> !git status       (shell escape)")
    lines.append("")
    print("\n".join(lines))


_SPECIAL_HELP: dict[str, str] = {
    ".help": "this message",
    ".quit": "exit the REPL",
    ".history": "show last 20 commands",
    ".repo": "show current repo path",
    ".refresh": "reload the graph from disk",
    ".graph": "print graph stats",
}


def _suggest_commands(bad: str) -> str:
    """Return a helpful message when the user types an unknown command."""
    # Numbers are browser navigation, not REPL commands
    if bad.isdigit():
        return (
            f"  · '{bad}' is browser navigation (use numbers in the browser menu,\n"
            f"    not the REPL). Type a command name or .help for the list."
        )
    # Suggest closest match by prefix
    matches = [c for c in _COMMANDS if c.startswith(bad[:2].lower())]
    if matches:
        return f"  · unknown command: {bad!r} — did you mean: {', '.join(matches[:3])}?"
    return f"  · unknown command: {bad!r} — type .help for available commands"


def _cmd_history() -> None:
    n = readline.get_current_history_length()
    start = max(1, n - 19)
    for i in range(start, n + 1):
        print(f"  {i:3d}  {readline.get_history_item(i)}")


# ── graph context ──────────────────────────────────────────────────────────────

class GraphContext:
    """Keeps a loaded graph in memory so repeated queries don't re-parse."""
    def __init__(self):
        self.repo: Path | None = None
        self.graph: Any | None = None  # lgwks_graph.Graph
        self.last_error: str = ""

    def load(self, repo_path: str = ".") -> bool:
        import lgwks_graph as gmod
        p = Path(repo_path).resolve()
        if not (p / ".git").exists():
            self.last_error = f"not a git repo: {p}"
            return False
        self.repo = p
        self.graph = gmod.get_graph(p)
        return True

    def stats(self) -> dict[str, Any]:
        if self.graph is None:
            return {}
        return self.graph.stats()

    def refresh(self) -> bool:
        if self.repo is None:
            self.last_error = "no repo loaded"
            return False
        import lgwks_graph as gmod
        self.graph = gmod.get_graph(self.repo, force_refresh=True)
        return True


# ── command dispatcher ─────────────────────────────────────────────────────────

# Map of commands that we can run inline (without subprocess).
# Each entry is (module_name, dispatch_function_name).
# If not in this map, we fall back to subprocess.
_INLINE_COMMANDS: dict[str, tuple[str, str]] = {
    "graph": ("lgwks_graph", "graph_command"),
    "solve": ("lgwks_solve", "solve_command"),
    "doctor": ("lgwks_capabilities", "doctor_command"),
}


def _dispatch_inline(argv: list[str], ctx: GraphContext) -> int:
    """Run a command inline in the current process, preserving context."""
    cmd = argv[0]
    mapping = _INLINE_COMMANDS.get(cmd)
    if not mapping:
        return -1  # signal: not inline-able
    mod_name, fn_name = mapping
    try:
        mod = __import__(mod_name)
        fn = getattr(mod, fn_name)
    except Exception as e:
        print(f"  · inline import failed: {mod_name}.{fn_name}: {e}", file=sys.stderr)
        return 1
    # Build an argparse-like args object from the argv tail
    args = _argv_to_args(argv[1:])
    # Inject repo context for graph commands
    if cmd == "graph" and ctx.repo and not getattr(args, "repo", None):
        args.repo = str(ctx.repo)
    try:
        return fn(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"  · inline error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def _argv_to_args(argv: list[str]) -> Any:
    """Convert ['--complexity', '--files', 'a.py'] into a argparse-like Namespace."""
    class Args:
        pass
    args = Args()
    i = 0
    while i < len(argv):
        token = argv[i]
        if token.startswith("--"):
            key = token.lstrip("-").replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                val = argv[i + 1]
                # type inference for known numeric flags
                if key in ("radius", "max_depth", "limit"):
                    try:
                        val = int(val)
                    except ValueError:
                        pass
                elif key in ("frontier", "lens", "depth"):
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                setattr(args, key, val)
                i += 2
                continue
            else:
                # boolean flag
                setattr(args, key, True)
        i += 1
    return args


def _dispatch_subprocess(argv: list[str]) -> int:
    """Fallback: run in subprocess (the old way). Used for commands we can't inline."""
    import subprocess
    try:
        result = subprocess.run([sys.executable, str(ROOT / argv[0]), *argv[1:]], capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0 and result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.returncode
    except Exception as e:
        print(f"  · subprocess failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


# ── prompt string ──────────────────────────────────────────────────────────────

def _prompt(ctx: GraphContext) -> str:
    """Build the prompt: green >>> with repo name if loaded."""
    try:
        import lgwks_ui as ui
        on = ui.color_on()
    except Exception:
        on = False
    arrow = ui.fg(">>> ", ui.EMERALD, on=on, bold=True) if on else ">>> "
    if ctx.repo:
        repo_tag = ui.fg(ctx.repo.name, ui.CREAM_DIM, on=on) if on else ctx.repo.name
        return f"{repo_tag} {arrow}"
    return arrow


# ── main loop ──────────────────────────────────────────────────────────────────

def run_repl(repo_path: str = ".", no_color: bool = False, *, welcome_hint: str = "") -> int:
    """Enter the REPL. Returns exit code.

    welcome_hint: shown once on entry so the user knows what context they dropped
    into (e.g. "s solve git    prove what happened (read-only)").
    """
    # Setup readline
    if HISTORY_PATH.exists():
        try:
            readline.read_history_file(str(HISTORY_PATH))
        except Exception:
            pass
    atexit.register(lambda: readline.write_history_file(str(HISTORY_PATH)))

    completer = ReplCompleter()
    readline.parse_and_bind("tab: complete")
    readline.set_completer(completer.complete)

    # Load graph context
    ctx = GraphContext()
    if not ctx.load(repo_path):
        print(f"[repl] {ctx.last_error} — commands will still work, but no graph context.", file=sys.stderr)
    else:
        if ctx.graph:
            completer.set_graph_nodes(list(ctx.graph.nodes.keys()))
            s = ctx.graph.stats()
            print(f"[repl] graph loaded: {s['nodes']} nodes, {s['edges']} edges")

    # Context-aware welcome: bridge browser → REPL mental model
    if welcome_hint:
        print(f"[repl] {welcome_hint}")
    print("[repl] type a command (e.g. solve git, graph --impact) or .help")
    print()

    while True:
        try:
            line = input(_prompt(ctx)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue
        if line in (".quit", "exit", "quit"):
            return 0
        if line == ".help":
            _cmd_help()
            continue
        if line == ".history":
            _cmd_history()
            continue
        if line == ".repo":
            print(f"  {ctx.repo or '(none)'}")
            continue
        if line == ".refresh":
            if ctx.refresh():
                print("  graph refreshed")
                if ctx.graph:
                    completer.set_graph_nodes(list(ctx.graph.nodes.keys()))
            else:
                print(f"  {ctx.last_error}")
            continue
        if line == ".graph":
            s = ctx.stats()
            for k, v in s.items():
                print(f"  {k}: {v}")
            continue
        if line.startswith("!"):
            # shell escape — parsed via shlex (no shell=True) to block injection
            import subprocess
            try:
                shell_argv = shlex.split(line[1:])
            except ValueError as e:
                print(f"  · shell parse error: {e}", file=sys.stderr)
                continue
            if shell_argv:
                subprocess.run(shell_argv)
            continue

        # Parse into argv
        try:
            argv = shlex.split(line)
        except ValueError as e:
            print(f"  · parse error: {e}", file=sys.stderr)
            continue
        if not argv:
            continue

        # If the first token is a known lgwks command, prepend 'lgwks' to make a valid argv
        # Actually, in the REPL we just run the command directly
        if argv[0] in _COMMANDS:
            # Try inline first
            rc = _dispatch_inline(argv, ctx)
            if rc == -1:
                rc = _dispatch_subprocess(["lgwks"] + argv)
            if rc != 0:
                print(f"  · exit {rc}", file=sys.stderr)
        else:
            print(_suggest_commands(argv[0]), file=sys.stderr)

    return 0


# ── entry point for home launcher ──────────────────────────────────────────────

def repl_command(args) -> int:
    """Called from lgwks_home._entryway when user picks the REPL option."""
    repo = getattr(args, "repo", ".")
    return run_repl(repo_path=repo)
