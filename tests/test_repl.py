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
    """L0: .help prints something."""
    with patch("builtins.print") as mock_print:
        repl._cmd_help()
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("special commands" in t for t in texts)
