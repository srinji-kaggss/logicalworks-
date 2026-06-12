"""lgwks_crdt — CRDT state: G-Set, OR-Set, LWW-Register (I9).

No transport, no networking, no consensus — state-merge semantics ONLY.
Defines how two already-produced states merge; does not move bytes between machines.

Authority: spec/second-harness/INGESTION-PLAN.md §I9
           spec/second-harness/INGESTION-LAYER.md §6 (SEC requirement)
Schema:    lgwks.crdt.state.v1   (family: harness)
Issue:     I9

Design (INGESTION-PLAN §I9):
    world-nodes  = G-Set keyed by cid   # grow-only; idempotent add → CvRDT (I1 dedup)
    tenant edges = OR-Set (add/remove + unique tags)
                 | LWW-Register tie-broken by cognition-chain head (logical clock)
    merge(a, b)  = commutative ∧ associative ∧ idempotent   # CvRDT laws; SEC follows

Decisions:
    D1: merge core is PURE (no I/O) — clock is an ARGUMENT, not a global read.
        This makes every merge call deterministic and trivially testable.
    D2: G-Set merge = set-union (append-only world-nodes, mirroring the axiom fabric DAG).
    D3: OR-Set uses unique add-tags (hex str); remove cancels only the observed tags
        (add-wins on concurrent add+remove).
    D4: LWW-Register tie-breaks by (seq, head_bytes) from CognitionLog._tail_hash /
        _next_seq — NOT wall-clock (wall-clock is non-deterministic, breaks replay).
    D5: lgwks.crdt.state.v1 crosses the store file boundary → JSON-Schema file required
        (REGISTRY rule 3); see docs/schemas/lgwks.crdt.state.v1.json.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.crdt.state.v1"


# ---------------------------------------------------------------------------
# G-Set (grow-only set)
# ---------------------------------------------------------------------------

@dataclass
class GSet:
    """Grow-only set keyed by cid.  merge = set-union.

    CvRDT proof:
      commutative:  union(A,B) == union(B,A)
      associative:  union(union(A,B),C) == union(A,union(B,C))
      idempotent:   union(A,A) == A
    Adding the same cid twice is a no-op (I1 cid dedup invariant — assert explicitly).
    """

    _elements: frozenset[str] = field(default_factory=frozenset)

    def add(self, cid: str) -> "GSet":
        """Return a new GSet with cid added (pure — original is unchanged)."""
        return GSet(self._elements | frozenset([cid]))

    def merge(self, other: "GSet") -> "GSet":
        """Merge two G-Sets via set-union (commutative, associative, idempotent)."""
        return GSet(self._elements | other._elements)

    def value(self) -> frozenset[str]:
        """Return the current element set."""
        return self._elements

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GSet):
            return NotImplemented
        return self._elements == other._elements

    def __repr__(self) -> str:
        return f"GSet({len(self._elements)} elements)"


# ---------------------------------------------------------------------------
# OR-Set (observed-remove set)
# ---------------------------------------------------------------------------

@dataclass
class ORSet:
    """Observed-remove set. add-wins on concurrent add+remove.

    Each add carries a unique tag (32-hex nonce). A remove cancels ONLY the tags
    it observed at the time of removal — a concurrent add (with a new tag) survives.

    CvRDT laws hold (D3):
      merge = pair-wise union of (adds, removes) → commutative, associative, idempotent.
    """

    # _adds: elem → frozenset of tags present from add operations
    _adds: dict[str, frozenset[str]] = field(default_factory=dict)
    # _removes: elem → frozenset of tags that have been removed
    _removes: dict[str, frozenset[str]] = field(default_factory=dict)

    def add(self, elem: str, tag: str | None = None) -> "ORSet":
        """Add elem with a unique tag (auto-generated if not provided)."""
        if tag is None:
            tag = secrets.token_hex(16)
        new_adds = dict(self._adds)
        new_adds[elem] = new_adds.get(elem, frozenset()) | frozenset([tag])
        return ORSet(new_adds, dict(self._removes))

    def remove(self, elem: str, observed_tags: frozenset[str] | None = None) -> "ORSet":
        """Remove elem, cancelling only the observed_tags (defaults to all current tags).

        //why: if observed_tags is None we cancel all currently visible tags, which
        is the common single-writer case.  Concurrent add (new tag) survives.
        """
        current_tags = self._adds.get(elem, frozenset())
        if observed_tags is None:
            observed_tags = current_tags
        new_removes = dict(self._removes)
        new_removes[elem] = new_removes.get(elem, frozenset()) | (current_tags & observed_tags)
        return ORSet(dict(self._adds), new_removes)

    def merge(self, other: "ORSet") -> "ORSet":
        """Merge two OR-Sets (commutative, associative, idempotent)."""
        all_elems = set(self._adds) | set(other._adds)
        new_adds: dict[str, frozenset[str]] = {}
        new_removes: dict[str, frozenset[str]] = {}
        for elem in all_elems:
            new_adds[elem] = self._adds.get(elem, frozenset()) | other._adds.get(elem, frozenset())
            new_removes[elem] = self._removes.get(elem, frozenset()) | other._removes.get(elem, frozenset())
        return ORSet(new_adds, new_removes)

    def value(self) -> frozenset[str]:
        """Return the current visible elements (add-wins: elem present if any add-tag not removed)."""
        out = set()
        for elem, tags in self._adds.items():
            live_tags = tags - self._removes.get(elem, frozenset())
            if live_tags:
                out.add(elem)
        return frozenset(out)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ORSet):
            return NotImplemented
        return self.value() == other.value()

    def __repr__(self) -> str:
        return f"ORSet({len(self.value())} elements visible)"


# ---------------------------------------------------------------------------
# LWW-Register (last-writer-wins)
# ---------------------------------------------------------------------------

@dataclass
class LWWRegister:
    """Last-writer-wins register. Tie-break: higher seq wins; equal seq → higher head_bytes.

    head and seq come from CognitionLog._tail_hash / _next_seq (D4).
    NEVER tie-break by wall-clock — non-deterministic, breaks replay.
    """

    _value: Any = None
    _head: str = ""    # cognition chain head hash (hex str) — logical clock
    _seq: int = -1     # cognition chain seq — monotone counter

    def set(self, value: Any, *, head: str, seq: int) -> "LWWRegister":
        """Return new register with value if (seq, head) dominates current."""
        if (seq, head) > (self._seq, self._head):
            return LWWRegister(value, head, seq)
        return LWWRegister(self._value, self._head, self._seq)

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        """Merge two LWW-Registers: higher (seq, head) wins (deterministic)."""
        if (other._seq, other._head) > (self._seq, self._head):
            return LWWRegister(other._value, other._head, other._seq)
        return LWWRegister(self._value, self._head, self._seq)

    def value(self) -> Any:
        return self._value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWRegister):
            return NotImplemented
        # Two registers are equal if they hold the same (value, head, seq)
        return (self._value, self._head, self._seq) == (other._value, other._head, other._seq)

    def __repr__(self) -> str:
        return f"LWWRegister(value={self._value!r}, seq={self._seq})"


# ---------------------------------------------------------------------------
# merge_state dispatch
# ---------------------------------------------------------------------------

def merge_state(a: GSet | ORSet | LWWRegister, b: GSet | ORSet | LWWRegister) -> Any:
    """Merge two CRDT states of the same type. Raises TypeError on type mismatch."""
    if type(a) is not type(b):
        raise TypeError(
            f"merge_state requires identical CRDT types, got {type(a).__name__} and {type(b).__name__}"
        )
    return a.merge(b)


# ---------------------------------------------------------------------------
# Serialization helpers (for lgwks.crdt.state.v1 payload)
# ---------------------------------------------------------------------------

def serialise(state: GSet | ORSet | LWWRegister) -> dict:
    """Encode a CRDT state as a lgwks.crdt.state.v1 dict (no free-text fields)."""
    if isinstance(state, GSet):
        return {
            "schema": SCHEMA,
            "type": "gset",
            "elements": sorted(state.value()),
        }
    if isinstance(state, ORSet):
        return {
            "schema": SCHEMA,
            "type": "orset",
            "adds": {k: sorted(v) for k, v in state._adds.items()},
            "removes": {k: sorted(v) for k, v in state._removes.items()},
        }
    if isinstance(state, LWWRegister):
        return {
            "schema": SCHEMA,
            "type": "lww",
            "value": state._value,
            "head": state._head,
            "seq": state._seq,
        }
    raise TypeError(f"unknown CRDT type: {type(state).__name__}")


def deserialise(d: dict) -> GSet | ORSet | LWWRegister:
    """Decode a lgwks.crdt.state.v1 dict back to a CRDT instance."""
    t = d.get("type")
    if t == "gset":
        return GSet(frozenset(d["elements"]))
    if t == "orset":
        adds = {k: frozenset(v) for k, v in d.get("adds", {}).items()}
        removes = {k: frozenset(v) for k, v in d.get("removes", {}).items()}
        return ORSet(adds, removes)
    if t == "lww":
        return LWWRegister(d.get("value"), d.get("head", ""), d.get("seq", -1))
    raise ValueError(f"unknown CRDT type in payload: {t!r}")


# ---------------------------------------------------------------------------
# Convergence sink + reconverge (ARCH L6 — the live convergence path, #100)
# ---------------------------------------------------------------------------
# The merge algebra above is pure and stateless. To make a RUN reconverge with
# prior runs (rather than start empty and overwrite), replica state is loaded
# from and committed to a ConvergenceSink. This is the #97 swap seam: the default
# is a local JSON file; a future kernel-tape sink is a sibling impl behind the
# SAME interface — the merge functions never change and take no kernel type.


@runtime_checkable
class ConvergenceSink(Protocol):
    """Where converged CRDT replica state is loaded from and committed to.

    `load()` returns the prior replica state keyed by name ({} on first run).
    `commit(state)` durably persists the converged state. Zero kernel dependency.
    """

    def load(self) -> dict[str, GSet | ORSet | LWWRegister]: ...

    def commit(self, state: dict[str, GSet | ORSet | LWWRegister]) -> None: ...


class JsonFileSink:
    """Default ConvergenceSink — a flat {key: lgwks.crdt.state.v1} JSON file.

    Pure-Python, local-first, no kernel import. Output is sorted for byte-stable
    serialisation (SEC: same converged state → identical bytes).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, GSet | ORSet | LWWRegister]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {k: deserialise(v) for k, v in raw.items()}

    def commit(self, state: dict[str, GSet | ORSet | LWWRegister]) -> None:
        payload = {k: serialise(v) for k, v in state.items()}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )


def reconverge(
    sink: ConvergenceSink,
    current: dict[str, GSet | ORSet | LWWRegister],
) -> dict[str, GSet | ORSet | LWWRegister]:
    """Load prior replica state from `sink`, merge it per-key with `current`, commit
    the converged result, and return it. This is the live convergence path (ARCH L6).

    Each per-key merge is a CvRDT merge (commutative ∧ associative ∧ idempotent), so
    the committed state is independent of the order runs execute in and of how many
    times any run is replayed — a run RECONVERGES instead of resetting. A key present
    on only one side is carried through unchanged; a key whose CRDT type differs
    between prior and current raises TypeError (via merge_state).
    """
    prior = sink.load()
    merged: dict[str, GSet | ORSet | LWWRegister] = {}
    for k in set(prior) | set(current):
        if k in prior and k in current:
            merged[k] = merge_state(prior[k], current[k])
        else:
            # Carry-through (key on one side only): self-merge so the committed bytes
            # are CANONICAL — identical to the form a later cross-merge produces. Without
            # this, a first run and a replayed run serialise differently (e.g. OR-Set
            # merge materialises empty remove-keys), breaking byte-level idempotency.
            only = current[k] if k in current else prior[k]
            merged[k] = merge_state(only, only)
    sink.commit(merged)
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("crdt", help="CRDT state merge — G-Set / OR-Set / LWW (I9)")
    sp = p.add_subparsers(dest="crdt_cmd", required=True)

    info_p = sp.add_parser("info", help="show CRDT design and SEC proof summary")
    info_p.set_defaults(func=_cmd_info)

    merge_p = sp.add_parser("merge", help="merge two serialised CRDT state files")
    merge_p.add_argument("a", help="path to first state JSON file")
    merge_p.add_argument("b", help="path to second state JSON file")
    merge_p.set_defaults(func=_cmd_merge)


def _cmd_info(args) -> int:
    import json as _json

    print(_json.dumps({
        "schema": SCHEMA,
        "types": {
            "gset": "grow-only set keyed by cid; merge=set-union; CvRDT (commutative, associative, idempotent)",
            "orset": "observed-remove set; add-wins on concurrent add+remove; OR-Set semantics",
            "lww": "last-writer-wins register; tie-break by (seq, head) from cognition chain — NOT wall-clock",
        },
        "sec_proof": "convergence via random permutation test across N replicas (tests/test_crdt.py)",
        "clock_source": "CognitionLog._tail_hash + _next_seq (lgwks_cognition.py:50,81)",
        "clock_rule": "NO wall-clock in merge — same inputs → same winner across runs",
    }, indent=2))
    return 0


def _cmd_merge(args) -> int:
    import json as _json
    import sys as _sys

    try:
        with open(args.a, encoding="utf-8") as f:
            da = _json.load(f)
        with open(args.b, encoding="utf-8") as f:
            db = _json.load(f)
    except (OSError, _json.JSONDecodeError) as e:
        print(f"error: cannot load state file: {e}", file=_sys.stderr)
        return 1

    try:
        sa = deserialise(da)
        sb = deserialise(db)
        merged = merge_state(sa, sb)
    except (TypeError, ValueError) as e:
        print(f"error: {e}", file=_sys.stderr)
        return 1

    print(_json.dumps(serialise(merged), indent=2))
    return 0
