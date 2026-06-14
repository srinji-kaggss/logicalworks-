"""lgwks_hashing — the single source of truth for content hashing.

One file defines what a content-id *is*. Every module imports from here instead of
re-deriving `hashlib.sha256(...).hexdigest()[:n]` locally. That re-derivation was the
C-10 "cid-consistency" drift: the same primitive was copy-pasted ~15× with divergent
truncation (12 / 16 / full-64), divergent error modes (ignore / replace / strict), and
two outright different algorithms (blake2b, canonical-JSON sha) — so there was no one
place that said what a content address means.

Primitives (pick by intent, not by copy-paste):

  content_id(text, n=16)  Truncated SHA-256 hex. For content-addressing keys/ids where a
                          short stable handle suffices. `n` is the *store's* width — a
                          store may legitimately use 12 or 16; the drift was re-deriving
                          the primitive, not choosing a width. Pass `n` explicitly when
                          it is not the 16-char default.
  digest(text)            Full 64-char SHA-256 hex. For integrity / audit-chain / cache
                          keys — NEVER truncate these; the collision headroom is the point.
  digest_bytes(data)      Full SHA-256 hex over raw bytes (e.g. file/blob caches).
  digest_file(path)       Streamed full SHA-256 hex of a file's bytes (constant memory).
  canonical_id(obj)       digest() over canonical JSON (sorted keys, compact separators) —
                          a stable id for a structured object regardless of key order or
                          whitespace.
  blake_id(text, size=16) BLAKE2b hex. A deliberately different algorithm kept here so that
                          ALL hashing lives in one file; used where a non-SHA digest is wanted.

Error mode: all *text* hashing decodes UTF-8 with errors="ignore" (lossy-but-total — a
content address must never raise on a stray lone surrogate). Inputs are already-decoded
`str`, so this differs from strict/replace mode only on pathological lone-surrogate input,
never on real corpus text. Standardizing the mode here is part of "one source of truth".

//why no class/registry: these are pure functions over (text|bytes|obj)->hex. A module of
free functions IS the single source; anything heavier would be ceremony.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = [
    "content_id",
    "digest",
    "digest_bytes",
    "digest_file",
    "canonical_id",
    "blake_id",
]

# Streamed-read buffer for digest_file; 64 KiB balances syscalls vs memory.
_FILE_BUFSIZE = 65536


def content_id(text: str, n: int = 16) -> str:
    """Truncated SHA-256 hex content id. `n` = store width (default 16)."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def digest(text: str) -> str:
    """Full 64-char SHA-256 hex — integrity/audit/cache keys; do not truncate."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def digest_bytes(data: bytes) -> str:
    """Full 64-char SHA-256 hex over raw bytes."""
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path | str) -> str:
    """Full 64-char SHA-256 hex of a file's bytes, read in constant memory."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_FILE_BUFSIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_id(obj: Any) -> str:
    """Full SHA-256 hex over canonical JSON (sorted keys, compact) — order-stable id."""
    return digest(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def blake_id(text: str, size: int = 16) -> str:
    """BLAKE2b hex (digest_size bytes -> 2*size hex chars). Non-SHA digest."""
    return hashlib.blake2b(text.encode("utf-8", errors="ignore"), digest_size=size).hexdigest()
