"""Tests for axiom.wire — canonical TLV. The canonicality negatives are the AUDIT F-05 fix:
exactly one byte form per message; non-canonical input cannot be decoded (so it cannot be hashed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.wire import encode, decode, decode_canonical, WireError, VARINT, LEN  # noqa: E402


def test_roundtrip_mixed_fields():
    fields = [(1, LEN, b"hello"), (2, VARINT, 300), (3, VARINT, 0), (4, LEN, b"")]
    data = encode(fields)
    assert decode_canonical(data) == sorted(fields, key=lambda f: (f[0],))


def test_encode_is_canonical_regardless_of_input_order():
    a = encode([(2, VARINT, 5), (1, LEN, b"x")])
    b = encode([(1, LEN, b"x"), (2, VARINT, 5)])
    assert a == b  # field order in the call does not change the bytes


def test_decode_canonical_rejects_wrong_field_order():
    # hand-build non-canonical: field 2 before field 1
    non_canon = encode([(2, VARINT, 5)]) + encode([(1, LEN, b"x")])
    # decode tolerates it structurally...
    assert len(decode(non_canon)) == 2
    # ...but canonical decode rejects it (re-encode would sort 1 before 2)
    with pytest.raises(WireError):
        decode_canonical(non_canon)


def test_decode_rejects_unknown_wire_type():
    # tag for field 1 wire_type 5 (unknown): (1<<3)|5 = 13
    with pytest.raises(WireError):
        decode(bytes([13]))


def test_field_zero_rejected():
    with pytest.raises(WireError):
        encode([(0, VARINT, 1)])
    with pytest.raises(WireError):
        decode(b"\x00\x01")


def test_decode_rejects_truncated_len():
    # field 1 LEN, claims 10 bytes, supplies 2
    data = bytes([(1 << 3) | LEN, 10, 0x41, 0x42])
    with pytest.raises(WireError):
        decode(data)


def test_decode_rejects_overlong_tag():
    # overlong uleb128 tag (0x80 0x00) must bubble up as WireError
    with pytest.raises(WireError):
        decode(b"\x80\x00")


def test_repeated_field_values_canonical_order():
    # two LEN values on the same field number must be ascending by bytes to be canonical
    canon = encode([(1, LEN, b"a"), (1, LEN, b"b")])
    assert decode_canonical(canon) == [(1, LEN, b"a"), (1, LEN, b"b")]
    reversed_bytes = encode([(1, LEN, b"b")]) + encode([(1, LEN, b"a")])
    with pytest.raises(WireError):
        decode_canonical(reversed_bytes)


def test_unknown_field_number_preserved_for_canonicality():
    # an unknown field number (99) must survive decode->encode so the CID covers it
    data = encode([(1, LEN, b"x"), (99, VARINT, 7)])
    fields = decode_canonical(data)
    assert (99, VARINT, 7) in fields
