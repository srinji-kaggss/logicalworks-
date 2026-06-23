"""
lgwks_cli_introspect — one source of truth for live CLI parser introspection + the
verb→domain taxonomy.

Both operator surfaces (the `lgwks_home` browser and `lgwks_repl`) must read the SAME
live `lgwks` dispatcher and group verbs the SAME way, or the two drift (a verb appears
in one and not the other, or lands in a different domain). Previously each re-spelled
the SourceFileLoader block and carried its own `_DOMAINS`/`_domain_for` copy — this
module is the canonical primitive they both call. Per-caller output SHAPING (name list,
tree, hint tuples) stays in the caller; only the shared mechanics live here.

`lgwks` is a script (no .py suffix), so it is loaded via SourceFileLoader and registered
in sys.modules BEFORE exec (Python 3.14 dataclass() needs sys.modules[__name__]).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

# Verb → domain taxonomy. Unknown verbs land in "Other" (never hidden). One source of
# truth for both the home browser and the REPL palette.
DOMAINS: dict[str, list[str]] = {
    # Primary product — the subconscious loop and operator surface
    "Subconscious": ["agent", "map", "engine", "session", "solve", "debug", "intent", "doctor",
                     "spawn", "portal", "agent-os", "tui"],
    # Research and knowledge work — the conscious-layer tools
    "Research":  ["fetch", "refine", "preview", "extract", "convert",
                  "manifest", "login", "cohere", "comprehend", "geo", "public",
                  "akinator", "run", "context", "model-hub", "capture", "jepa",
                  "workflow", "research", "crawl"],
    "GitHub":    ["gh"],
    "DevOps":    ["repo", "review", "project", "batch", "refactor", "hooks"],
    "System":    ["repl", "initialize", "auth", "keyvault", "foundation",
                  "aup", "schema", "codebase", "access", "daemon", "bulk-harvest",
                  "gate", "ops", "human", "verify"],
    # L0 substrate — ingestion, vector store, contracts (foundational, not the product)
    "Substrate": ["store", "memory", "embed", "axiom", "pipeline", "waste",
                  "entity-graph", "graph", "substrate", "score", "rank", "inbound",
                  "admission", "capability", "crdt", "viz-project", "state"],
}


def domain_for(verb: str) -> str:
    for domain, verbs in DOMAINS.items():
        # exact match first
        if verb in verbs:
            return domain
        # prefix match for nested verbs (e.g. "agent-os bootstrap" → "agent-os")
        for v in verbs:
            if verb.startswith(v + " "):
                return domain
    return "Other"


def load_parser():
    """Load the live `lgwks` dispatcher and return its argparse parser.

    Raises on failure — callers decide their own fallback (the UIs emit nothing
    rather than fake/drifting hints).
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("lgwks_cli", str(ROOT / "lgwks"))
    spec = importlib.util.spec_from_loader("lgwks_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("lgwks_cli", mod)
    loader.exec_module(mod)
    return mod.build_parser()


def command_action(parser) -> Any:
    """Return the top-level subparsers action (dest == 'command'), or None."""
    for action in parser._actions:
        if action.dest == "command":
            return action
    return None


def help_by_name(sub_action) -> dict[str, str]:
    """name → trimmed help text for a subparsers action's choices.

    //why: argparse keeps per-verb help on `_choices_actions`, not on the inner
    ArgumentParser objects (their `description` is None when only `help=` was passed).
    """
    return {ca.dest: (ca.help or "").strip() for ca in sub_action._choices_actions}


def command_names() -> list[str]:
    """Sorted live subcommand names; aliases (empty help text) are filtered.

    Falls back to [] if the parser cannot be introspected (e.g. lgwks is broken).
    """
    try:
        parser = load_parser()
    except Exception:
        return []
    sub_action = command_action(parser)
    if sub_action is None or not getattr(sub_action, "choices", None):
        return []
    hb = help_by_name(sub_action)
    return sorted([name for name in sub_action.choices.keys() if hb.get(name)])


def command_tree() -> dict[str, dict[str, Any]]:
    """{verb: {"help": ..., "subcommands": {...}}} — one level deep (the lgwks CLI shape)."""
    try:
        parser = load_parser()
    except Exception:
        return {}
    sub_action = command_action(parser)
    if sub_action is None or not getattr(sub_action, "choices", None):
        return {}

    hb = help_by_name(sub_action)
    tree: dict[str, dict[str, Any]] = {}
    for name, subparser in sub_action.choices.items():
        help_text = hb.get(name, "")
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
            choice_keys = choices.keys() if isinstance(choices, dict) else choices
            node["subcommands"] = {
                sc_name: {"help": sub_help.get(sc_name, "")}
                for sc_name in choice_keys
            }
        tree[name] = node
    return tree
