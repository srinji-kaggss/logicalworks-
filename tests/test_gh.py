"""Tests for lgwks_gh — GitHub surface with DiD validation.

Strategy: mock subprocess.run. Assert schema, next_actions, input validation,
secret scrubbing, and rate-limit detection.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import lgwks_gh as gh


def _make_run(returncode_val: int = 0, stdout_val: str = "", stderr_val: str = ""):
    def _run(*args, **kwargs):
        class _Result:
            returncode = returncode_val
            stdout = stdout_val
            stderr = stderr_val
        return _Result()
    return _run



# ── input validation ─────────────────────────────────────────────────────────

def test_validate_slug_ok():
    assert gh._validate_slug("acme/widget") == "acme/widget"


def test_validate_slug_none():
    assert gh._validate_slug(None) is None
    assert gh._validate_slug("") is None


def test_validate_slug_bad():
    try:
        gh._validate_slug("../../etc/passwd")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "invalid repo slug" in str(e)


def test_validate_number_ok():
    assert gh._validate_number("42") == 42


def test_validate_number_bad():
    for bad in ["abc", "0", "-1", "10000000", "", "1; rm -rf /"]:
        try:
            gh._validate_number(bad)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass


# ── secret scrub ─────────────────────────────────────────────────────────────

def test_scrub_api_key():
    text = "api_key='sk-1234567890abcdef'"
    assert "[REDACTED]" in gh._scrub(text)
    assert "sk-1234567890abcdef" not in gh._scrub(text)


def test_scrub_token():
    text = "token: ghp_xxxxxxxxxxxxxxxxxxxx"
    assert "[REDACTED]" in gh._scrub(text)


# ── rate limit detection ─────────────────────────────────────────────────────

def test_rate_limit_detected():
    stdout = "API rate limit exceeded. Please retry after 3600 seconds."
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        rc, out = gh._gh("issue", "list")
    assert rc == 1
    assert "rate limit" in out.lower()


# ── auth ─────────────────────────────────────────────────────────────────────

def test_gh_auth_ok():
    with patch("subprocess.run", side_effect=_make_run(0, "✓ Logged in to github.com")):
        rc, out = gh._gh("auth", "status")
    assert rc == 0


def test_gh_auth_fail():
    with patch("subprocess.run", side_effect=_make_run(1, "You are not logged into any GitHub hosts")):
        rc, out = gh._gh("auth", "status")
    assert rc == 1


def test_gh_not_installed():
    def _raise(*a, **k):
        raise FileNotFoundError("gh")
    with patch("subprocess.run", side_effect=_raise):
        rc, out = gh._gh("auth", "status")
    assert rc == 1
    assert "not installed" in out


def test_gh_timeout():
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=30)
    with patch("subprocess.run", side_effect=_timeout):
        rc, out = gh._gh("auth", "status")
    assert rc == 1
    assert "timed out" in out


# ── issue next_actions ─────────────────────────────────────────────────────

def test_issue_next_bug_unassigned():
    issue = gh.IssueView(number=1, title="crash", state="open", labels=["bug"], assignees=[])
    actions = gh._compute_issue_next(issue)
    verbs = [a.verb for a in actions]
    assert "assign" in verbs


def test_issue_next_bug_assigned():
    issue = gh.IssueView(number=1, title="crash", state="open", labels=["bug"], assignees=["alice"])
    actions = gh._compute_issue_next(issue)
    verbs = [a.verb for a in actions]
    assert "assign" not in verbs
    assert "start" in verbs


def test_issue_next_security():
    issue = gh.IssueView(number=1, title="leak", state="open", labels=["security"], assignees=[])
    actions = gh._compute_issue_next(issue)
    verbs = [a.verb for a in actions]
    assert "review" in verbs


def test_issue_next_closed():
    issue = gh.IssueView(number=1, title="done", state="closed", labels=[], assignees=[])
    actions = gh._compute_issue_next(issue)
    assert actions[0].verb == "archive"


def test_issue_next_linked_pr():
    issue = gh.IssueView(number=1, state="open", labels=[], assignees=[], linked_prs=[{"number": 5}])
    actions = gh._compute_issue_next(issue)
    verbs = [a.verb for a in actions]
    assert "review_pr" in verbs


# ── state next_actions ───────────────────────────────────────────────────────

def test_state_next_backlog():
    state = gh.RepoState(open_issues=25, open_prs=2, health_score=0.6)
    actions = gh._compute_state_next(state)
    assert any(a.verb == "triage" for a in actions)


def test_state_next_stale():
    state = gh.RepoState(open_issues=2, open_prs=1, last_commit_age_hours=200, health_score=0.5)
    actions = gh._compute_state_next(state)
    assert any(a.verb == "stale" for a in actions)


def test_state_next_healthy():
    state = gh.RepoState(open_issues=2, open_prs=1, last_commit_age_hours=10, health_score=0.9)
    actions = gh._compute_state_next(state)
    assert not actions


# ── repo state ───────────────────────────────────────────────────────────────

def test_repo_state_inference_from_git():
    with patch("subprocess.run", side_effect=_make_run(0, "https://github.com/acme/widget.git")):
        slug = gh._current_repo_slug()
    assert slug == "acme/widget"


def test_repo_state_inference_ssh():
    with patch("subprocess.run", side_effect=_make_run(0, "git@github.com:acme/widget.git")):
        slug = gh._current_repo_slug()
    assert slug == "acme/widget"


# ── harden ───────────────────────────────────────────────────────────────────

def test_harden_schema():
    def _mock_run(cmd, **kwargs):
        class _Result:
            returncode = 0
            stdout = json.dumps({"tagName": "v1.0.0"})
            stderr = ""
        return _Result()
    with patch("subprocess.run", side_effect=_mock_run):
        result = gh._harden("acme/widget")
    assert result["schema"] == "lgwks.gh.v0"
    assert result["check"] == "harden"
    assert "findings" in result
    assert "next_actions" in result


# ── audit log ───────────────────────────────────────────────────────────────

def test_audit_log(tmp_path: Path):
    original = gh._audit_log_path
    gh._audit_log_path = lambda: tmp_path / "audit.jsonl"
    try:
        gh._audit("harden", {"repo": "acme/demo"}, "completed")
        lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["verb"] == "harden"
        assert rec["outcome"] == "completed"
    finally:
        gh._audit_log_path = original


# ── issue view fallback parsing ──────────────────────────────────────────────

def test_issue_view_fallback_parse():
    stdout = "title:\tBug in parser\nstate:\topen\nlabels:\tbug, priority\n"
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        issue = gh._issue_view(42, None)
    assert issue.number == 42
    assert issue.title == "Bug in parser"
    assert issue.state == "open"
    assert "bug" in issue.labels


# ── issue list parse ─────────────────────────────────────────────────────────

def test_issues_list_parse():
    stdout = "\nNUMBER  TITLE\n  #42  Bug in parser\n  #43  Feature request\n"
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        issues = gh._issues_list(None, "open", None)
    assert len(issues) == 2
    assert issues[0]["number"] == 42


# ── PR list parse ────────────────────────────────────────────────────────────

def test_prs_list_parse():
    stdout = "\nNUMBER  TITLE\n  #7  Add gh module\n  #8  Fix typo\n"
    with patch("subprocess.run", side_effect=_make_run(0, stdout)):
        prs = gh._prs_list(None, "open")
    assert len(prs) == 2
    assert prs[0]["number"] == 7


# ── abuse: shell injection in label ───────────────────────────────────────────

def test_issues_list_bad_label_rejected():
    issues = gh._issues_list("acme/demo", "open", "'; rm -rf /;'")
    assert issues == []


# ── abuse: bad slug in command ──────────────────────────────────────────────

def test_issue_command_bad_slug():
    import argparse
    args = argparse.Namespace(number="42", repo="../../etc/passwd", json=False)
    rc = gh.issue_command(args)
    assert rc == 1
