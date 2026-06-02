"""Tests for lgwks_debug — automated debugging.

Strategy: mock subprocess.run to avoid real commands. Assert pattern matching,
findings, schema, and log append.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import lgwks_debug as dbg


def _make_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    def _run(*args, **kwargs):
        class _Result:
            returncode = returncode
            stdout = stdout
            stderr = stderr
        return _Result()
    return _run


# ── pattern matching ─────────────────────────────────────────────────────────

def test_match_missing_module():
    text = "ModuleNotFoundError: No module named 'pytest'"
    findings = dbg._match_patterns(text)
    assert len(findings) == 1
    assert findings[0].check == "missing_module"
    assert "pytest" in findings[0].message
    assert "pip install pytest" in findings[0].fix_cmd


def test_match_merge_conflict():
    text = "CONFLICT (content): Merge conflict in src/main.py"
    findings = dbg._match_patterns(text)
    assert any(f.check == "merge_conflict" for f in findings)


def test_match_gh_auth():
    text = "gh: not authenticated"
    findings = dbg._match_patterns(text)
    assert any(f.check == "gh_not_authed" for f in findings)


def test_match_no_pattern():
    text = "Everything worked fine"
    findings = dbg._match_patterns(text)
    assert not findings


# ── command runner ─────────────────────────────────────────────────────────────

def test_debug_command_run_failure():
    stdout = "ModuleNotFoundError: No module named 'pytest'"
    with patch("subprocess.run", side_effect=_make_run(1, stdout, "")):
        result = dbg.debug_command_run("python -m pytest")
    assert result.exit_code == 1
    assert result.schema == "lgwks.debug.v0"
    assert any(f.check == "missing_module" for f in result.findings)


def test_debug_command_run_success():
    with patch("subprocess.run", side_effect=_make_run(0, "OK", "")):
        result = dbg.debug_command_run("echo OK")
    assert result.exit_code == 0
    assert not result.findings


def test_debug_command_timeout():
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="sleep 100", timeout=1)
    with patch("subprocess.run", side_effect=_timeout):
        result = dbg.debug_command_run("sleep 100")
    assert result.exit_code == 124


# ── test runner ──────────────────────────────────────────────────────────────

def test_run_tests_failure():
    stdout = "FAILED tests/test_foo.py::test_bar - AssertionError: 1 != 2"
    with patch("subprocess.run", side_effect=_make_run(1, stdout, "")):
        result = dbg._run_tests()
    assert result.exit_code == 1
    assert any(f.check == "pytest_failed" for f in result.findings)


def test_run_tests_success():
    with patch("subprocess.run", side_effect=_make_run(0, "3 passed", "")):
        result = dbg._run_tests()
    assert result.exit_code == 0


# ── scrubber ─────────────────────────────────────────────────────────────────

def test_scrub_secrets():
    text = "api_key='sk-1234567890abcdef' password='hunter2'"
    scrubbed = dbg._scrub(text)
    assert "[REDACTED]" in scrubbed
    assert "sk-1234567890abcdef" not in scrubbed


# ── debug log ────────────────────────────────────────────────────────────────

def test_debug_log_append_and_load(tmp_path: Path):
    # Override log path to tmp
    original_path = dbg._debug_log_path
    log_file = tmp_path / "debug-log.jsonl"
    dbg._debug_log_path = lambda: log_file
    try:
        result = dbg.DebugResult(command="echo hi", exit_code=1, findings=[
            dbg.DebugFinding(check="fail", severity="warn", message="oops", fix_cmd="fix", fix_risk="read")
        ])
        dbg._append_debug_log(result)
        rec = dbg._load_last_failure()
        assert rec is not None
        assert rec["command"] == "echo hi"
        assert rec["exit_code"] == 1
    finally:
        dbg._debug_log_path = original_path


def test_load_last_no_log():
    original_path = dbg._debug_log_path
    dbg._debug_log_path = lambda: Path("/nonexistent/debug-log.jsonl")
    try:
        rec = dbg._load_last_failure()
        assert rec is None
    finally:
        dbg._debug_log_path = original_path


# ── parser registration ──────────────────────────────────────────────────────

def test_add_parser():
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers()
    dbg.add_parser(sub)
    # Should not raise
    assert True
