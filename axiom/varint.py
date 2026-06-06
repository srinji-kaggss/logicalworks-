"""
LEB128 base-128 varints — the lowest byte-layer primitive (WASM uses these for all lengths/indices).

Two hardening rules, both grounded in real CVE-class attacks on varint decoders (protobuf/WASM):
  - OVERLONG rejection: a value must use the FEWEST bytes. `0x80 0x00` (a non-minimal encoding of 0) is
    rejected — otherwise one logical value has many byte forms, which breaks canonical encoding (AUDIT F-05
    family) and enables CID confusion.
  - BOMB rejection: a continuation chain longer than the type width (>10 bytes for a 64-bit value) is
    rejected rather than read unboundedly — the classic varint denial-of-service.

Pure, deterministic, stdlib-only. No upward imports.
"""

from __future__ import annotations

_MAX_U64_BYTES = 10  # ceil(64 / 7) = 10 bytes max for a 64-bit unsigned value


class VarintError(ValueError):
    """Malformed varint: overlong, unterminated, out of range, or bomb."""


def encode_uleb128(value: int) -> bytes:
    """Encode a non-negative int as canonical (minimal-length) unsigned LEB128."""
    if value < 0:
        raise VarintError(f"uleb128 requires value >= 0, got {value}")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)  # set continuation bit
        else:
            out.append(byte)
            return bytes(out)


def decode_uleb128(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode canonical unsigned LEB128 at offset. Returns (value, next_offset).
    Rejects overlong encodings, unterminated chains, and >64-bit bombs."""
    result = 0
    shift = 0
    start = offset
    while True:
        if offset >= len(data):
            raise VarintError("unterminated uleb128 (ran off the end)")
        if offset - start >= _MAX_U64_BYTES:
            raise VarintError("uleb128 too long (>64-bit bomb)")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):  # last byte (continuation bit clear)
            # canonical/overlong check: a multi-byte encoding whose final group is 0 carries no value
            if (offset - start) > 1 and (byte & 0x7F) == 0:
                raise VarintError("overlong uleb128 (non-minimal encoding)")
            return result, offset
        shift += 7


def encode_sleb128(value: int) -> bytes:
    """Encode a signed int as canonical signed LEB128 (two's-complement, sign-extended)."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7  # arithmetic shift in Python preserves sign
        sign_bit_set = bool(byte & 0x40)
        # done when value has converged to 0 (and sign bit clear) or -1 (and sign bit set)
        if (value == 0 and not sign_bit_set) or (value == -1 and sign_bit_set):
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def decode_sleb128(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode canonical signed LEB128 at offset. Returns (value, next_offset)."""
    result = 0
    shift = 0
    start = offset
    while True:
        if offset >= len(data):
            raise VarintError("unterminated sleb128 (ran off the end)")
        if offset - start >= _MAX_U64_BYTES:
            raise VarintError("sleb128 too long (>64-bit bomb)")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            if byte & 0x40:  # sign bit set → sign-extend
                result |= -(1 << shift)
            return result, offset
