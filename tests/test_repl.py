"""Tests for lgwks_repl — interactive readline harness."""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import lgwks_repl as repl


# ── argv → args parser ─────────────────────────────────────────────────────────

def test_argv_to_args_boolean_flags():
    """L0: boolean flags become True."""
    args = repl._argv_to_args(["--complexity", "--refresh"])
    assert args.complexity is True
    assert args.refresh is True


def test_argv_to_args_string_values():
    """L0: --key value pairs become attributes."""
    args = repl._argv_to_args(["--repo", "/tmp", "--files", "a.py,b.py"])
    assert args.repo == "/tmp"
    assert args.files == "a.py,b.py"


def test_argv_to_args_numeric():
    """L0: numeric flags are typed as int/float."""
    args = repl._argv_to_args(["--radius", "5", "--frontier", "0.8"])
    assert args.radius == 5
    assert args.frontier == 0.8


# ── completer ──────────────────────────────────────────────────────────────────

def test_completer_commands():
    """L0: first token completion suggests commands."""
    c = repl.ReplCompleter()
    assert c.complete("gr", 0) == "graph "
    assert c.complete("so", 0) == "solve "


def test_completer_graph_options():
    """L0: after 'graph', completes flags."""
    c = repl.ReplCompleter()
    with patch("lgwks_repl.readline.get_line_buffer", return_value="graph --com"):
        assert c.complete("--com", 0) == "--complexity "


def test_completer_path():
    """L0: _complete_path returns entries for an existing directory."""
    c = repl.ReplCompleter()
    # test the internal path completer directly on current dir
    results = c._complete_path("./")
    assert len(results) >= 1


# ── graph context ───────────────────────────────────────────────────────────────

def test_graph_context_load_fails_on_non_git(tmp_path):
    """L1: loading a non-git directory fails gracefully."""
    ctx = repl.GraphContext()
    ok = ctx.load(str(tmp_path))
    assert ok is False
    assert "not a git repo" in ctx.last_error


# ── inline dispatch ─────────────────────────────────────────────────────────────

def test_dispatch_inline_returns_minus_one_for_unknown():
    """L0: unknown commands return -1 (fallback to subprocess)."""
    ctx = repl.GraphContext()
    rc = repl._dispatch_inline(["unknown-cmd"], ctx)
    assert rc == -1


def test_dispatch_inline_graph_complexity(tmp_path, capsys):
    """L0: inline graph --complexity runs without subprocess."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)

    ctx = repl.GraphContext()
    ctx.load(str(repo))
    # _dispatch_inline expects the FULL argv including flags
    rc = repl._dispatch_inline(["graph", "--complexity"], ctx)
    assert rc == 0


# ── special commands ───────────────────────────────────────────────────────────

def test_cmd_help_prints():
    """L0: .help prints domain-grouped commands (same mental model as browser)."""
    with patch("builtins.print") as mock_print:
        repl._cmd_help()
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("commands by domain" in t for t in texts)
    assert any("Special commands" in t for t in texts)


def test_suggest_commands_for_number():
    """L0: typing a number in the REPL gets a helpful 'use browser menu' message."""
    msg = repl._suggest_commands("1")
    assert "browser navigation" in msg


def test_suggest_commands_prefix_match():
    """L0: typing an unknown prefix suggests closest matching commands."""
    msg = repl._suggest_commands("sol")
    assert "solve" in msg


def test_suggest_commands_no_match():
    """L0: completely unknown command shows generic help message."""
    msg = repl._suggest_commands("xyz")
    assert "unknown command" in msg
    assert ".help" in msg


def test_live_commands_non_empty():
    """L0: dynamic command discovery must find at least the commands we know exist."""
    cmds = repl._live_commands()
    assert "gh" in cmds
    assert "solve" in cmds
    assert "jarvis" in cmds


def test_repl_welcome_hint_shown():
    """L0: welcome_hint is printed on REPL entry."""
    with patch("builtins.input", side_effect=[".quit"]):
        with patch("builtins.print") as mock_print:
            repl.run_repl(welcome_hint="commands: solve git, gh issues")
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("commands: solve git, gh issues" in t for t in texts)


def test_repl_unknown_command_number_gives_browser_hint():
    """L1: end-to-end: user types '1' in REPL → gets browser navigation hint."""
    with patch("builtins.input", side_effect=["1", ".quit"]):
        with patch("builtins.print") as mock_print:
            repl.run_repl()
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("browser navigation" in t for t in texts)


def test_repl_commands_match_cli_no_drift():
    """L1: REPL command list must match the live CLI parser.
    Regression: _COMMANDS was a hardcoded list that drifted from the CLI,
    missing 18 commands. Now it's derived from the parser — this test catches
    any future drift."""
    import lgwks_home as home
    cli_cmds = set(home._build_command_tree().keys())
    repl_cmds = set(repl._COMMANDS)
    missing = cli_cmds - repl_cmds
    assert not missing, f"REPL is missing CLI commands: {sorted(missing)}"


def test_repl_help_shows_all_domains():
    """L1: .help must show every domain that has at least one command."""
    with patch("builtins.print") as mock_print:
        repl._cmd_help()
    texts = " ".join(str(c) for c in mock_print.call_args_list)
    # Every domain in _DOMAINS should appear if it has commands
    for domain in repl._DOMAINS:
        cmds_in_domain = [c for c in repl._COMMANDS if repl._domain_for(c) == domain]
        if cmds_in_domain:
            assert domain in texts, f"domain '{domain}' missing from .help output"
