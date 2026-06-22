#!/usr/bin/env python3
"""Keel `sim` harness — replay ONE interleaving against the real lgwks_crdt.GSet.

The system-under-test is the SHIPPED ``lgwks_crdt.GSet`` (grow-only CvRDT). Keel
(``lgwks_verify/keel/src/run-sim.mjs``) enumerates the order-preserving interleavings of the
declared actors' step sequences (the finite schedule space) and sets ``KEEL_SCHEDULE`` to the JSON
of one schedule — a list of ``{actor, op}`` steps. This script replays that one schedule and
applies the CONSISTENCY ORACLE:

    A grow-only set must CONVERGE to the union of all added elements regardless of the order in
    which the adds are applied (the CvRDT commutative/associative/idempotent law, lgwks_crdt.py
    lines 54-58). So the GSet value after replaying this interleaving must equal the
    order-independent union of the elements added in it.

Exit 0  = this interleaving is consistent (value == union).
Exit 1  = divergence — this interleaving is the race (a real CvRDT-law violation would surface here).
Exit 2  = malformed op — recorded by Keel as `unknown`, never a silent pass.

Ops are strings of the form ``add:<element>``.
"""

from __future__ import annotations

import json
import os
import sys

# Keel runs this with cwd = the repo root; make the root importable for a script file.
sys.path.insert(0, os.getcwd())

import lgwks_crdt as crdt  # noqa: E402  (after sys.path fix-up, by design)


def main() -> int:
    try:
        schedule = json.loads(os.environ["KEEL_SCHEDULE"])
    except (KeyError, ValueError) as exc:
        print(f"bad KEEL_SCHEDULE: {exc}", file=sys.stderr)
        return 2

    g = crdt.GSet()
    added: set[str] = set()
    for step in schedule:
        op = step.get("op", "")
        if op.startswith("add:"):
            elem = op.split(":", 1)[1]
            g = g.add(elem)
            added.add(elem)
        else:
            print(f"unknown op {op!r}", file=sys.stderr)
            return 2

    # Consistency oracle: convergence to the order-independent union.
    expected = frozenset(added)
    if g.value() == expected:
        return 0
    print(f"divergence under this interleaving: {set(g.value())} != {set(expected)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
