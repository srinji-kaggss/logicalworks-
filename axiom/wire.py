"""
Canonical TLV wire — tag-length-value over LEB128 (the WASM section / protobuf TLV shape, but we OWN the
canonicality the canon does not provide; see ADR-004 D3, translation-chain §3.1).

A message is a sequence of fields: tag = uleb128((field_no << 3) | wire_type), then the value.
Two wire types only (enough for the capsule): VARINT (0) for ints/bools, LEN (2) for bytes/strings/nested.

CANONICALITY (the AUDIT F-05 fix) is enforced HARD: there is exactly one byte form per message. The encoder
emits fields sorted by (field_no, value); `decode_canonical` rejects any input that is not byte-identical to
the re-encoding of what it decoded. So a hostile non-canonical variant of a logical message cannot be hashed
(no CID confusion). Unknown field NUMBERS are preserved (not dropped) so canonicality round-trips and the CID
covers them; interpretation of which fields are known happens one layer up (capsule.py). Unknown wire TYPES
are rejected as malformed.

Pure, deterministic, stdlib-only. Imports only the sibling varint primitive.
"""

from __future__ import annotations

from .varint import decode_uleb128, encode_uleb128, VarintError

VARINT = 0
LEN = 2
_WIRE_TYPES = (VARINT, LEN)


class WireError(ValueError):
    """Malformed or non-canonical wire bytes."""


# A field is (field_no:int, wire_type:int, value). value is int for VARINT, bytes for LEN.
Field = tuple[int, int, object]


def _field_sort_key(f: Field) -> tuple[int, int, bytes]:
    field_no, wire_type, value = f
    # within a field number, order VARINT by numeric value, LEN by raw bytes — total, deterministic order
    if wire_type == VARINT:
        return (field_no, 0, encode_uleb128(int(value)))  # type: ignore[arg-type]
    return (field_no, 1, bytes(value))  # type: ignore[arg-type]


def encode(fields: list[Field]) -> bytes:
    """Encode fields into canonical TLV bytes: sorted by (field_no, value), minimal varints."""
    out = bytearray()
    for field_no, wire_type, value in sorted(fields, key=_field_sort_key):
        if field_no < 0:
            raise WireError(f"negative field number {field_no}")
        if wire_type not in _WIRE_TYPES:
            raise WireError(f"unknown wire type {wire_type}")
        out += encode_uleb128((field_no << 3) | wire_type)
        if wire_type == VARINT:
            if not isinstance(value, int) or value < 0:
                raise WireError(f"VARINT field {field_no} needs a non-negative int, got {value!r}")
            out += encode_uleb128(value)
        else:  # LEN
            if not isinstance(value, (bytes, bytearray)):
                raise WireError(f"LEN field {field_no} needs bytes, got {type(value).__name__}")
            out += encode_uleb128(len(value))
            out += bytes(value)
    return bytes(out)


def decode(data: bytes) -> list[Field]:
    """Decode TLV bytes into fields (ALL fields, known or not, in stream order). Structural validation only;
    canonicality is checked by decode_canonical. Rejects unknown wire types, truncation, bad lengths."""
    fields: list[Field] = []
    offset = 0
    n = len(data)
    while offset < n:
        try:
            tag, offset = decode_uleb128(data, offset)
        except VarintError as e:
            raise WireError(f"bad tag varint: {e}") from e
        field_no = tag >> 3
        wire_type = tag & 0x7
        if wire_type not in _WIRE_TYPES:
            raise WireError(f"unknown wire type {wire_type} for field {field_no}")
        if wire_type == VARINT:
            try:
                value, offset = decode_uleb128(data, offset)
            except VarintError as e:
                raise WireError(f"bad VARINT value for field {field_no}: {e}") from e
            fields.append((field_no, VARINT, value))
        else:  # LEN
            try:
                length, offset = decode_uleb128(data, offset)
            except VarintError as e:
                raise WireError(f"bad LEN length for field {field_no}: {e}") from e
            if offset + length > n:
                raise WireError(f"LEN field {field_no} runs past end ({length} bytes)")
            fields.append((field_no, LEN, data[offset:offset + length]))
            offset += length
    return fields


def decode_canonical(data: bytes) -> list[Field]:
    """Decode AND enforce canonicality: the input must be byte-identical to re-encoding what we decoded.
    This is the hard one-byte-form-per-message guarantee (AUDIT F-05). Raises on any non-canonical input."""
    fields = decode(data)
    if encode(fields) != data:
        raise WireError("non-canonical wire bytes (field order, encoding, or padding not canonical)")
    return fields
