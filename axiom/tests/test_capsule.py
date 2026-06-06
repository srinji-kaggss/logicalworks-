"""Tests for axiom.capsule — typed Claim/Hole. Negatives mirror the audit: hole-with-grants rejected
(F-02), NaN/Inf params rejected + −0 normalized (F-05), CID stable across equal meaning."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.capsule import Capsule, CapsuleError  # noqa: E402


def test_roundtrip_claim():
    c = Capsule("entity", "party being billed", grants=frozenset({"read"}), by="human")
    back = Capsule.from_bytes(c.to_bytes())
    assert back == c and back.cid() == c.cid()


def test_roundtrip_with_params_and_on():
    c = Capsule("constraint", "tension", on=("b2b256:aa", "b2b256:bb"),
                params={"tension": (170.0, 0.0, 200.0)})
    back = Capsule.from_bytes(c.to_bytes())
    assert back == c


def test_hole_with_grants_rejected():
    h = Capsule("constraint", "dispute?", is_hole=True, grants=frozenset({"admin"}))
    with pytest.raises(CapsuleError):
        h.to_bytes()  # F-02: a hole may not carry grants


def test_hole_with_needs_rejected():
    h = Capsule("constraint", "dispute?", is_hole=True, needs=frozenset({"charge"}))
    with pytest.raises(CapsuleError):
        h.to_bytes()


def test_valid_hole_roundtrips():
    h = Capsule("constraint", "what on dispute?", on=("b2b256:aa",), is_hole=True)
    assert Capsule.from_bytes(h.to_bytes()) == h


def test_nan_param_rejected():
    c = Capsule("constraint", "x", params={"p": (float("nan"), 0.0, 1.0)})
    with pytest.raises(CapsuleError):
        c.to_bytes()  # F-05


def test_inf_param_rejected():
    c = Capsule("constraint", "x", params={"p": (float("inf"), 0.0, 1.0)})
    with pytest.raises(CapsuleError):
        c.to_bytes()


def test_negative_zero_normalized():
    a = Capsule("constraint", "x", params={"p": (-0.0, 0.0, 1.0)})
    b = Capsule("constraint", "x", params={"p": (0.0, 0.0, 1.0)})
    assert a.cid() == b.cid()  # −0.0 and 0.0 hash identically (F-05 normalization)


def test_cid_independent_of_set_order():
    a = Capsule("effect", "x", needs=frozenset({"read", "write"}), grants=frozenset({"read"}))
    b = Capsule("effect", "x", needs=frozenset({"write", "read"}), grants=frozenset({"read"}))
    assert a.cid() == b.cid()  # sets are canonical-sorted


def test_genesis_and_signature_survive_roundtrip():
    g = Capsule("capability", "genesis", is_genesis=True, signature=b"\x01\x02\x03",
                grants=frozenset({"charge", "admin"}))
    back = Capsule.from_bytes(g.to_bytes())
    assert back.is_genesis and back.signature == b"\x01\x02\x03" and back == g
