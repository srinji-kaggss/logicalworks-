"""
lgwks_axiom — first-pass implementation of the Axiom v0 ISA verifier core.

Realizes SPEC-axiom-isa-v0 §2 (the capsule), §4 (the decidable click), §5 (capability up the DAG),
§14 (pending->committed transaction). This is the KEYSTONE that proves §0 end-to-end on commodity
hardware with ZERO AI: validity is a decidable check (enum membership + capability-lattice subset +
interval bounds + base-first), computable on a phone. Strip every model out and this still runs.

Scope of this first pass: the trust core only — capsule + canonical CID + the click + the fabric +
the pending/commit transaction + one worked deterministic gauge. NOT wired into the lgwks CLI dispatch
yet, NOT lowered to WASM (SPEC §6, unbuilt). Pure stdlib; no network, no LLM, no wall-clock inside the
core (the caller passes `now` so the verifier and transaction stay replayable — SPEC determinism rule).

NAMING CAVEAT (Director, 2026-06-06): "capsule"/"node" is a PROVISIONAL name for the L3 primitive, and
node-first vs relation-first is an OPEN fork (SPEC §OPEN). The verifier below is name- and shape-agnostic:
it checks a typed content-addressed record against its dependency edges, whatever we end up calling it.

HASH: SPEC/ADR-068 canon is BLAKE3; it is not installed here, so this first pass uses hashlib.blake2b
as a deterministic stand-in. The CID contract (content-address over canonical bytes) is unchanged; only
the digest function swaps when blake3 is wired.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# --- §2 closed vocabulary: a capsule's kind MUST be one of these (enum-membership = part of the click) ---
KINDS = frozenset(
    {"entity", "role", "state", "transition", "capability", "constraint", "effect", "evidence"}
)
# kinds whose click demands human confirmation before effecting (SPEC §8 Allow|RequireConfirm|Block)
EFFECTFUL = frozenset({"effect", "transition"})


@dataclass(frozen=True)
class Capsule:
    """One content-addressed typed record. Claim asserts; Hole abstains (is_hole=True)."""

    kind: str
    by: str  # "human" | "ai+human:<cap>" — the noder + the capability under which it was noded
    claim: str  # Claim: what it asserts. Hole: the context/question.
    on: tuple[str, ...] = ()  # base CIDs — dependency edges; base-first means these must already exist
    needs: frozenset[str] = frozenset()  # capabilities this capsule requires
    grants: frozenset[str] = frozenset()  # capabilities it makes available to capsules that build on it
    params: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # name -> (value, min, max)
    is_hole: bool = False

    def canonical_bytes(self) -> bytes:
        """Deterministic encoding over the semantic fields (CID is derived, never an input). SPEC §3.1:
        own the ordering before hashing. Sorted keys + compact separators = byte-identical for equal meaning."""
        body = {
            "kind": self.kind,
            "by": self.by,
            "claim": self.claim,
            "on": list(self.on),
            "needs": sorted(self.needs),
            "grants": sorted(self.grants),
            "params": {k: list(v) for k, v in sorted(self.params.items())},
            "is_hole": self.is_hole,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def cid(self) -> str:
        return "b2:" + hashlib.blake2b(self.canonical_bytes(), digest_size=16).hexdigest()


class TxState(str, Enum):
    PENDING = "pending"  # rejectable (SPEC §14)
    COMMITTED = "committed"  # window elapsed; "cannot just reject" — restructure via new relations only
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""
    requires_confirm: bool = False  # SPEC §8: effectful kinds route to human even when the click passes


@dataclass
class _Entry:
    capsule: Capsule
    state: TxState
    deadline: float  # `now + window` at propose time; >= this => committed


class Fabric:
    """Content-addressed append-only store + the pending->committed transaction ledger (the time-machine)."""

    def __init__(self) -> None:
        self._by_cid: dict[str, _Entry] = {}
        self.log: list[tuple[str, str]] = []  # append-only (event, cid)

    # --- §4 THE CLICK — decidable, pure, 0-AI. A capsule attaches IFF this returns ok. ---
    def click(self, c: Capsule) -> Verdict:
        # A Hole always records validly (it asserts nothing executable) -> it is an OPEN ticket (SPEC §9).
        if c.is_hole:
            return Verdict(ok=True, reason="hole recorded (open ticket)")

        # (1) kind in closed vocabulary (enum membership)
        if c.kind not in KINDS:
            return Verdict(False, f"unknown kind '{c.kind}' (not in closed vocabulary)")

        # (2) base-first: every dependency must already be a committed-or-pending capsule in the fabric.
        #     Rejects dangling/forward edges = WASM structured-CFG discipline. No node above un-noded base.
        for base in c.on:
            entry = self._by_cid.get(base)
            if entry is None:
                return Verdict(False, f"base '{base}' not noded (base-first violation)")
            if entry.state is TxState.SUPERSEDED:
                return Verdict(False, f"base '{base}' is superseded (stranded base)")

        # (3) capability subset up the DAG: needs ⊆ (union of base grants) ∪ (grant carried by `by`).
        #     Least-privilege as a graph property — a capsule cannot claim authority its base did not carry.
        lineage: set[str] = set()
        for base in c.on:
            lineage |= set(self._by_cid[base].capsule.grants)
        if c.by.startswith("ai+human:"):
            lineage.add(c.by.split(":", 1)[1])  # the capability the human granted for this noding
        missing = set(c.needs) - lineage
        if missing:
            return Verdict(False, f"capability not in lineage: {sorted(missing)}")

        # (4) interval bounds: every parameter value within [min, max] (ADR-063 mathematical bounding).
        for name, (val, lo, hi) in c.params.items():
            if not (lo <= val <= hi):
                return Verdict(False, f"param '{name}'={val} out of [{lo},{hi}]")

        return Verdict(ok=True, requires_confirm=c.kind in EFFECTFUL)

    # --- §14 transaction: propose (PENDING) -> commit window -> COMMITTED ---
    def propose(self, c: Capsule, now: float, window: float) -> tuple[Optional[str], Verdict]:
        v = self.click(c)
        if not v.ok:
            return None, v
        cid = c.cid()
        self._by_cid[cid] = _Entry(c, TxState.PENDING, deadline=now + window)
        self.log.append(("propose", cid))
        return cid, v

    def status(self, cid: str, now: float) -> Optional[TxState]:
        e = self._by_cid.get(cid)
        if e is None:
            return None
        if e.state is TxState.PENDING and now >= e.deadline:
            return TxState.COMMITTED  # window elapsed -> committed (derived, not a background job)
        return e.state

    def revert(self, cid: str, now: float) -> Verdict:
        """Pre-commit only: a PENDING capsule whose window has not elapsed can be rejected freely (§14).
        Once COMMITTED, 'cannot just reject' — caller must restructure via new relations / supersede."""
        e = self._by_cid.get(cid)
        if e is None:
            return Verdict(False, "no such capsule")
        if self.status(cid, now) is not TxState.PENDING:
            return Verdict(False, "committed: cannot just reject — restructure via new relations / sup")
        del self._by_cid[cid]
        self.log.append(("revert", cid))
        return Verdict(ok=True)

    def supersede(self, cid: str, new: Capsule, now: float, window: float) -> tuple[Optional[str], Verdict]:
        """The post-commit change path: append a replacement, mark the old superseded (never delete)."""
        if cid not in self._by_cid:
            return None, Verdict(False, "no such capsule")
        new_cid, v = self.propose(new, now, window)
        if not v.ok:
            return None, v
        self._by_cid[cid].state = TxState.SUPERSEDED
        self.log.append(("supersede", cid))
        return new_cid, v


# --- §1/§ gauges: a gauge is a STRICTLY math/stat pure fold over the fabric, parameterized by the end
# user, whose output is a UNIQUE ACTIONABLE NEXT STEP (Director 2026-06-06). 0-AI. Example gauges below. ---

def gauge_open_holes(fabric: Fabric, end_user: str = "designer") -> dict:
    """Count open holes (= open tickets) and emit the single most actionable next step."""
    holes = [e.capsule for e in fabric._by_cid.values() if e.capsule.is_hole]
    if not holes:
        return {"gauge": "open_holes", "metric": 0, "next_step": "no open holes — fabric is fully noded"}
    target = sorted(holes, key=lambda h: h.cid())[0]  # deterministic pick (not AI judgment)
    return {
        "gauge": "open_holes",
        "metric": len(holes),
        "next_step": f"node the hole: {target.claim!r}",
        "for": end_user,
    }


def gauge_pending_ratio(fabric: Fabric, now: float, end_user: str = "designer") -> dict:
    """Fraction of capsules still PENDING (uncommitted). High ratio => decide before building further."""
    states = [fabric.status(cid, now) for cid in fabric._by_cid]
    total = sum(1 for s in states if s is not TxState.SUPERSEDED) or 1
    pending = sum(1 for s in states if s is TxState.PENDING)
    ratio = pending / total
    step = "review pending changes before extending" if ratio > 0.5 else "safe to build on committed base"
    return {"gauge": "pending_ratio", "metric": round(ratio, 3), "next_step": step, "for": end_user}


if __name__ == "__main__":  # tiny human-legible demo (SPEC §7 human surface)
    fab = Fabric()
    cust, _ = fab.propose(Capsule("entity", "human", "party being billed", grants=frozenset({"read"})), now=0, window=10)
    assert cust is not None
    pm, _ = fab.propose(
        Capsule("entity", "ai+human:design", "tokenized card", on=(cust,),
                needs=frozenset({"read"}), grants=frozenset({"read"})), now=0, window=10)
    assert pm is not None
    fab.propose(Capsule("constraint", "ai+human:design", "what happens on dispute?", on=(pm,), is_hole=True), now=0, window=10)
    print(gauge_open_holes(fab))
    print(gauge_pending_ratio(fab, now=0))
