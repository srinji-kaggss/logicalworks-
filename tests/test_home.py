"""Tests for lgwks_home — the launcher dashboard and entryway."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_home as home

ROOT = Path(__file__).resolve().parent.parent


class FakeResult:
    """Mock subprocess.CompletedProcess."""
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_surfaces_stdout():
    """L0: picking a menu item should show the subprocess output, not silently swallow it."""
    with patch("lgwks_home.subprocess.run", return_value=FakeResult(stdout="hello from solve\n")) as mock_run:
        with patch("lgwks_home.print") as mock_print:
            home._run(["lgwks", "solve", "git"])
    mock_run.assert_called_once()
    # stdout was forwarded to print
    calls = [c for c in mock_print.call_args_list if "hello from solve" in str(c)]
    assert len(calls) >= 1


def test_run_surfaces_failure_code():
    """L0: a failing subprocess must not be silent — the user needs to see the exit code."""
    with patch("lgwks_home.subprocess.run", return_value=FakeResult(returncode=42)) as mock_run:
        with patch("lgwks_home.print") as mock_print:
            home._run(["lgwks", "solve", "git"])
    mock_run.assert_called_once()
    # one of the print calls contains the exit code
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("exited 42" in t for t in texts)


def test_run_surfaces_stderr_on_failure():
    """L0: stderr from a failed run must be printed so the user knows what broke."""
    with patch(
        "lgwks_home.subprocess.run",
        return_value=FakeResult(returncode=1, stderr="module not found: lgwks_solve"),
    ):
        with patch("lgwks_home.print") as mock_print:
            home._run(["lgwks", "solve", "git"])
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("module not found" in t for t in texts)


def test_run_exception_surfaces():
    """L1: if subprocess.run itself raises (e.g. file not found), the exception name is printed."""
    with patch("lgwks_home.subprocess.run", side_effect=FileNotFoundError("no lgwks")):
        with patch("lgwks_home.print") as mock_print:
            home._run(["lgwks", "solve", "git"])
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("FileNotFoundError" in t for t in texts)


def test_pause_reads_enter():
    """L0: _pause blocks on input so the menu doesn't immediately overwrite subprocess output."""
    with patch("lgwks_home.input", return_value="") as mock_input:
        home._pause(on=False)
    mock_input.assert_called_once()


def test_pause_graceful_on_eof():
    """L1: EOFError (piped/non-interactive) must not crash the pause."""
    with patch("lgwks_home.input", side_effect=EOFError):
        home._pause(on=False)  # should not raise


def test_entryway_quits_on_q():
    """L0: typing 'q' exits the entryway cleanly."""
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", return_value="q"):
            with patch("lgwks_home.print"):
                rc = home._entryway(on=False)
    assert rc == 0


def test_entryway_dispatches_solve_git():
    """L0: picking '1' runs lgwks solve git and pauses before re-rendering."""
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["1", "q"]) as mock_ask:
            with patch("lgwks_home._run") as mock_run:
                with patch("lgwks_home._pause") as mock_pause:
                    with patch("lgwks_home.print"):
                        home._entryway(on=False)
    mock_run.assert_called_once_with(["lgwks", "solve", "git"])
    mock_pause.assert_called_once()


def test_entryway_dispatches_doctor():
    """L0: picking '3' prints doctor output and pauses."""
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["3", "q"]):
            with patch("lgwks_home._print_doctor") as mock_doc:
                with patch("lgwks_home._pause") as mock_pause:
                    with patch("lgwks_home.print"):
                        home._entryway(on=False)
    mock_doc.assert_called_once()
    mock_pause.assert_called_once()
