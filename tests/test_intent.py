"""Tests for lgwks_intent — schema-driven intent router.

Strategy: mock subprocess.run for probes. Assert routing, schema, validation,
substitution, risk classification, and DiD layers.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import lgwks_intent as intent


def _make_run(returncode_val: int = 0, stdout_val: str = "", stderr_val: str = ""):
    def _run(cmd_parts, **kwargs):
        class _Result:
            returncode = returncode_val
            stdout = stdout_val
            stderr = stderr_val
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


def test_resolve_intent_bad_slug(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "lgwks.intent.v0", "repo": "not-a-slug", "next_if": {}}))
    try:
        intent._resolve_intent(path)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "invalid repo slug" in str(e)


def test_resolve_intent_issue_out_of_bounds(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "lgwks.intent.v0", "issue": 99999999, "next_if": {}}))
    try:
        intent._resolve_intent(path)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "issue must be" in str(e)


def test_resolve_intent_unsupported_condition(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "lgwks.intent.v0", "next_if": {"unknown.condition": "noop"}}))
    try:
        intent._resolve_intent(path)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unsupported next_if conditions" in str(e)


def test_resolve_intent_default_last(tmp_path: Path):
    path = tmp_path / "intent.json"
    path.write_text(json.dumps({
        "schema": "lgwks.intent.v0",
        "next_if": {
            "default": "fallback",
            "issue.open": "work",
        },
    }))
    doc = intent._resolve_intent(path)
    keys = list(doc.next_if.keys())
    assert keys[-1] == "default"
    assert keys[0] == "issue.open"


# ── substitution ─────────────────────────────────────────────────────────────

def test_safe_substitute():
    doc = intent.IntentDoc(schema=intent.INTENT_SCHEMA, project="p", repo="a/b", issue=5, pr=3)
    cmd = intent._safe_substitute("lgwks gh issue {issue} --repo {repo}", doc)
    assert "lgwks gh issue 5" in cmd
    assert "a/b" in cmd


def test_safe_substitute_escapes_shell():
    doc = intent.IntentDoc(schema=intent.INTENT_SCHEMA, repo="a/b; rm -rf /", issue=1)
    cmd = intent._safe_substitute("cmd {repo}", doc)
    assert "'" in cmd or '"' in cmd or "\\" in cmd
    assert ";" not in cmd or "'a/b; rm -rf /'" in cmd


# ── risk classification ─────────────────────────────────────────────────────

def test_classify_risk_read():
    assert intent._classify_risk("lgwks review --repo .") == "read"


def test_classify_risk_mutate():
    assert intent._classify_risk("git push origin main") == "mutate"


def test_classify_risk_destructive():
    assert intent._classify_risk("rm -rf build/") == "destructive"


def test_classify_risk_default():
    assert intent._classify_risk("some-unknown-cmd") == "mutate"


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
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "issue.open"
    assert "lgwks gh issue 42" in result.next_cmd
    assert result.next_cmd_risk == "read"


def test_route_issue_closed():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        repo="acme/demo",
        issue=42,
        next_if={"issue.open": "work", "issue.closed": "archive", "default": "idle"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "issue.closed"


# ── routing: tests ───────────────────────────────────────────────────────────

def test_route_tests_fail():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"tests.fail": "lgwks debug test", "tests.pass": "lgwks gh state"},
    )
    with patch("subprocess.run", side_effect=_make_run(1, "FAILED test_x", "")):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "tests.fail"


def test_route_tests_pass():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"tests.fail": "fix", "tests.pass": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, "3 passed", "")):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "tests.pass"


# ── routing: git dirty/clean ─────────────────────────────────────────────────

def test_route_dirty():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"dirty": "commit", "clean": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, " M src/main.py", "")):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "dirty"


def test_route_clean():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"dirty": "commit", "clean": "push"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, "", "")):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "clean"


# ── routing: default fallback ──────────────────────────────────────────────────

def test_route_default_fallback():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"issue.open": "work", "default": "rest"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == "default"


# ── routing: no match no default ───────────────────────────────────────────────

def test_route_no_match():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"issue.open": "work"},
    )
    stdout = json.dumps({"state": "CLOSED"})
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.matched_condition == ""
    assert "no condition matched" in result.reason


# ── routing: probe limit ──────────────────────────────────────────────────────

def test_route_probe_limit():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"issue.open": "a", "issue.closed": "b", "tests.fail": "c", "tests.pass": "d",
                 "dirty": "e", "clean": "f", "pr.draft": "g", "pr.open": "h", "pr.closed": "i",
                 "review.danger": "j", "review.warn": "k", "default": "z"},
    )
    old_limit = intent._MAX_PROBES_PER_ROUTE
    intent._MAX_PROBES_PER_ROUTE = 2
    try:
        with patch("subprocess.run", side_effect=_make_run(0, "")):
            result = intent._route(doc, Path("/tmp"), "intent.json")
    finally:
        intent._MAX_PROBES_PER_ROUTE = old_limit
    assert result.blocked
    assert "probe limit" in result.block_reason


# ── routing: destructive auto-execute blocked ────────────────────────────────

def test_route_destructive_blocked_for_auto():
    doc = intent.IntentDoc(
        schema=intent.INTENT_SCHEMA,
        next_if={"default": "rm -rf build/"},
    )
    with patch("subprocess.run", side_effect=_make_run(0, "")):
        result = intent._route(doc, Path("/tmp"), "intent.json")
    assert result.next_cmd_risk == "destructive"


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
