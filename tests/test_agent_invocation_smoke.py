"""Agent-invocation smoke harness.

Fires EVERY canonical verb the way a real agent does — as a subprocess invoking the
dispatcher (`./lgwks <verb> <args>`) — and fails on any Python-class crash
(NameError / ImportError / AttributeError / unhandled Traceback) that unit tests miss.

This is the gate that catches the `./lgwks research --live "..."` NameError class of
failure: a bug in a late CLI path that no unit assertion reaches because tests call
functions directly, never through the dispatcher shell.

Design rules (rooted in the real failure):
- Invoke `./lgwks` (the dispatcher), NOT python -m or direct function calls. The bug
  was a missing `import sys` reached only via the dispatcher's argparse dispatch.
- Realistic agent-shaped args per verb, biased to OFFLINE paths (no network flakiness).
  Network-dependent verbs are exercised but tolerant of no-egress sandboxes.
- Treat a nonzero exit that prints a Python traceback as CRASH (the gate fails).
- Treat nonzero exits that are legitimate argparse usage errors as SKIP (not crashes).
- Treat hangs (>timeout) as CRASH — the "agent stuck" failure mode.
- The harness itself is hermetic: temp sandbox, stubbed cache, no writes to the repo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LGWKS = REPO / "lgwks"
PY = sys.executable

TRACEBACK_RX = re.compile(
    r"Traceback \(most recent call last\)|^NameError:|^ImportError:|^AttributeError:|"
    r"^ModuleNotFoundError:|^TypeError:|^SyntaxError:",
    re.MULTILINE,
)


def _env(tmp: Path) -> dict[str, str]:
    e = os.environ.copy()
    e["LGWKS_CACHE_DIR"] = str(tmp / "cache")
    e["HOME"] = str(tmp)  # isolate config/state
    e.pop("CI", None)
    return e


def _run(args: list[str], tmp: Path, timeout: float = 20.0) -> tuple[int, str, str, bool]:
    """Return (rc, stdout, stderr, timed_out)."""
    try:
        p = subprocess.run(
            [PY, str(LGWKS), *args],
            cwd=str(REPO),
            env=_env(tmp),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", e.stderr or "", True


def _classify(rc: int, out: str, err: str, timed_out: bool) -> tuple[str, str]:
    """Return (status, reason). status ∈ {PASS, CRASH, USAGE, OPERATIONAL, TIMEOUT}.

    CRASH      = Python/JS traceback or silent fault (exit 0 WITH a FAULT/traceback marker).
                 The silent-fault class is the most dangerous: a verb that prints a stack
                 trace AND returns 0, so a caller believes it succeeded (e.g. the verify
                 ENOENT that returned 0 with a Node stacktrace).
    OPERATIONAL= clean nonzero exit, NO traceback (e.g. "no evidence", "profile not found").
                 Legitimate runtime signal, not a code defect.
    USAGE      = argparse usage/required-arg error.
    """
    if timed_out:
        return "TIMEOUT", "process did not exit within timeout"
    blob = out + "\n" + err
    has_trace = bool(TRACEBACK_RX.search(blob))
    has_fault = bool(re.search(r"\bRUNNER FAULT\b|unhandled rejection|UnhandledPromiseRejection", blob, re.I))
    if rc == 0 and (has_trace or has_fault):
        return "CRASH", "exit 0 WITH traceback/fault — silent failure: " + blob.strip()[:400]
    if rc == 0:
        return "PASS", ""
    if has_trace or has_fault:
        m = TRACEBACK_RX.search(blob) or re.search(r"RUNNER FAULT", blob, re.I)
        return "CRASH", blob[max(0, (m.start() if m else 0) - 200):(m.end() if m else 200) + 300].strip()
    if re.search(r"usage: lgwks |error: the following arguments are required|"
                 r"argument.*invalid choice|unrecognized arguments", blob):
        return "USAGE", "argparse usage error (expected, not a crash)"
    return "OPERATIONAL", f"clean nonzero exit={rc}. stderr: {err[:300]}"


# Each entry: (label, argv, min_status)
#   PASS/OPERATIONAL/USAGE acceptable, CRASH/TIMEOUT fail the suite.
# Args chosen to exercise the happy offline path each verb actually serves.
CASES: list[tuple[str, list[str], set[str]]] = [
    # --- read tier (the agent's bread-and-butter) ---
    ("extract/missing-file", ["extract", "/nonexistent/path.pdf"], {"OPERATIONAL", "USAGE"}),
    ("extract/help-json", ["extract", "--help"], {"PASS"}),
    ("convert/help", ["convert", "--help"], {"PASS"}),
    # --- refactor (the rewired verb) ---
    ("refactor/help", ["refactor", "--help"], {"PASS"}),
    # --- research: offline paths only (network is a separate tier) ---
    ("research/probe-offline", ["research", "--probe", "test query"], {"PASS", "OPERATIONAL", "USAGE"}),
    ("research/quick-offline", ["research", "--quick", "test query"], {"PASS", "OPERATIONAL", "USAGE"}),
    ("research/no-args", ["research"], {"USAGE"}),
    # --- review / verify ---
    ("review/help", ["review", "--help"], {"PASS"}),
    ("verify/missing-profile", ["verify", "--profile", "nonexistent"], {"OPERATIONAL", "USAGE"}),
    # --- graph / repo ---
    ("graph/help", ["graph", "--help"], {"PASS"}),
    ("repo/help", ["repo", "--help"], {"PASS"}),
    # --- fetch / crawl (network: tolerate egress-blocked) ---
    ("fetch/help", ["fetch", "--help"], {"PASS"}),
    ("crawl/help", ["crawl", "--help"], {"PASS"}),
    # --- orchestrators ---
    ("agent/help", ["agent", "--help"], {"PASS"}),
    ("solve/help", ["solve", "--help"], {"PASS"}),
    # --- subcommand shells ---
    ("ops/help", ["ops", "--help"], {"PASS"}),
    ("state/help", ["state", "--help"], {"PASS"}),
    ("model-hub/help", ["model-hub", "--help"], {"PASS"}),
    ("model-hub/list", ["model-hub", "list"], {"PASS", "OPERATIONAL", "USAGE"}),
    ("human/help", ["human", "--help"], {"PASS"}),
    # --- capability/introspection ---
    ("doctor", ["doctor"], {"PASS"}),
    ("manifest/help", ["manifest", "--help"], {"PASS"}),
    ("auth/help", ["auth", "--help"], {"PASS"}),
    ("gate/help", ["gate", "--help"], {"PASS"}),
    # --- top-level ---
    ("root/help", ["--help"], {"PASS"}),
    ("root/no-args", [], {"PASS", "USAGE"}),
]


def run_all() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lgwks-smoke-"))
    try:
        results = []
        for label, argv, acceptable in CASES:
            rc, out, err, to = _run(argv, tmp)
            status, reason = _classify(rc, out, err, to)
            ok = status in acceptable
            results.append((label, status, ok, reason))
            line = f"{'OK ' if ok else 'FAIL'} {label:28s} {status:8s}"
            if not ok and reason:
                line += f"  :: {reason[:300]}"
            print(line, file=sys.stderr)

        crashes = [r for r in results if r[1] == "CRASH"]
        timeouts = [r for r in results if r[1] == "TIMEOUT"]
        fails = [r for r in results if not r[2]]

        print("", file=sys.stderr)
        print(f"smoke: {len(results)} cases, {sum(1 for r in results if r[2])} ok, "
              f"{len(crashes)} crashes, {len(timeouts)} timeouts, {len(fails)} total fails",
              file=sys.stderr)

        if fails:
            print("\nFAILURES:", file=sys.stderr)
            for label, status, _, reason in fails:
                print(f"  {label}: {status}\n    {reason[:600]}", file=sys.stderr)
        return 1 if fails else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_all())