#!/usr/bin/env python3
"""Keel `soak` harness — measure the sustained-safe throughput of lgwks on the calls_per_sec axis.

Emits a ``capacity-profile/v0`` JSON on stdout (the contract ``run-soak.mjs`` ingests):

    {"schema":"capacity-profile/v0","dimension":"calls_per_sec","v_no":<sustained-safe>,"v_ne":<peak>}

The representative "call" is ``lgwks_hashing.content_id`` over a ~1 KiB payload — the
content-addressing primitive on the hot path of every fabric write. The harness runs a real
escalate→sustain loop: several timed windows, each measuring ops/sec. It reports
``v_no`` = the MINIMUM window rate observed (the conservative sustained-safe limit — we do not
claim a peak we cannot hold) and ``v_ne`` = the maximum window rate (never-exceed / observed peak).

This is a genuine measurement, not a declared constant: the number traces to wall-clock work done
on this machine at this source version. Keel content-addresses the node on source, so an unchanged
tree reuses the (re-measured) profile; ``acceptEnvelope`` then crosses v_no against
``envelope.target.calls_per_sec × margin``. Timing is an empirical sensor; the accept decision is
deterministic.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

import lgwks_hashing as h  # noqa: E402  (after sys.path fix-up, by design)

_PAYLOAD = "x" * 1024
_WINDOWS = 5
_WINDOW_SECONDS = 0.5


def measure_window(seconds: float) -> float:
    """Return the sustained ops/sec over one timed window."""
    count = 0
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        h.content_id(_PAYLOAD)
        count += 1
    elapsed = max(time.perf_counter() - (deadline - seconds), 1e-9)
    return count / elapsed


def main() -> int:
    # warm the path so the first window is not penalised by import/JIT-cache effects
    for _ in range(1000):
        h.content_id(_PAYLOAD)
    rates = [measure_window(_WINDOW_SECONDS) for _ in range(_WINDOWS)]
    v_no = min(rates)   # conservative sustained-safe limit (claim only what we can hold)
    v_ne = max(rates)   # observed peak (never-exceed)
    profile = {
        "schema": "capacity-profile/v0",
        "dimension": "calls_per_sec",
        "v_no": round(v_no, 2),
        "v_ne": round(v_ne, 2),
        "samples": [round(r, 2) for r in rates],
    }
    print(json.dumps(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
