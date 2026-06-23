"""Canonical repository Python-file enumeration — one source of truth.

Every bot/reviewer previously re-globbed ``repo.glob("**/*.py")`` with its own
(divergent, usually incomplete) exclusion set. The divergence WAS the bug: a
vendored virtualenv like ``.venv-models/`` — full of multi-MB generated torch /
playwright / huggingface ``.py`` — slipped past the ``{".venv"}`` check and got
ast-parsed on every ``lgwks review``, burning >70s of CPU and effectively hanging
the CLI. This module is the single primitive every caller routes through, so the
exclusion set is defined exactly once.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from lgwks_substrate_config import SKIP_DIRS as _BASE_SKIP_DIRS, with_extras  # one source of truth

# Derive from the canonical base (which already excludes VCS/caches/vendored via
# ``site-packages``) and add the review-scope delta: things that are NOT "code
# under review" — agent worktrees, tool state, archived copies, emitted findings.
# Scanning .worktrees/.claude re-reports every finding once per checkout (review
# noise); archive/ is dead source. caches are belt-and-suspenders.
SKIP_DIRS = with_extras(
    _BASE_SKIP_DIRS,
    ".worktrees", ".claude", "archive", "findings",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
)


def _skip(p: Path) -> bool:
    return any(
        part in SKIP_DIRS or part.startswith(".venv") or part.startswith("venv")
        for part in p.parts
    )


def py_files(repo: Path | str, changed_files: Optional[list[str]] = None) -> list[Path]:
    """Sorted ``.py`` files under ``repo``, excluding vendored/cache/state trees.

    When ``changed_files`` is given, restrict to exactly those paths (bounded
    review scope) — the same files an agent asked to review, nothing else.
    """
    repo = Path(repo)
    if changed_files:
        cand = [repo / c for c in changed_files]
        return sorted(
            p for p in cand
            if p.suffix == ".py" and p.is_file() and not _skip(p)
        )
    return sorted(p for p in repo.glob("**/*.py") if not _skip(p))
