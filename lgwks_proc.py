"""lgwks_proc — the single source of truth for safe subprocess invocation.

run_git is the (rc, stdout) git wrapper that was triplicated verbatim across
lgwks_repo / lgwks_agent_os / lgwks_solve: same subprocess.run + timeout +
"never crash, return (1, '<git failed: ...>')" contract. Centralizing means one
place sets the invocation hygiene (timeout always present, check=False, exceptions
turned into a return value instead of an unhandled crash).

Deliberately NOT folded in here (different contracts, by design):
  - lgwks_axiom._git  -> returns a 3-tuple (rc, stdout, stderr); axiom consumes stderr.
  - lgwks_daemon._git -> merges stdout+stderr and lets timeouts raise (daemon-local policy).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["run_git"]


def run_git(repo: Path | str, *args: str, timeout: int = 30) -> tuple[int, str]:
    """Run `git -C <repo> <args>`; return (returncode, stripped stdout).

    Never raises: a timeout or spawn failure returns (1, "<git failed: ...>").
    """
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 1, f"<git failed: {e}>"
