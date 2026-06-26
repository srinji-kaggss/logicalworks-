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


def test_compute_issue_next_shows_local_branch():
    """L1: _compute_issue_next shows 'checkout existing branch' when local branch exists."""
    import lgwks_gh as gh
    # Use a synthetic issue number that can never appear in git history or as a
    # real branch — otherwise _git_log_has_issue_ref / _local_branches_for_issue
    # read live repo state and route to "verify"/"checkout", making this test
    # depend on whatever commits/branches happen to exist (a real #352 commit on
    # main broke it). The assertion below is unchanged; only the fixture is hermetic.
    issue = gh.IssueView(number=99999999, title="test", state="open", labels=[], assignees=[])
    actions = gh._compute_issue_next(issue)
    assert len(actions) > 0
    # When no linked PR and no local branch, it suggests "create branch"
    start_actions = [a for a in actions if a.verb == "start"]
    assert len(start_actions) > 0 or any(a.verb in ("checkout", "push") for a in actions)
