"""
lgwks_cognition — the COGNITION-LOG store (build #2, z4 core).

Append-only, HMAC hash-chained record of AI thinking + intent-commits. Two roles in one structure:
  1. SOC2 audit trail — every reasoning step / refinement is logged, chained, tamper-evident (a rewrite
     breaks the chain; with a keyed signer via lgwks_sign it is unforgeable, not just checksum).
  2. The Machine's TRAINING CORPUS — the distillation flywheel reads intent-commit chains back from here
     to teach the Tier-E Machine (SPEC-lgwks-experience §1). The log IS the corpus.

Boundary (T0): holds AI cognition + intent STRUCTURE (prompts, gaps, ideas, why) — NOT raw user PII
(that is lgwks_vault) and NOT fetched world data (that is lgwks_cache). Kinds: thought · intent_commit ·
alignment · gate. Each entry chains on the previous hash; the chain head proves the whole history.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import lgwks_sign

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "cognition"
_GENESIS = "0" * 64
_KINDS = {"thought", "intent_commit", "alignment", "gate", "note"}
_STREAM_SAFE = re.compile(r"[^a-z0-9._-]+")


def _log_path(stream: str) -> Path:
    safe = _STREAM_SAFE.sub("-", stream.strip().lower()).strip(".-")
    if not safe:
        raise ValueError("cognition stream name cannot be empty")
    suffix = hashlib.sha256(stream.encode("utf-8")).hexdigest()[:12]
    return _DIR / f"{safe}-{suffix}.cognition.jsonl"


class CognitionLog:
    """Append-only HMAC-chained cognition stream. One stream per logical context (default 'main').
    tamper-EVIDENT: rewriting any past entry breaks every subsequent hash (and signature, if keyed)."""

    def __init__(self, stream: str = "main", key: bytes | None = None) -> None:
        self.stream = stream
        self._path = _log_path(stream)
        self._key, self._mode = (key, "provided") if key is not None else lgwks_sign.signing_key()
        self._prev = self._tail_hash()

    def _tail_hash(self) -> str:
        """Recover the chain head from disk so a new process continues the same chain."""
        if not self._path.exists():
            return _GENESIS
        last = _GENESIS
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)["hash"]
            except (json.JSONDecodeError, KeyError):
                continue
        return last

    def append(self, kind: str, data: dict) -> dict:
        """Append one chained, signed entry. kind must be known (no silent free-form). Returns the entry."""
        if kind not in _KINDS:
            raise ValueError(f"unknown cognition kind {kind!r}; known: {sorted(_KINDS)}")
        if self._path.exists() and not self.verify():
            raise ValueError(f"refusing to append to broken cognition chain: {self.stream}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"seq": self._next_seq(), "ts": time.time(), "kind": kind, "data": data, "prev": self._prev}
        core = json.dumps(rec, sort_keys=True, separators=(",", ":"))
        rec["hash"] = hashlib.sha256(core.encode("utf-8")).hexdigest()
        rec["sig"] = lgwks_sign.mac(rec["hash"], self._key) if self._key else ""
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self._prev = rec["hash"]
        return rec

    def _next_seq(self) -> int:
        return len(self._read_raw())

    def _read_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        out = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def verify(self) -> bool:
        """Re-walk the chain: each entry's hash recomputes and its prev matches the predecessor. With a
        keyed signer, also verify the HMAC. Any break ⇒ False (tamper / corruption)."""
        prev = _GENESIS
        if not self._path.exists():
            return True
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False
            body = {k: rec[k] for k in ("seq", "ts", "kind", "data", "prev") if k in rec}
            if set(body) != {"seq", "ts", "kind", "data", "prev"}:
                return False
            if rec.get("kind") not in _KINDS:
                return False
            core = json.dumps(body, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(core.encode("utf-8")).hexdigest() != rec.get("hash"):
                return False
            if rec.get("prev") != prev:
                return False
            if self._key and rec.get("sig") and not lgwks_sign.verify(rec["hash"], rec["sig"], self._key):
                return False
            prev = rec["hash"]
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
