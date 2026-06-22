"""lgwks_chain — the one canonical JSONL hash-chain link discipline (#298).

Three logs (cognition, memory, cycle) each re-rolled the same append-only
hash-chain control flow *slightly differently* — and cycle's write path lacked
the exclusive lock + verify-before-append that the others had, a latent
corruption surface under concurrent writes. That "slightly different = the bug"
drift is what this consolidates.

What this owns (the genuinely shared atom — the part where the concurrency and
crash-safety bugs live): open `a+`, take an exclusive `fcntl` lock, read the
existing chain, **verify it and refuse to extend a broken chain**, compute the
next `seq`/`prev` linkage, write one atomic JSON line, flush + fsync.

What each store injects (the parts that legitimately differ, so the on-disk
bytes are byte-for-byte unchanged — no data migration, existing `.jsonl` chains
still verify):
  - `build_core(n_existing, prev, kind, data) -> dict` — the record body and its
    field names/order/seq-base (cognition is 0-based, memory 1-based, etc.).
  - `hash_core(core, prev, key) -> str` — the per-store hash construction
    (`digest(core)` vs `mac(core+prev)` vs `mac(canon(core))`). The only required
    injection: it defines the chain's integrity and is shared by verify + append.
  - `build_core(n_existing, prev, kind, data) -> dict` + `serialize(rec) -> str` —
    the record body / field-order / seq-base and the `json.dumps` flavour. Required
    only to `append`; a **verify-only** log (e.g. `lgwks_cycle`, whose chain is
    batch-built and overwritten elsewhere, not incrementally appended) omits both.
  - optional `sign(hash, key) -> str` written to `sign_field` (cognition's
    separate signature; memory folds the MAC into the hash and passes None).
    When given, the signature is emitted on every record (the callable decides
    what an absent key means — e.g. cognition writes "" when unkeyed).
  - optional `verify_record(rec, index, prev) -> bool` — a per-record predicate
    for store-specific invariants the generic walk doesn't cover (e.g.
    cognition's `seq == line_index` and its separate-signature check). The
    generic checks (kind / prev-linkage / hash recompute) always run first.

stdlib + sibling lgwks_* only.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

GENESIS = "0" * 64


class BrokenChainError(ValueError):
    """Raised when an append would extend a chain that fails verification."""


class HashChainLog:
    def __init__(
        self,
        path: str | Path,
        *,
        key: bytes | None,
        hash_core: Callable[[dict, str, Optional[bytes]], str],
        build_core: Optional[Callable[[int, str, str, dict], dict]] = None,
        serialize: Optional[Callable[[dict], str]] = None,
        kinds: Optional[set[str]] = None,
        sign: Optional[Callable[[str, Optional[bytes]], str]] = None,
        verify_record: Optional[Callable[[dict, int, str], bool]] = None,
        hash_field: str = "hash",
        sign_field: str = "sig",
    ) -> None:
        self._path = Path(path)
        self._key = key
        self._build_core = build_core
        self._hash_core = hash_core
        self._serialize = serialize
        self._kinds = kinds
        self._sign = sign
        self._verify_record = verify_record
        self._hash_field = hash_field
        self._sign_field = sign_field

    # -- internals ------------------------------------------------------
    def _strip(self, rec: dict) -> dict:
        """The hashed core = the record minus the fields added after hashing."""
        return {k: v for k, v in rec.items() if k not in (self._hash_field, self._sign_field)}

    def _walk(self, rows: list[dict]) -> tuple[bool, str, str]:
        """The one link-walk. Returns (ok, head_hash, error). error in
        {'', 'bad-kind', 'bad-link', 'bad-hash', 'bad-record'}."""
        prev = GENESIS
        for index, rec in enumerate(rows):
            if self._kinds is not None and rec.get("kind") not in self._kinds:
                return False, prev, "bad-kind"
            if rec.get("prev") != prev:
                return False, prev, "bad-link"
            core = self._strip(rec)
            if self._hash_core(core, prev, self._key) != rec.get(self._hash_field):
                return False, prev, "bad-hash"
            if self._verify_record is not None and not self._verify_record(rec, index, prev):
                return False, prev, "bad-record"
            prev = rec[self._hash_field]  # non-None: the hash check above passed
        return True, prev, ""

    def _verify_rows(self, rows: list[dict]) -> bool:
        return self._walk(rows)[0]

    def read(self) -> list[dict]:
        if not self._path.exists():
            return []
        out: list[dict] = []
        with self._path.open("r", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
            try:
                for line in fh:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return out

    def verify(self) -> bool:
        if not self._path.exists():
            return True
        try:
            return self._verify_rows(self.read())
        except (json.JSONDecodeError, KeyError, OSError):
            return False

    def scan(self) -> dict:
        """Structured sibling of verify() for callers that need a rich audit
        result (count / head / error), e.g. lgwks_cycle.verify_cycles. Never
        raises: a read/parse failure maps to ok=False, error='read-error'."""
        if not self._path.exists():
            return {"ok": True, "count": 0, "head": GENESIS, "error": ""}
        try:
            rows = self.read()
        except (json.JSONDecodeError, KeyError, OSError):
            return {"ok": False, "count": 0, "head": GENESIS, "error": "read-error"}
        ok, head, error = self._walk(rows)
        return {"ok": ok, "count": len(rows), "head": head, "error": error}

    # -- the canonical append control flow ------------------------------
    def append(self, kind: str, data: dict) -> dict:
        """Append one chained entry under an exclusive lock; refuse a broken chain."""
        if self._build_core is None or self._serialize is None:
            raise TypeError("verify-only HashChainLog: no build_core/serialize to append with")
        build_core, serialize = self._build_core, self._serialize
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.seek(0)
                rows: list[dict] = []
                for line in fh.read().splitlines():
                    if line.strip():
                        rows.append(json.loads(line))

                if rows:
                    if not self._verify_rows(rows):
                        raise BrokenChainError(
                            f"refusing to append to broken chain: {self._path}"
                        )
                    prev = rows[-1][self._hash_field]
                else:
                    prev = GENESIS

                core = build_core(len(rows), prev, kind, data)
                h = self._hash_core(core, prev, self._key)
                rec: dict[str, Any] = {**core, self._hash_field: h}
                if self._sign is not None:
                    rec[self._sign_field] = self._sign(h, self._key)

                fh.seek(0, 2)  # EOF
                fh.write(serialize(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                return rec
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
