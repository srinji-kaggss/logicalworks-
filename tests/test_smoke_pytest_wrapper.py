"""pytest wrapper for the agent-invocation smoke harness.

Runs `tests/test_agent_invocation_smoke.py` as a subprocess and fails the test if the
harness reports ANY crash/timeout. This is the merge gate that catches the class of
bug no unit assertion sees: a real agent invoking `./lgwks <verb>` and hitting a
NameError/ImportError/silent-fault on a late CLI path.

Skipped in the fast CI tier unless LGWKS_SMOKE=1 (the harness spawns ~26 subprocesses,
so it is gated to the nightly tier alongside the other slow guards).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "tests" / "test_agent_invocation_smoke.py"


@pytest.mark.skipif(
    os.environ.get("LGWKS_SMOKE") != "1",
    reason="agent-invocation smoke harness is slow (26 subprocesses); set LGWKS_SMOKE=1 to run",
)
def test_no_verb_crashes_under_real_agent_invocation() -> None:
    proc = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=240,
    )
    tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
    assert proc.returncode == 0, (
        f"agent-invocation smoke harness FAILED (rc={proc.returncode}).\n"
        f"harness summary: {tail}\n---- stderr ----\n{proc.stderr[-2000:]}"
    )
    # Sanity: the harness must report it ran cases and found zero crashes/timeouts.
    assert "0 crashes" in tail and "0 timeouts" in tail, (
        f"smoke harness did not report a clean result: {tail}\n{proc.stderr[-2000:]}"
    )