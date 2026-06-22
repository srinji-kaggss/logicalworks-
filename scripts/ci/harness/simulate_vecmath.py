#!/usr/bin/env python3
"""Keel `simulate` harness — drive a real lgwks_vecmath function across ONE input vector.

The system-under-test is the SHIPPED ``lgwks_vecmath`` module (imported, never reimplemented).
Keel (``lgwks_verify/keel/src/run-simulate.mjs``) enumerates the finite input envelope from the
scenario's sensor model, sets ``KEEL_VECTOR`` to the JSON of one vector's values, runs this script
once per vector, and compares the number printed on stdout to the scenario's A6 reference table.

``argv[1]`` selects which deterministic vecmath identity to exercise. Every identity is
reconstructable by hand with a calculator and no internet (the lgwks "calculator test"):

    l2_norm_3n4n     ||[3n, 4n]||           = 5*|n|        (3-4-5 Pythagorean)
    dot_nn           <[n, n], [n, n]>       = 2*n^2
    cosine_orth      cos([n, 0], [0, n])    = 0            (orthogonal; zero-vector graceful)
    cosine_parallel  cos([n, 0], [2n, 0])   = 1 (n != 0), 0 at the zero vector

Exit 0 always when the function returns; the verdict is Keel's reference comparison, not this
script's judgement (A6: truth traces to the reference data, not the harness's intuition).
A bad ``expr`` or malformed input exits non-zero so Keel records `unknown`, never a silent pass.
"""

from __future__ import annotations

import json
import os
import sys

# Keel runs this with cwd = the repo root (profile.target.root). A script file puts its own
# directory on sys.path[0], not the root, so make the root importable explicitly.
sys.path.insert(0, os.getcwd())

import lgwks_vecmath as m  # noqa: E402  (after sys.path fix-up, by design)


def main() -> int:
    expr = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        n = float(json.loads(os.environ["KEEL_VECTOR"])["n"])
    except (KeyError, ValueError, TypeError) as exc:
        print(f"bad KEEL_VECTOR: {exc}", file=sys.stderr)
        return 2

    if expr == "l2_norm_3n4n":
        out = m.l2_norm([3.0 * n, 4.0 * n])
    elif expr == "dot_nn":
        out = m.dot([n, n], [n, n])
    elif expr == "cosine_orth":
        out = m.cosine([n, 0.0], [0.0, n])
    elif expr == "cosine_parallel":
        out = m.cosine([n, 0.0], [2.0 * n, 0.0])
    else:
        print(f"unknown expr {expr!r}", file=sys.stderr)
        return 2

    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
