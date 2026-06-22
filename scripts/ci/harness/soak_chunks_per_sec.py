#!/usr/bin/env python3
"""Keel `soak` harness — measure sustained-safe throughput of lgwks on the chunks_per_sec axis.

The second envelope dimension (replacing the fictitious multi-tenant `users` axis — lgwks is
local-first / single-operator, repo CLAUDE.md). The representative work is the ingestion pipeline's
text segmentation: ``lgwks_chunking.SlidingWindowChunking().chunk(doc)`` over a ~1000-word document.
This is a genuinely DIFFERENT operation from the content-addressing `calls_per_sec` axis (it stresses
string scanning / windowing, not hashing), so the two dimensions characterise different parts of the
machine rather than re-measuring one.

Emits a ``capacity-profile/v0`` on stdout: ``v_no`` = MIN window rate (conservative sustained-safe),
``v_ne`` = MAX window rate (observed peak). A real measurement, model-free (LGWKS_NO_MODELS), traced
to wall-clock work at this source version; ``acceptEnvelope`` crosses v_no against
``envelope.target.chunks_per_sec × margin``.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

import lgwks_chunking as chunking  # noqa: E402  (after sys.path fix-up, by design)

_DOC = "lorem ipsum dolor sit amet " * 200  # ~1000-word representative document
_WINDOWS = 5
_WINDOW_SECONDS = 0.5


def measure_window(chunker, seconds: float) -> float:
    """Return sustained chunks/sec over one timed window."""
    chunks = 0
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        chunks += len(chunker.chunk(_DOC))
    elapsed = max(time.perf_counter() - (deadline - seconds), 1e-9)
    return chunks / elapsed


def main() -> int:
    chunker = chunking.SlidingWindowChunking()
    for _ in range(50):  # warm
        chunker.chunk(_DOC)
    rates = [measure_window(chunker, _WINDOW_SECONDS) for _ in range(_WINDOWS)]
    profile = {
        "schema": "capacity-profile/v0",
        "dimension": "chunks_per_sec",
        "v_no": round(min(rates), 2),
        "v_ne": round(max(rates), 2),
        "samples": [round(r, 2) for r in rates],
    }
    print(json.dumps(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
