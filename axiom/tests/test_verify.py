"""Tests for axiom.verify — the decidable click. These re-run the AUDIT exploits and assert they now FAIL:
SP-1 capability ladder, the by:-string self-grant (F-03), grant forgery, unsigned genesis, hole laundering."""

import hashlib
import hmac
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.capsule import Capsule  # noqa: E402
from axiom.verify import verify, effective_grants  # noqa: E402

KEY = b"trusted-genesis-key"


def sign(c: Capsule, key: bytes = KEY) -> Capsule:
    unsigned = replace(c, signature=b"").to_bytes()
    return replace(c, signature=hmac.new(key, unsigned, hashlib.blake2b).digest())


def store(*capsules: Capsule):
    d = {c.cid(): c for c in capsules}
    return d, (lambda cid: d.get(cid))


def test_signed_genesis_grants_flow_to_child():
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"charge", "read"})))
    _, resolve = store(g)
    child = Capsule("effect", "capture", on=(g.cid(),), needs=frozenset({"charge"}))
    v = verify(child, resolve, KEY)
    assert v.ok and v.requires_confirm  # effect → confirm


def test_unsigned_genesis_grants_nothing():
    g = Capsule("capability", "fake genesis", is_genesis=True, grants=frozenset({"charge"}))  # no signature
    _, resolve = store(g)
    child = Capsule("effect", "capture", on=(g.cid(),), needs=frozenset({"charge"}))
    v = verify(child, resolve, KEY)
    assert not v.ok  # F-03: unsigned genesis carries no authority


def test_self_grant_path_is_gone():
    # the old by:"ai+human:charge" self-grant (AUDIT F-03 / SP): no base, needs charge → must FAIL
    c = Capsule("effect", "charge with no base", by="ai+human:charge", needs=frozenset({"charge"}))
    v = verify(c, store()[1], KEY)
    assert not v.ok and "capability not in lineage" in v.reason


def test_grant_forgery_rejected():
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"read"})))
    _, resolve = store(g)
    # non-genesis child tries to grant 'admin' which lineage never carried
    forger = Capsule("role", "i grant admin", on=(g.cid(),), grants=frozenset({"admin"}))
    v = verify(forger, resolve, KEY)
    assert not v.ok and "forgery" in v.reason


def test_sp1_capability_ladder_via_hole_fails():
    # AUDIT SP-1: park node-at-runtime in a hole, inherit it. Capsule.py forbids a hole with grants,
    # so the laundering capsule cannot even be built; and a grantless hole contributes ∅.
    with pytest.raises(Exception):
        Capsule("constraint", "park", is_hole=True, grants=frozenset({"node-at-runtime"})).to_bytes()
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"read"})))
    hole = Capsule("constraint", "open q", on=(g.cid(),), is_hole=True)  # legal hole, grants=∅
    _, resolve = store(g, hole)
    child = Capsule("effect", "abuse", on=(hole.cid(),), needs=frozenset({"node-at-runtime"}))
    v = verify(child, resolve, KEY)
    assert not v.ok and "capability not in lineage" in v.reason  # hole laundered nothing


def test_needs_not_in_lineage_fails():
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"read"})))
    _, resolve = store(g)
    child = Capsule("effect", "write", on=(g.cid(),), needs=frozenset({"write"}))
    assert not verify(child, resolve, KEY).ok


def test_base_first_missing_base_fails():
    c = Capsule("entity", "orphan", on=("b2b256:doesnotexist",))
    v = verify(c, store()[1], KEY)
    assert not v.ok and "base-first" in v.reason


def test_unknown_kind_fails():
    v = verify(Capsule("feature", "vague"), store()[1], KEY)
    assert not v.ok and "unknown kind" in v.reason


def test_param_out_of_interval_fails():
    v = verify(Capsule("constraint", "t", params={"t": (999.0, 0.0, 200.0)}), store()[1], KEY)
    assert not v.ok and "out of" in v.reason


def test_genesis_root_entity_clicks():
    # a plain root entity (no on, no needs) just clicks
    assert verify(Capsule("entity", "root", grants=frozenset()), store()[1], KEY).ok


def test_effective_grants_intersection():
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"read", "charge"})))
    _, resolve = store(g)
    mid = Capsule("role", "re-grant subset", on=(g.cid(),), grants=frozenset({"read"}))
    assert effective_grants(mid, resolve, KEY) == frozenset({"read"})  # only what it holds ∩ declares
