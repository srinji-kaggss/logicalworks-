"""Tests for axiom.cid — content identity. verify/require are the AUDIT F-01 fix (verify on read);
256-bit width is the F-09 fix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.cid import compute_cid, verify_cid, require_cid, CidError, CID_ALG  # noqa: E402


def test_deterministic_and_distinct():
    assert compute_cid(b"hello") == compute_cid(b"hello")
    assert compute_cid(b"hello") != compute_cid(b"world")


def test_full_width_256_bit():
    cid = compute_cid(b"x")
    alg, _, hexdigest = cid.partition(":")
    assert alg == CID_ALG
    assert len(hexdigest) == 64  # 32 bytes * 2 hex chars = 256-bit (AUDIT F-09)


def test_verify_true_and_false():
    cid = compute_cid(b"payload")
    assert verify_cid(b"payload", cid) is True
    assert verify_cid(b"tampered", cid) is False          # the F-01 catch
    assert verify_cid(b"payload", "b2b256:deadbeef") is False
    assert verify_cid(b"payload", "wrongalg:" + cid.split(":")[1]) is False


def test_require_raises_on_mismatch():
    cid = compute_cid(b"a")
    require_cid(b"a", cid)  # no raise
    with pytest.raises(CidError):
        require_cid(b"b", cid)


def test_non_bytes_rejected():
    with pytest.raises(CidError):
        compute_cid("not bytes")  # type: ignore[arg-type]
