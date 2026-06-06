"""
Content identity (CID) — the address of a node over its CANONICAL bytes.

The CID is the identity, the dedup key, and the replay anchor (ADR-004 D3). Two hardening rules from the
audit:
  - FULL WIDTH (AUDIT F-09): 256-bit digest, never 128. A key that gates capability lineage must not sit at
    a 2^64 birthday bound.
  - VERIFY, DON'T TRUST (AUDIT F-01): `verify(bytes, cid)` is provided so every store/read can assert the
    bytes actually hash to the claimed CID. Content-addressing is only real if it is re-checked.

The CID is computed over the bytes you pass — canonicality of those bytes is the wire layer's job
(`wire.decode_canonical`). Pass non-canonical bytes and you get a different CID; that is the point.

HASH: ADR-068 canon is BLAKE3-256. Not installed here, so this uses hashlib.blake2b(digest_size=32) as a
256-bit stand-in. The prefix names the algorithm so a swap is detectable and never silently confused.
Pure, deterministic, stdlib-only.
"""

from __future__ import annotations

import hashlib

CID_ALG = "b2b256"  # blake2b-256 stand-in; swaps to "b3-256" when blake3 is wired (contract unchanged)
_DIGEST_SIZE = 32  # bytes = 256-bit (AUDIT F-09: no 128-bit)


class CidError(ValueError):
    """CID input or verification failure."""


def compute_cid(canonical_bytes: bytes) -> str:
    """Content-address of canonical bytes. Format: '<alg>:<hex>'. Deterministic, full-width."""
    if not isinstance(canonical_bytes, (bytes, bytearray)):
        raise CidError(f"CID requires bytes, got {type(canonical_bytes).__name__}")
    digest = hashlib.blake2b(bytes(canonical_bytes), digest_size=_DIGEST_SIZE).hexdigest()
    return f"{CID_ALG}:{digest}"


def verify_cid(canonical_bytes: bytes, cid: str) -> bool:
    """True iff `canonical_bytes` actually hash to `cid`. The AUDIT F-01 check: never trust a stored key —
    re-derive it. Mismatched algorithm prefix is a verification failure, not a crash."""
    try:
        return compute_cid(canonical_bytes) == cid
    except CidError:
        return False


def require_cid(canonical_bytes: bytes, cid: str) -> None:
    """Assert the bytes hash to the CID; raise CidError on mismatch. Use at every store and base read."""
    if not verify_cid(canonical_bytes, cid):
        raise CidError(f"CID mismatch: bytes do not hash to {cid}")
