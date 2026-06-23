"""Regression guard for lgwks_repo_scan — the canonical .py enumerator.

The `review` hang (2026-06-23) was a vendored virtualenv (`.venv-models/`,
hyphen → missed by the `{".venv"}` check) getting ast-parsed on every run. No
test caught it because the suite runs with a clean repo and LGWKS_NO_MODELS=1.
These tests pin the exclusion contract directly on a synthetic tree so the
regression cannot return silently.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lgwks_repo_scan as rs


class TestPyFilesExclusions(unittest.TestCase):
    def _tree(self, root: Path):
        # real source
        (root / "lgwks_real.py").write_text("x = 1\n", encoding="utf-8")
        (root / "pkg").mkdir()
        (root / "pkg" / "mod.py").write_text("y = 2\n", encoding="utf-8")
        # vendored / cache / state that must be skipped
        for d in (".venv", ".venv-models", "venv", "node_modules",
                  ".git", "__pycache__", "store", ".worktrees", "archive"):
            sub = root / d / "deep"
            sub.mkdir(parents=True)
            (sub / "junk.py").write_text("import torch\n", encoding="utf-8")
        # the classic offender: a site-packages tree under ANY venv name
        sp = root / ".venv-models" / "lib" / "py" / "site-packages" / "torch"
        sp.mkdir(parents=True)
        (sp / "huge.py").write_text("# " + "a" * 10000 + "\n", encoding="utf-8")

    def test_excludes_all_vendored_and_state_dirs(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            got = {p.relative_to(root).as_posix() for p in rs.py_files(root)}
            self.assertEqual(got, {"lgwks_real.py", "pkg/mod.py"})

    def test_no_venv_variant_leaks_through(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            leaked = [p for p in rs.py_files(root)
                      if any(part.startswith(".venv") or part == "site-packages"
                             for part in p.parts)]
            self.assertEqual(leaked, [], f"vendored files leaked: {leaked}")

    def test_changed_files_scopes_to_those_paths(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            got = rs.py_files(root, changed_files=["pkg/mod.py"])
            self.assertEqual([p.relative_to(root).as_posix() for p in got], ["pkg/mod.py"])

    def test_changed_files_still_excludes_vendored(self):
        # even if a caller passes a vendored path, it must not be scanned
        with TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            got = rs.py_files(root, changed_files=[".venv/deep/junk.py", "lgwks_real.py"])
            self.assertEqual([p.relative_to(root).as_posix() for p in got], ["lgwks_real.py"])


if __name__ == "__main__":
    unittest.main()
