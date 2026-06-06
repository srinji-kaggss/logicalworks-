"""
The Capsule — one typed, content-addressed record. Claim asserts; Hole abstains. The unit the verifier
checks and the fabric stores. Name is provisional (Director: "idk if node is correct"); the framework is
name-agnostic.

Hardening baked into encode/decode so a malformed capsule cannot even be serialized:
  - Hole carries grants=∅ and needs=∅ (AUDIT F-02 — a hole may not mint or require capability).
  - params use STRICT IEEE754: NaN and ±Inf are rejected, −0.0 is normalized to 0.0 (AUDIT F-05 — one byte
    form per value).
  - `by` is provenance only, NOT authority. Authority is the genesis signature (AUDIT F-03); the string-
    prefix self-grant is gone. `is_genesis` + `signature` carry the cryptographic root; verify.py checks them.

Canonical bytes (wire.encode) → CID. on/needs/grants are SETS (order-independent → canonical sort). params
sorted by name. Pure, deterministic, stdlib-only; imports only sibling varint/wire/cid.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from .cid import compute_cid
from .wire import LEN, VARINT, decode_canonical, encode

KINDS = frozenset(
    {"entity", "role", "state", "transition", "capability", "constraint", "effect", "evidence"}
)
EFFECTFUL = frozenset({"effect", "transition"})

# wire field numbers (closed; unknown numbers are preserved by the wire layer but ignored here)
_F_KIND, _F_CLAIM, _F_ON, _F_NEEDS, _F_GRANTS, _F_PARAMS, _F_IS_HOLE, _F_IS_GENESIS, _F_SIG, _F_BY = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10
)
# nested param field numbers
_P_NAME, _P_VAL, _P_MIN, _P_MAX = 1, 2, 3, 4


class CapsuleError(ValueError):
    """Malformed capsule (structural or encoding violation)."""


def _pack_f64(x: float) -> bytes:
    """Canonical 8-byte IEEE754: reject NaN/±Inf, normalize −0.0 → 0.0 (AUDIT F-05)."""
    f = float(x)
    if not math.isfinite(f):
        raise CapsuleError(f"non-finite param value {x!r} (NaN/Inf rejected — canonical codec)")
    if f == 0.0:
        f = 0.0  # collapse -0.0 to +0.0 (they compare equal; this picks the canonical bit pattern)
    return struct.pack(">d", f)


def _unpack_f64(b: bytes) -> float:
    if len(b) != 8:
        raise CapsuleError("param value must be 8 bytes")
    (f,) = struct.unpack(">d", b)
    if not math.isfinite(f):
        raise CapsuleError("non-finite param value decoded")
    return f


@dataclass(frozen=True)
class Capsule:
    kind: str
    claim: str
    on: tuple[str, ...] = ()            # base CIDs (dependency edges) — a set, canonical-sorted on encode
    needs: frozenset[str] = frozenset()
    grants: frozenset[str] = frozenset()
    params: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # name -> (val, lo, hi)
    is_hole: bool = False
    is_genesis: bool = False
    signature: bytes = b""              # HMAC/sig tag; verified by verify.py against the trusted key
    by: str = ""                        # provenance label only — NOT authority (AUDIT F-03)

    def validate_structure(self) -> None:
        """Structural invariants enforced before encoding. A capsule that fails here cannot be serialized."""
        if self.is_hole and (self.grants or self.needs):
            raise CapsuleError("a Hole must carry grants=∅ and needs=∅ (AUDIT F-02)")
        if self.kind == "" :
            raise CapsuleError("kind must be non-empty")

    def to_bytes(self) -> bytes:
        self.validate_structure()
        fields: list[tuple[int, int, object]] = [
            (_F_KIND, LEN, self.kind.encode("utf-8")),
            (_F_CLAIM, LEN, self.claim.encode("utf-8")),
            (_F_IS_HOLE, VARINT, 1 if self.is_hole else 0),
            (_F_IS_GENESIS, VARINT, 1 if self.is_genesis else 0),
            (_F_BY, LEN, self.by.encode("utf-8")),
        ]
        if self.signature:
            fields.append((_F_SIG, LEN, bytes(self.signature)))
        for c in self.on:
            fields.append((_F_ON, LEN, c.encode("utf-8")))
        for c in self.needs:
            fields.append((_F_NEEDS, LEN, c.encode("utf-8")))
        for c in self.grants:
            fields.append((_F_GRANTS, LEN, c.encode("utf-8")))
        for name in sorted(self.params):
            val, lo, hi = self.params[name]
            nested = encode([
                (_P_NAME, LEN, name.encode("utf-8")),
                (_P_VAL, LEN, _pack_f64(val)),
                (_P_MIN, LEN, _pack_f64(lo)),
                (_P_MAX, LEN, _pack_f64(hi)),
            ])
            fields.append((_F_PARAMS, LEN, nested))
        return encode(fields)  # wire.encode sorts canonically

    def cid(self) -> str:
        return compute_cid(self.to_bytes())

    @staticmethod
    def from_bytes(data: bytes) -> "Capsule":
        fields = decode_canonical(data)  # rejects non-canonical input (AUDIT F-05)
        kind = claim = by = ""
        on: list[str] = []
        needs: set[str] = set()
        grants: set[str] = set()
        params: dict[str, tuple[float, float, float]] = {}
        is_hole = is_genesis = False
        signature = b""
        for fno, wtype, value in fields:
            if fno == _F_KIND and wtype == LEN:
                kind = bytes(value).decode("utf-8")  # type: ignore[arg-type]
            elif fno == _F_CLAIM and wtype == LEN:
                claim = bytes(value).decode("utf-8")  # type: ignore[arg-type]
            elif fno == _F_BY and wtype == LEN:
                by = bytes(value).decode("utf-8")  # type: ignore[arg-type]
            elif fno == _F_ON and wtype == LEN:
                on.append(bytes(value).decode("utf-8"))  # type: ignore[arg-type]
            elif fno == _F_NEEDS and wtype == LEN:
                needs.add(bytes(value).decode("utf-8"))  # type: ignore[arg-type]
            elif fno == _F_GRANTS and wtype == LEN:
                grants.add(bytes(value).decode("utf-8"))  # type: ignore[arg-type]
            elif fno == _F_IS_HOLE and wtype == VARINT:
                is_hole = bool(value)
            elif fno == _F_IS_GENESIS and wtype == VARINT:
                is_genesis = bool(value)
            elif fno == _F_SIG and wtype == LEN:
                signature = bytes(value)  # type: ignore[arg-type]
            elif fno == _F_PARAMS and wtype == LEN:
                name, val, lo, hi = _decode_param(bytes(value))  # type: ignore[arg-type]
                params[name] = (val, lo, hi)
            # unknown field numbers: ignored here (wire layer kept them for canonicality/CID)
        cap = Capsule(kind, claim, tuple(on), frozenset(needs), frozenset(grants),
                      params, is_hole, is_genesis, signature, by)
        cap.validate_structure()
        return cap


def _decode_param(data: bytes) -> tuple[str, float, float, float]:
    name = ""
    val = lo = hi = None
    for fno, wtype, value in decode_canonical(data):
        if fno == _P_NAME and wtype == LEN:
            name = bytes(value).decode("utf-8")  # type: ignore[arg-type]
        elif fno == _P_VAL and wtype == LEN:
            val = _unpack_f64(bytes(value))  # type: ignore[arg-type]
        elif fno == _P_MIN and wtype == LEN:
            lo = _unpack_f64(bytes(value))  # type: ignore[arg-type]
        elif fno == _P_MAX and wtype == LEN:
            hi = _unpack_f64(bytes(value))  # type: ignore[arg-type]
    if name == "" or val is None or lo is None or hi is None:
        raise CapsuleError("incomplete param (name/val/min/max required)")
    return name, val, lo, hi
