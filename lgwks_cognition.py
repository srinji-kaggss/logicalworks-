"""
lgwks_cognition — the COGNITION-LOG store (build #2, z4 core).

Append-only, HMAC hash-chained record of AI thinking + intent-commits. Two roles in one structure:
  1. SOC2 audit trail — every reasoning step / refinement is logged, chained, tamper-evident (a rewrite
     breaks the chain; with a keyed signer via lgwks_sign it is unforgeable, not just checksum).
  2. The Machine's TRAINING CORPUS — the distillation flywheel reads intent-commit chains back from here
     to teach the Tier-E Machine (SPEC-lgwks-experience §1). The log IS the corpus.

Boundary (T0): holds AI cognition + intent STRUCTURE (prompts, gaps, ideas, why) — NOT raw user PII
(that is lgwks_vault) and NOT fetched world data (that is lgwks_cache). Kinds: thought · intent_commit ·
alignment · gate · note · promotion (the audited tenant→world cross-tier write, L5 of #89; see
lgwks_promote). Each entry chains on the previous hash; the chain head proves the whole history.
"""

from __future__ import annotations

import fcntl
import lgwks_chain
import lgwks_hashing
import json
import time
from pathlib import Path

import lgwks_sign

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "cognition"
_GENESIS = lgwks_chain.GENESIS
_KINDS = {"thought", "intent_commit", "alignment", "gate", "note", "promotion"}
_BODY = {"seq", "ts", "kind", "data", "prev"}  # the hashed core field set
from lgwks_substrate_config import SLUG_SCRUB_RE as _STREAM_SAFE  # one source of truth


def _log_path(stream: str) -> Path:
    safe = _STREAM_SAFE.sub("-", stream.strip().lower()).strip(".-")
    if not safe:
        raise ValueError("cognition stream name cannot be empty")
    suffix = lgwks_hashing.content_id(stream, 12)
    return _DIR / f"{safe}-{suffix}.cognition.jsonl"


class CognitionLog:
    """Append-only HMAC-chained cognition stream. One stream per logical context (default 'main').
    tamper-EVIDENT: rewriting any past entry breaks every subsequent hash (and signature, if keyed)."""

    def __init__(self, stream: str = "main", key: bytes | None = None) -> None:
        self.stream = stream
        self._path = _log_path(stream)
        self._key, self._mode = (key, "provided") if key is not None else lgwks_sign.signing_key()

        def build_core(n_existing: int, prev: str, kind: str, data: dict) -> dict:
            # cognition seq is 0-based (first record seq == 0).
            return {"seq": n_existing, "ts": time.time(), "kind": kind, "data": data, "prev": prev}

        def hash_core(core: dict, prev: str, k: bytes | None) -> str:
            # hash = digest(core); prev is already inside core, key is not folded in here.
            return lgwks_hashing.digest(json.dumps(core, sort_keys=True, separators=(",", ":")))

        def sign(h: str, k: bytes | None) -> str:
            # separate signature over the hash; "" when unkeyed (byte-exact with prior code).
            return lgwks_sign.mac(h, k) if k else ""

        def verify_record(rec: dict, index: int, prev: str) -> bool:
            body = {key: rec[key] for key in _BODY if key in rec}
            if set(body) != _BODY:
                return False
            if rec.get("seq") != index:  # 0-based positional seq
                return False
            sig = rec.get("sig", "")
            if self._key and sig:
                return lgwks_sign.verify(rec["hash"], sig, self._key)
            return True

        self._log = lgwks_chain.HashChainLog(
            self._path,
            key=self._key,
            build_core=build_core,
            hash_core=hash_core,
            serialize=lambda rec: json.dumps(rec, sort_keys=True),
            kinds=_KINDS,
            sign=sign,
            verify_record=verify_record,
        )

    def append(self, kind: str, data: dict) -> dict:
        """Append one chained, signed entry. kind must be known. Returns the entry.

        The exclusive lock, verify-before-append (refuse a broken chain), and atomic
        fsynced write are owned by the canonical lgwks_chain primitive (#298).
        """
        if kind not in _KINDS:
            raise ValueError(f"unknown cognition kind {kind!r}; known: {sorted(_KINDS)}")
        return self._log.append(kind, data)

    def verify(self) -> bool:
        """Verify the integrity of the entire chain."""
        return self._log.verify()

    def _read_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        out = []
        with self._path.open("r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return out

    def corpus(self, kind: str = "intent_commit") -> list[dict]:
        """Read back entries of a kind — how the distillation flywheel pulls the Machine's training data."""
        if not self.verify():
            raise ValueError(f"refusing to read corpus from broken cognition chain: {self.stream}")
        return [r["data"] for r in self._read_raw() if r.get("kind") == kind]



def status(stream: str = "main") -> dict:
    log = CognitionLog(stream)
    n = len(log._read_raw())
    return {"store": "cognition-log", "dir": str(_DIR), "stream": stream, "entries": n,
            "chain_ok": log.verify(), "integrity": log._mode}
