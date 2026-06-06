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


def test_browser_entryway_quits_on_q():
    """L0: typing 'q' exits the browser cleanly."""
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", return_value="q"):
            with patch("lgwks_home.print"):
                rc = home._browser_entryway(on=False)
    assert rc == 0


def test_browser_entryway_dispatches_solve_git():
    """L0: picking 's' (quick action) runs lgwks solve git and pauses before re-rendering."""
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["s", "q"]):
            with patch("lgwks_home._run") as mock_run:
                with patch("lgwks_home._pause") as mock_pause:
                    with patch("lgwks_home.print"):
                        with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                            with patch("lgwks_home._repo_for_command", return_value=[]):
                                home._browser_entryway(on=False)
    mock_run.assert_called_once_with(["lgwks", "solve", "git"])
    mock_pause.assert_called_once()


def test_browser_entryway_dispatches_doctor():
    """L0: picking 'd' (quick action) prints doctor output and pauses."""
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["d", "q"]):
            with patch("lgwks_home._print_doctor") as mock_doc:
                with patch("lgwks_home._pause") as mock_pause:
                    with patch("lgwks_home.print"):
                        with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                            home._browser_entryway(on=False)
    mock_doc.assert_called_once()
    mock_pause.assert_called_once()


def test_build_command_tree_non_empty():
    """L0: parser introspection must discover at least the commands we know exist."""
    tree = home._build_command_tree()
    assert "gh" in tree
    assert "jarvis" in tree
    assert "solve" in tree
    # crawl alias should be filtered out (empty help)
    assert "crawl" not in tree


def test_domain_for_coverage():
    """L0: every discovered command must map to a known domain (no 'Other' catch-all)."""
    tree = home._build_command_tree()
    for verb in tree:
        domain = home._domain_for(verb)
        assert domain != "Other", f"{verb} is unmapped — add it to _DOMAINS"


def test_render_command_detail_with_subcommands():
    """L0: gh (orchestrator) must show its subcommands in the detail view."""
    tree = home._build_command_tree()
    node = tree.get("gh", {})
    assert "subcommands" in node
    with patch("lgwks_home.print") as mock_print:
        home._render_command_detail("gh", node, on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("issue" in t for t in texts)
    assert any("pr" in t for t in texts)


def test_render_command_detail_leaf():
    """L0: leaf commands (no subcommands) must show run/help options, not a subcommand list."""
    tree = home._build_command_tree()
    node = tree.get("solve", {})
    assert "subcommands" not in node
    with patch("lgwks_home.print") as mock_print:
        home._render_command_detail("solve", node, on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("run" in t for t in texts)
    assert any("help" in t for t in texts)


def test_browser_navigates_domain_to_command():
    """L0: user picks domain '1' (Research), then command '1' (first Research verb), then 'q'."""
    tree = home._build_command_tree()
    research_verbs = sorted([v for v in tree if home._domain_for(v) == "Research"])
    first_verb = research_verbs[0]
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["1", "1", "q"]):
            with patch("lgwks_home._run") as mock_run:
                with patch("lgwks_home._pause"):
                    with patch("lgwks_home.print"):
                        with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                            home._browser_entryway(on=False)
    # The first Research verb should have been run
    mock_run.assert_called_once_with(["lgwks", first_verb])


def test_browser_back_navigation():
    """L0: 'b' at domain level pops back to home; 'b' at home stays at home."""
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["1", "b", "q"]):
            with patch("lgwks_home._run") as mock_run:
                with patch("lgwks_home._pause"):
                    with patch("lgwks_home.print"):
                        with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                            home._browser_entryway(on=False)
def test_detect_repo_context_in_repo():
    """L0: when cwd is a git repo, _detect_repo_context returns it with empty nearby list."""
    fake = Path("/tmp/fake-repo")
    with patch("lgwks_home._is_git_repo", return_value=True):
        with patch("lgwks_home.Path.cwd", return_value=fake):
            repo, nearby = home._detect_repo_context()
    assert repo is not None
    assert repo.resolve() == fake.resolve()
    assert nearby == []


def test_detect_repo_context_not_in_repo():
    """L0: when cwd is not a git repo, _detect_repo_context returns None + nearby repos."""
    fake_nearby = [Path("/a"), Path("/b")]
    with patch("lgwks_home._is_git_repo", return_value=False):
        with patch("lgwks_home._scan_nearby_repos", return_value=fake_nearby):
            repo, nearby = home._detect_repo_context()
    assert repo is None
    assert nearby == fake_nearby


def test_repo_status_line_clean():
    """L0: clean repo returns 'clean'; dirty repo returns count string."""
    with patch("lgwks_home.subprocess.run", return_value=FakeResult(stdout="")):
        assert home._repo_status_line(Path("/x")) == "clean"
    with patch("lgwks_home.subprocess.run", return_value=FakeResult(stdout=" M a.py\n?? b.py\n")):
        assert "2" in home._repo_status_line(Path("/x"))


def test_repo_for_command_aware():
    """L0: repo-aware commands (gh, solve) get --repo injected; unaware commands do not."""
    repo = Path("/tmp/fake")
    assert home._repo_for_command("gh", repo) == ["--repo", str(repo)]
    assert home._repo_for_command("solve", repo) == ["--repo", str(repo)]
    assert home._repo_for_command("doctor", repo) == []
    assert home._repo_for_command("gh", None) == []


def test_quick_actions_with_repo():
    """L0: when a repo is active, quick actions include 'g' (gh issues) and 's' (solve)."""
    actions = home._quick_actions_for_repo(Path("/tmp/fake"))
    keys = [a[0] for a in actions]
    assert "s" in keys
    assert "g" in keys
    assert "d" in keys


def test_quick_actions_without_repo():
    """L0: when no repo is active, quick actions still include 's' and 'd' but no 'g'."""
    actions = home._quick_actions_for_repo(None)
    keys = [a[0] for a in actions]
    assert "s" in keys
    assert "d" in keys
    assert "g" not in keys


def test_no_repo_screen_shows_nearby():
    """L0: starting with no repo context shows the no-repo screen with nearby projects."""
    nearby = [Path("/Users/srinji/project-a"), Path("/Users/srinji/project-b")]
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["q"]):
            with patch("lgwks_home._detect_repo_context", return_value=(None, nearby)):
                with patch("lgwks_home.print") as mock_print:
                    home._browser_entryway(on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("not in a git repo" in t for t in texts)
    assert any("project-a" in t for t in texts)


def test_no_repo_continue_without_project():
    """L0: pressing 'n' on no-repo screen switches to the full home browser."""
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["n", "q"]):
            with patch("lgwks_home._detect_repo_context", return_value=(None, [])):
                with patch("lgwks_home.print") as mock_print:
                    home._browser_entryway(on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    # After 'n', the home browser should render (showing domain grid)
    assert any("Research" in t for t in texts)


def test_no_repo_picks_nearby_project():
    """L0: pressing '1' on no-repo screen selects the first nearby repo and switches to home."""
    nearby = [Path("/Users/srinji/project-a"), Path("/Users/srinji/project-b")]
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["1", "q"]):
            with patch("lgwks_home._detect_repo_context", return_value=(None, nearby)):
                with patch("lgwks_home.print") as mock_print:
                    home._browser_entryway(on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    # Should show the switched-to message and then home browser
    assert any("switched to project-a" in t for t in texts)


def test_home_repo_picker():
    """L0: pressing 'p' on home screen opens the project picker; picking '1' switches repo."""
    nearby = [Path("/Users/srinji/project-b")]
    current = Path("/Users/srinji/project-a")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["p", "1", "q"]):
            with patch("lgwks_home._detect_repo_context", return_value=(current, nearby)):
                with patch("lgwks_home.print") as mock_print:
                    home._browser_entryway(on=False)
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("switch project" in t for t in texts)
    assert any("switched to project-b" in t for t in texts)


def test_resolve_argv_injects_repo():
    """L0: _resolve_argv injects --repo for repo-aware commands when a repo is selected."""
    with patch("lgwks_home._repo_for_command", return_value=["--repo", "/tmp/fake"]):
        # _resolve_argv is a closure inside _browser_entryway; test via the public side-effect on _run
        fake_repo = Path("/tmp/fake")
        with patch("lgwks_home.sys.stdin.isatty", return_value=True):
            with patch("lgwks_home._ask", side_effect=["s", "q"]):
                with patch("lgwks_home._run") as mock_run:
                    with patch("lgwks_home._pause"):
                        with patch("lgwks_home.print"):
                            with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                                home._browser_entryway(on=False)
        mock_run.assert_called_once_with(["lgwks", "solve", "git", "--repo", "/tmp/fake"])


def test_render_home_browser_shows_repo():
    """L0: home browser shows current project name when a repo is active."""
    tree = home._build_command_tree()
    with patch("lgwks_home.print") as mock_print:
        home._render_home_browser(tree, on=False, repo=Path("/Users/srinji/logic-os-kernel"))
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("current project" in t for t in texts)
    assert any("logic-os-kernel" in t for t in texts)


def test_render_no_repo_home_shows_options():
    """L0: no-repo screen shows create / initialize / continue options."""
    with patch("lgwks_home.print") as mock_print:
        home._render_no_repo_home(on=False, nearby=[])
    texts = [str(c) for c in mock_print.call_args_list]
    assert any("create repo" in t for t in texts)
    assert any("initialize" in t for t in texts)
    assert any("continue" in t for t in texts)


def test_repo_for_command_coverage():
    """L0: repo-aware verbs get --repo; everything else returns empty."""
    repo = Path("/tmp/fake")
    repo_aware_verbs = {"gh", "repo", "review", "session", "graph", "solve", "debug", "intent", "entity-graph"}
    for verb in repo_aware_verbs:
        assert home._repo_for_command(verb, repo) == ["--repo", str(repo)]
    for verb in ("doctor", "jarvis", "akinator", "fetch", "crawl", "plan", "pr", "issue"):
        assert home._repo_for_command(verb, repo) == []


def test_browser_repl_uses_selected_repo():
    """L0: pressing 'r' from home with a selected repo passes that repo to run_repl.
    Regression: previously run_repl() was called with no args, so it fell back to
    cwd and printed 'not a git repo' even though a project was picked."""
    fake_repo = Path("/tmp/fake-repo")
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["r", "q"]):
            with patch("lgwks_home.print"):
                with patch("lgwks_home._detect_repo_context", return_value=(fake_repo, [])):
                    with patch("lgwks_repl.run_repl") as mock_repl:
                        home._browser_entryway(on=False)
    mock_repl.assert_called_once_with(repo_path=str(fake_repo))


def test_browser_repl_without_repo_uses_cwd():
    """L0: pressing 'r' when no repo is selected passes '.' so run_repl uses cwd.
    Must press 'n' first to exit no_repo screen and enter home mode."""
    with patch("lgwks_home.sys.stdin.isatty", return_value=True):
        with patch("lgwks_home._ask", side_effect=["n", "r", "q"]):
            with patch("lgwks_home.print"):
                with patch("lgwks_home._detect_repo_context", return_value=(None, [])):
                    with patch("lgwks_repl.run_repl") as mock_repl:
                        home._browser_entryway(on=False)
    mock_repl.assert_called_once_with(repo_path=".")

