#!/usr/bin/env python3
"""Keel `latency` harness — measure the per-call latency of a representative core lgwks operation.

The system-under-test is the SHIPPED ``lgwks_hashing.content_id`` — the content-addressing primitive
on the hot path of every fabric write (so it is a fair stand-in for "one call" in the
``envelope.target.calls_per_sec`` sense). Keel (``lgwks_verify/keel/src/run-latency.mjs``) runs this
script ``samples`` times; each run measures the MEAN wall-clock latency of the operation over a warm
batch and prints it in milliseconds on stdout. Keel aggregates max/p99/jitter across the samples and
crosses the declared budget.

The budget is NOT fitted to the measurement (that would be a magic constant / teaching-to-the-test).
It is DERIVED and cited: to sustain ``envelope.target.calls_per_sec = 10`` single-threaded, one call
must complete within 1000 ms / 10 = 100 ms. That 100 ms ceiling is the latency budget declared in
``lgwks.profile.json`` with that derivation as its ``source_ref``.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.getcwd())

import lgwks_hashing as h  # noqa: E402  (after sys.path fix-up, by design)

_PAYLOAD = "x" * 1024  # ~1 KiB representative content-addressing input
_WARMUP = 100
_BATCH = 2000


def main() -> int:
    for _ in range(_WARMUP):
        h.content_id(_PAYLOAD)
    t0 = time.perf_counter()
    for _ in range(_BATCH):
        h.content_id(_PAYLOAD)
    mean_ms = (time.perf_counter() - t0) / _BATCH * 1000.0
    print(f"{mean_ms:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
