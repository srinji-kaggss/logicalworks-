"""Tests for axiom.fabric — immutable DAG + transaction + chain. Negatives mirror the audit:
never-delete (F-06), monotonic time / window≥1 (F-04), CID-keyed (F-01), chain tamper-detection."""

import hashlib
import hmac
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from axiom.capsule import Capsule  # noqa: E402
from axiom.fabric import Fabric, TxState, LogEntry  # noqa: E402

KEY = b"trusted-genesis-key"


def sign(c: Capsule) -> Capsule:
    unsigned = replace(c, signature=b"").to_bytes()
    return replace(c, signature=hmac.new(KEY, unsigned, hashlib.blake2b).digest())


def fresh():
    fab = Fabric(trusted_key=KEY)
    g = sign(Capsule("capability", "genesis", is_genesis=True, grants=frozenset({"read", "charge"})))
    gcid, v = fab.propose(g, window=1)
    assert v.ok and gcid is not None
    return fab, g, gcid


def test_propose_stores_and_resolves_by_own_cid():
    fab, g, gcid = fresh()
    assert fab.resolve(gcid) == g          # F-01: keyed by its own content hash
    assert gcid == g.cid()


def test_invalid_capsule_is_rejected_and_not_stored():
    fab, g, gcid = fresh()
    bad = Capsule("effect", "needs write", on=(gcid,), needs=frozenset({"write"}))  # not in lineage
    cid, v = fab.propose(bad)
    assert cid is None and not v.ok
    assert fab.resolve(bad.cid()) is None   # not stored


def test_window_must_be_positive():
    fab, _, _ = fresh()
    cid, v = fab.propose(Capsule("entity", "x"), window=0)
    assert cid is None and "window must be >= 1" in v.reason


def test_pending_then_committed_monotone():
    fab = Fabric(trusted_key=KEY)
    cid, _ = fab.propose(Capsule("entity", "x"), window=5)
    assert cid is not None
    assert fab.status(cid) is TxState.PENDING
    fab.tick(10)
    assert fab.status(cid) is TxState.COMMITTED
    fab.tick(100)
    assert fab.status(cid) is TxState.COMMITTED  # monotone — never un-commits (F-04)


def test_time_cannot_rewind():
    fab = Fabric(trusted_key=KEY)
    with pytest.raises(Exception):
        fab.tick(0)        # no zero/negative advance; there is no rewind API at all (F-04)
    with pytest.raises(Exception):
        fab.tick(-5)


def test_abandon_pending_keeps_object_resolvable():
    fab = Fabric(trusted_key=KEY)
    cid, _ = fab.propose(Capsule("entity", "x"), window=5)
    assert cid is not None
    assert fab.abandon(cid).ok
    assert fab.resolve(cid) is not None     # F-06: object NEVER deleted, only dropped from checkout


def test_abandon_committed_fails():
    fab = Fabric(trusted_key=KEY)
    cid, _ = fab.propose(Capsule("entity", "x"), window=1)
    assert cid is not None
    fab.tick(5)
    v = fab.abandon(cid)
    assert not v.ok and "supersede" in v.reason


def test_supersede_old_still_resolves():
    fab = Fabric(trusted_key=KEY)
    cid, _ = fab.propose(Capsule("entity", "v1"), window=1)
    assert cid is not None
    new_cid, v = fab.supersede(cid, Capsule("entity", "v2"), window=1)
    assert v.ok and new_cid is not None and new_cid != cid
    assert fab.status(cid) is TxState.SUPERSEDED
    assert fab.resolve(cid) is not None and fab.resolve(new_cid) is not None  # F-06/F-07: nothing lost


def test_chain_integrity_and_tamper_detection():
    fab = Fabric(trusted_key=KEY)
    fab.propose(Capsule("entity", "a"), window=1)
    fab.propose(Capsule("entity", "b"), window=1)
    assert fab.verify_chain() is True
    # tamper: rewrite a log entry's cid without recomputing the chain
    fab.log[0] = LogEntry(fab.log[0].seq, fab.log[0].event, "b2b256:forged", fab.log[0].chain_tag)
    assert fab.verify_chain() is False
