"""Tests for lgwks_intent — schema-driven intent router.

Strategy: mock subprocess.run for probes. Assert routing, schema, substitution.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import lgwks_intent as intent


def _make_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    def _run(*args, **kwargs):
        class _Result:
            returncode = returncode
            stdout = stdout
            stderr = stderr
        return _Result()
    return _run


# ── intent resolution ────────────────────────────────────────────────────────

def test_resolve_intent_valid(tmp_path: Path):
    data = {
        "schema": "lgwks.intent.v0",
        "project": "demo",
        "repo": "acme/demo",
        "issue": 42,
        "goal": "ship it",
        "next_if": {"issue.open": "lgwks gh issue {issue}"},
    }
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(data))
    doc = intent._resolve_intent(path)
    assert doc.project == "demo"
    assert doc.issue == 42
    assert doc.next_if["issue.open"] == "lgwks gh issue {issue}"


def test_resolve_intent_bad_schema(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "wrong", "project": "x"}))
    try:
        intent._resolve_intent(path)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "expected schema" in str(e)


# ── substitution ─────────────────────────────────────────────────────────────

def test_substitute():
    doc = intent.IntentDoc(schema=intent.INTENT_SCHEMA, project="p", repo="a/b", issue=5, pr=3)
    cmd = intent._substitute("lgwks gh issue {issue} --repo {repo}", doc)
    assert cmd == "lgwks gh issue 5 --repo a/b"


# ── routing: issue.open ───────────────────────────────────────────────────────

def test_route_issue_open():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        repo="acme/demo",
        issue=42,
        next_if={"issue.open": "lgwks gh issue {issue}"},
    )
    stdout = json.dumps({"state": "OPEN"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "issue.open"
    assert "lgwks gh issue 42" in result.next_cmd


def test_route_issue_closed():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        repo="acme/demo",
        issue=42,
        next_if={"issue.open": "work", "issue.closed": "archive", "default": "idle"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "issue.closed"


# ── routing: tests ───────────────────────────────────────────────────────────

def test_route_tests_fail():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"tests.fail": "lgwks debug test", "tests.pass": "lgwks gh state"},
    )
    with patch("subprocess.run", side_effect=_make_run(1, "FAILED test_x", "")):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "tests.fail"


def test_route_tests_pass():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"tests.fail": "fix", "tests.pass": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, "3 passed", "")):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "tests.pass"


# ── routing: git dirty/clean ─────────────────────────────────────────────────

def test_route_dirty():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"dirty": "commit", "clean": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, " M src/main.py", "")):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "dirty"


def test_route_clean():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"dirty": "commit", "clean": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, "", "")):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "clean"


# ── routing: default fallback ──────────────────────────────────────────────────

def test_route_default_fallback():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"issue.open": "work", "default": "rest"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == "default"


# ── routing: no match no default ───────────────────────────────────────────────

def test_route_no_match():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"issue.open": "work"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"))
    assert result.matched_condition == ""
    assert "no condition matched" in result.reason


# ── init command ───────────────────────────────────────────────────────────────

def test_init_command():
    import argparse
    args = argparse.Namespace(name="demo")
    rc = intent.init_command(args)
    assert rc == 0


# ── parser registration ──────────────────────────────────────────────────────

def test_add_parser():
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers()
    intent.add_parser(sub)
    assert True
