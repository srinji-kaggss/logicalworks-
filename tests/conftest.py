"""Pytest configuration — ensure repo root is on sys.path for imports."""
import os
import sys
from pathlib import Path

# Add repo root to path so lgwks_* modules resolve correctly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Hermetic git identity for tests that shell out to `git commit` (graph fixtures,
# session/worktree tests). Without this they pass only where the runner's shell
# already has a global git identity — git's auto-derived "user@host" fallback
# yields an EMPTY name on a clean CI runner (or with user.useConfigOnly) and
# `git commit` exits 128. setdefault: a real configured env still wins; we only
# provide a floor so the suite is reproducible independent of the host's config.
for _k, _v in (
    ("GIT_AUTHOR_NAME", "lgwks-tests"),
    ("GIT_AUTHOR_EMAIL", "tests@lgwks.local"),
    ("GIT_COMMITTER_NAME", "lgwks-tests"),
    ("GIT_COMMITTER_EMAIL", "tests@lgwks.local"),
):
    os.environ.setdefault(_k, _v)
