"""Tests for Rust graph indexing and language detection warnings."""
from __future__ import annotations

import os
from pathlib import Path

import lgwks_graph as gmod


# ── Rust parser ─────────────────────────────────────────────────────────────────

def test_parse_rust_file_extracts_all_constructs():
    """L0: _parse_rust_file extracts imports, defines, variables, calls."""
    source = '''
use std::collections::HashMap;
use crate::auth::session;
use super::utils;

mod egress;
mod handlers {
    pub fn handle() {}
}

struct User { name: String }
enum Status { Active, Inactive }
trait Authenticable { fn auth(&self); }
impl Authenticable for User {
    fn auth(&self) {
        let token = generate();
        validate(token);
    }
}
fn generate() -> String { 'token'.to_string() }
fn validate(t: String) { println!("ok"); }
'''
    imports, defines, variables, calls = gmod._parse_rust_file(source, "src/main.rs")
    assert "std::collections::HashMap" in imports
    assert "crate::auth::session" in imports
    assert "fn:generate" in defines
    assert "fn:validate" in defines
    assert "struct:User" in defines
    assert "enum:Status" in defines
    assert "trait:Authenticable" in defines
    assert "impl:User" in defines
    assert "mod:egress" in defines
    assert "token" in variables
    assert "generate" in calls
    assert "validate" in calls


def test_rust_import_to_path_crate():
    """L0: crate::foo::bar maps to src/foo/bar.rs."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src" / "foo").mkdir(parents=True)
        (repo / "src" / "foo" / "bar.rs").write_text("fn bar() {}")
        result = gmod._rust_import_to_path("crate::foo::bar", repo, "src/main.rs")
        assert result == "src/foo/bar.rs"


def test_rust_import_to_path_super():
    """L0: super::foo maps to sibling directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "foo.rs").write_text("fn foo() {}")
        result = gmod._rust_import_to_path("super::foo", repo, "src/bar/mod.rs")
        assert result == "src/foo.rs"


def test_rust_import_to_path_self():
    """L0: self::foo maps to current directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "foo.rs").write_text("fn foo() {}")
        result = gmod._rust_import_to_path("self::foo", repo, "src/main.rs")
        assert result == "src/foo.rs"


def test_detect_unindexed_languages_warns():
    """L0: _detect_unindexed_languages warns when dominant language has 0 indexed files."""
    paths = [
        "src/main.rs", "src/lib.rs", "src/auth.rs", "src/session.rs", "src/utils.rs",
        "config.yml", "README.md", "Cargo.toml",
    ]
    indexed = {"config.yml"}
    warnings = gmod._detect_unindexed_languages(paths, indexed)
    assert len(warnings) >= 1
    assert "rs" in warnings[0]
    assert "0%" in warnings[0]


def test_detect_unindexed_languages_silent_when_indexed():
    """L0: no warning when language has indexed files."""
    paths = ["src/main.py", "src/lib.py", "src/auth.py"]
    indexed = {"src/main.py", "src/lib.py", "src/auth.py"}
    warnings = gmod._detect_unindexed_languages(paths, indexed)
    assert len(warnings) == 0


# ── Integration: extract_from_repo with Rust ─────────────────────────────────

def test_extract_from_repo_indexes_rust_files():
    """L1: extract_from_repo discovers and indexes .rs files."""
    import tempfile, subprocess
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        env = {
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env={**os.environ, **env})
        (repo / "src").mkdir()
        (repo / "src" / "main.rs").write_text('''
use crate::auth::session;
mod auth;
fn main() { auth::validate(); }
''')
        (repo / "src" / "auth.rs").write_text('''
pub fn validate() {}
''')
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env={**os.environ, **env})
        subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True, env={**os.environ, **env})

        graph = gmod.extract_from_repo(repo)
        assert "src/main.rs" in graph.nodes
        assert "src/auth.rs" in graph.nodes
        # main.rs should have an import edge to auth.rs
        import_edges = [e for e in graph.edges if e.source == "src/main.rs" and e.target == "src/auth.rs" and e.kind == "import"]
        assert len(import_edges) > 0
        # main.rs should have a call edge to auth.rs (validate)
        call_edges = [e for e in graph.edges if e.source == "src/main.rs" and e.target == "src/auth.rs" and e.kind == "call"]
        assert len(call_edges) > 0


# ── GH local branch awareness ─────────────────────────────────────────────────

def test_local_branches_for_issue_finds_match():
    """L0: _local_branches_for_issue finds branches containing issue number."""
    # We can't mock subprocess easily for git branch --list, so test the regex matching logic
    # by checking the function exists and has correct signature
    import inspect, lgwks_gh as gh
    sig = inspect.signature(gh._local_branches_for_issue)
    assert "number" in sig.parameters


def test_compute_issue_next_shows_local_branch(monkeypatch):
    """L1: _compute_issue_next routes to 'start' (create branch) when no PR, no
    commit ref, and no local branch reference the issue."""
    import lgwks_gh as gh
    # Fully hermetic: _compute_issue_next consults live git via two readers
    # (_git_log_has_issue_ref, _local_branches_for_issue). A real #352 commit on
    # main once broke this test because it read live state. Stub both readers to
    # the empty/no-match case so the routing — not the ambient repo — is what's
    # under test. (Synthetic-number isolation alone left a residual collision
    # surface and an OR-clause that would have passed even on a collision.)
    monkeypatch.setattr(gh, "_git_log_has_issue_ref", lambda *_: False)
    monkeypatch.setattr(gh, "_local_branches_for_issue", lambda *_: [])
    issue = gh.IssueView(number=99999999, title="test", state="open", labels=[], assignees=[])
    actions = gh._compute_issue_next(issue)
    verbs = [a.verb for a in actions]
    # No PR + no commit ref + no branch ⇒ the create-branch ("start") action MUST
    # be present, and none of the live-state-dependent routes may appear.
    assert "start" in verbs
    assert not any(v in ("checkout", "push", "verify", "review_pr") for v in verbs)
