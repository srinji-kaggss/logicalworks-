"""
The fabric — immutable content-addressed DAG + hash-chained append-only log + the pending→committed
transaction. The git/Google-Drive model (SPEC §14): objects are permanent and addressed by CID; "change"
appends a new version; refs/checkouts move, objects never die.

In-memory by design: persistence is a CONSUMER concern (the CLI, next session). Keeping the fabric in
memory preserves the package's independence. stdlib-only; imports only sibling capsule/cid/verify.

Hardening (every item maps to an AUDIT finding):
  - F-01: objects are keyed ONLY by their own CID (`put` recomputes; mismatch is impossible by construction).
  - F-04: time is a MONOTONIC logical clock internal to the fabric (number of ops); callers cannot supply or
    rewind `now`. Commit windows are in ticks and must be ≥ 1. COMMITTED is monotone — it cannot un-happen.
  - F-06: NOTHING is ever deleted. Pre-commit "abandon" drops a capsule from the working checkout; the
    immutable object remains resolvable forever, so dependents are never stranded.
  - F-07: `supersede` stores+verifies the replacement first; because objects are immutable and base-first is
    existence, the superseded base still resolves → the fabric replays consistently.
  - hash-chained log: tag_n = cid(tag_{n-1} || event || cid) → tamper-evident history (the time-machine).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .capsule import Capsule
from .cid import CidError, compute_cid, require_cid
from .verify import Verdict, verify


class TxState(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class LogEntry:
    seq: int
    event: str
    cid: str
    chain_tag: str  # cid(prev_tag || event || cid) — append-only integrity


class FabricError(ValueError):
    pass


class Fabric:
    def __init__(self, trusted_key: Optional[bytes] = None) -> None:
        self._objects: dict[str, Capsule] = {}      # immutable: cid -> capsule, NEVER deleted (F-06)
        self._commit_at: dict[str, int] = {}         # cid -> logical tick at which it becomes COMMITTED
        self._superseded: set[str] = set()           # ref-level marker; object still resolves (F-06)
        self._checkout: set[str] = set()             # the working set (abandon drops from here, not objects)
        self._clock: int = 0                          # monotonic logical time (F-04)
        self.log: list[LogEntry] = []
        self._trusted_key = trusted_key

    # --- time: monotonic, internal, forward-only (F-04) ---
    def tick(self, n: int = 1) -> int:
        if n < 1:
            raise FabricError("tick must advance by >= 1 (time is monotonic)")
        self._clock += n
        return self._clock

    @property
    def now(self) -> int:
        return self._clock

    # --- immutable resolve: an object, once stored, always resolves (even if superseded) ---
    def resolve(self, cid: str) -> Optional[Capsule]:
        capsule = self._objects.get(cid)
        if capsule is None:
            return None
        try:
            require_cid(capsule.to_bytes(), cid)
        except CidError:
            return None
        return capsule

    def _append_log(self, event: str, cid: str) -> None:
        prev = self.log[-1].chain_tag if self.log else ""
        seq = len(self.log)
        tag = compute_cid(f"{prev}\n{seq}\n{event}\n{cid}".encode("utf-8"))
        self.log.append(LogEntry(seq, event, cid, tag))

    # --- propose: verify (the click) → store immutably → PENDING with a commit window in ticks ---
    def propose(self, capsule: Capsule, window: int = 1) -> tuple[Optional[str], Verdict]:
        if window < 1:
            return None, Verdict(False, "commit window must be >= 1 tick (AUDIT F-04)")
        v = verify(capsule, self.resolve, self._trusted_key)
        if not v.ok:
            return None, v
        cid = capsule.cid()
        if cid not in self._objects:                  # idempotent; keyed only by content (F-01)
            self._objects[cid] = capsule
            self._append_log("propose", cid)
        self._commit_at[cid] = self._clock + window
        self._checkout.add(cid)
        self.tick()                                    # an op advances logical time
        return cid, v

    def status(self, cid: str) -> Optional[TxState]:
        if self.resolve(cid) is None:
            return None
        if cid in self._superseded:
            return TxState.SUPERSEDED
        if cid in self._checkout and self._clock < self._commit_at.get(cid, 0):
            return TxState.PENDING
        return TxState.COMMITTED

    def abandon(self, cid: str) -> Verdict:
        """Pre-commit only: drop from the working checkout. The immutable object is NOT deleted (F-06),
        so any dependent pinned to its CID stays valid."""
        if self.status(cid) is not TxState.PENDING:
            return Verdict(False, "not pending: committed history changes only via supersede (F-06)")
        self._checkout.discard(cid)
        self._append_log("abandon", cid)
        return Verdict(ok=True)

    def supersede(self, old_cid: str, new_capsule: Capsule, window: int = 1) -> tuple[Optional[str], Verdict]:
        if self.resolve(old_cid) is None:
            return None, Verdict(False, "no such capsule to supersede")
        new_cid, v = self.propose(new_capsule, window)   # store+verify replacement FIRST (F-07)
        if not v.ok:
            return None, v
        self._superseded.add(old_cid)                     # ref-level; old object still resolves
        self._append_log("supersede", old_cid)
        return new_cid, v

    # --- integrity: recompute the chain; any tamper breaks it ---
    def verify_chain(self) -> bool:
        prev = ""
        for expected_seq, entry in enumerate(self.log):
            if entry.seq != expected_seq:
                return False
            if self.resolve(entry.cid) is None:
                return False
            tag = compute_cid(f"{prev}\n{entry.seq}\n{entry.event}\n{entry.cid}".encode("utf-8"))
            if tag != entry.chain_tag:
                return False
            prev = tag
        return True
