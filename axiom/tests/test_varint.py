"""Tests for axiom.varint — LEB128. The negative tests (overlong, unterminated, bomb) are the point:
a varint decoder that accepts non-minimal encodings breaks canonical CID (AUDIT F-05 family)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.varint import (  # noqa: E402
    encode_uleb128, decode_uleb128, encode_sleb128, decode_sleb128, VarintError,
)


@pytest.mark.parametrize("n", [0, 1, 63, 64, 127, 128, 255, 300, 16384, 2**32, 2**63, 2**64 - 1])
def test_uleb128_roundtrip(n):
    enc = encode_uleb128(n)
    val, off = decode_uleb128(enc)
    assert val == n and off == len(enc)


@pytest.mark.parametrize("n", [0, 1, -1, 63, -64, 64, -65, 127, -128, 2**40, -(2**40), 2**63 - 1, -(2**63)])
def test_sleb128_roundtrip(n):
    enc = encode_sleb128(n)
    val, off = decode_sleb128(enc)
    assert val == n and off == len(enc)


def test_uleb128_is_minimal():
    # canonical: 0 is one byte 0x00; 128 is exactly two bytes
    assert encode_uleb128(0) == b"\x00"
    assert encode_uleb128(128) == b"\x80\x01"
    assert len(encode_uleb128(127)) == 1


def test_uleb128_rejects_overlong():
    # 0x80 0x00 is a non-minimal encoding of 0 — MUST be rejected (canonicality)
    with pytest.raises(VarintError):
        decode_uleb128(b"\x80\x00")
    # non-minimal encoding of 1 (0x81 0x00) likewise
    with pytest.raises(VarintError):
        decode_uleb128(b"\x81\x00")


def test_uleb128_rejects_unterminated():
    with pytest.raises(VarintError):
        decode_uleb128(b"\x80\x80\x80")  # continuation bits set, no terminator


def test_uleb128_rejects_bomb():
    with pytest.raises(VarintError):
        decode_uleb128(b"\x80" * 11 + b"\x00")  # > 64-bit chain


def test_uleb128_rejects_negative_encode():
    with pytest.raises(VarintError):
        encode_uleb128(-1)


def test_offset_advances_in_stream():
    stream = encode_uleb128(300) + encode_uleb128(7)
    v1, o1 = decode_uleb128(stream, 0)
    v2, o2 = decode_uleb128(stream, o1)
    assert (v1, v2) == (300, 7) and o2 == len(stream)
