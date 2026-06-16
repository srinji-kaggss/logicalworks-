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
import hashlib
import lgwks_hashing
import json
import os
import time
from pathlib import Path

import lgwks_sign

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "cognition"
_GENESIS = "0" * 64
_KINDS = {"thought", "intent_commit", "alignment", "gate", "note", "promotion"}
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

    def _tail_hash(self) -> str:
        """Recover the chain head from disk so a new process continues the same chain."""
        if not self._path.exists():
            return _GENESIS
        last = _GENESIS
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)["hash"]
                except (json.JSONDecodeError, KeyError):
                    continue
        return last

    def append(self, kind: str, data: dict) -> dict:
        """Append one chained, signed entry. kind must be known. Returns the entry."""
        if kind not in _KINDS:
            raise ValueError(f"unknown cognition kind {kind!r}; known: {sorted(_KINDS)}")
        
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure file exists for locking
        self._path.touch(exist_ok=True)
        
        with self._path.open("a+", encoding="utf-8") as f:
            # Advisory lock (exclusive, blocking)
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # 1. Verify chain head under lock
                if not self.verify_under_lock(f):
                    raise ValueError(f"refusing to append to broken cognition chain: {self.stream}")
                
                # 2. Get current head and sequence
                f.seek(0)
                lines = f.readlines()
                seq = len(lines)
                prev = _GENESIS
                if lines:
                    try:
                        prev = json.loads(lines[-1])["hash"]
                    except (json.JSONDecodeError, KeyError):
                        pass

                # 3. Build record
                rec = {"seq": seq, "ts": time.time(), "kind": kind, "data": data, "prev": prev}
                core = json.dumps(rec, sort_keys=True, separators=(",", ":"))
                rec["hash"] = hashlib.sha256(core.encode("utf-8")).hexdigest()
                rec["sig"] = lgwks_sign.mac(rec["hash"], self._key) if self._key else ""
                
                # 4. Write
                f.seek(0, 2) # seek to end
                f.write(json.dumps(rec, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
                return rec
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

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

    def verify(self) -> bool:
        """Verify the integrity of the entire chain."""
        if not self._path.exists():
            return True
        with self._path.open("r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return self.verify_under_lock(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def verify_under_lock(self, f) -> bool:
        """Internal verify logic assuming file is already locked."""
        f.seek(0)
        prev_hash = _GENESIS
        for i, line in enumerate(f):
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                actual_hash = rec.pop("hash")
                sig = rec.pop("sig", "")
                
                # Verify body fields match core set
                body = {k: rec[k] for k in ("seq", "ts", "kind", "data", "prev") if k in rec}
                if set(body) != {"seq", "ts", "kind", "data", "prev"}:
                    return False

                # 1. Verify sequence
                if rec["seq"] != i: return False
                
                # 2. Verify link
                if rec["prev"] != prev_hash: return False
                
                # 3. Verify hash
                core = json.dumps(body, sort_keys=True, separators=(",", ":"))
                expected_hash = hashlib.sha256(core.encode("utf-8")).hexdigest()
                if actual_hash != expected_hash: return False
                
                # 4. Verify signature (if keyed)
                if self._key and sig:
                    if not lgwks_sign.verify(actual_hash, sig, self._key):
                        return False
                
                prev_hash = actual_hash
            except (json.JSONDecodeError, KeyError):
                return False
        return True

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
