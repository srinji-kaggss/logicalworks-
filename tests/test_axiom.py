"""
Tests for lgwks_axiom — the Axiom v0 verifier core. Each test maps to a SPEC-axiom-isa-v0 acceptance
invariant; the negative tests are the ones that matter (a gate is theater unless its failure is proven).
Pure/deterministic: no network, no LLM, `now` injected — so the whole suite is replayable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgwks_axiom import (  # noqa: E402
    Capsule, Fabric, TxState, KINDS,
    gauge_open_holes, gauge_pending_ratio,
)


def _root(claim="root", grants=frozenset({"read"})):
    return Capsule("entity", "human", claim, grants=grants)


# --- INV-2 decidable click: a well-formed capsule clicks (happy path) ---
def test_valid_capsule_clicks():
    fab = Fabric()
    assert fab.click(_root()).ok


# --- INV-3 base-first: a capsule whose base is not noded is REJECTED (negative) ---
def test_base_first_violation_rejected():
    fab = Fabric()
    orphan = Capsule("entity", "human", "no base", on=("b2:deadbeef",))
    v = fab.click(orphan)
    assert not v.ok and "base-first" in v.reason


# --- INV-5 capability up the DAG: needs not carried by lineage is REJECTED (negative) ---
def test_capability_not_in_lineage_rejected():
    fab = Fabric()
    cid, v = fab.propose(_root(grants=frozenset({"read"})), now=0, window=10)
    assert cid is not None
    needs_write = Capsule("effect", "ai+human:design", "write something",
                          on=(cid,), needs=frozenset({"write"}))
    v = fab.click(needs_write)
    assert not v.ok and "capability not in lineage" in v.reason


def test_capability_granted_by_lineage_clicks():
    fab = Fabric()
    cid, _ = fab.propose(_root(grants=frozenset({"read", "write"})), now=0, window=10)
    assert cid is not None
    ok_cap = Capsule("effect", "ai+human:design", "write", on=(cid,), needs=frozenset({"write"}))
    assert fab.click(ok_cap).ok


# --- ADR-063 interval bounds: out-of-range parameter is REJECTED (negative) ---
def test_param_out_of_interval_rejected():
    fab = Fabric()
    bad = Capsule("constraint", "human", "tension", params={"tension": (999.0, 0.0, 200.0)})
    v = fab.click(bad)
    assert not v.ok and "out of" in v.reason


# --- closed vocabulary: unknown kind REJECTED (negative) ---
def test_unknown_kind_rejected():
    fab = Fabric()
    v = fab.click(Capsule("feature", "human", "vague"))  # 'feature' is not a canonical kind
    assert not v.ok and "unknown kind" in v.reason
    assert "feature" not in KINDS


# --- SPEC §8 effectful kinds require confirmation even when the click passes ---
def test_effect_requires_confirm():
    fab = Fabric()
    cid, _ = fab.propose(_root(grants=frozenset({"charge"})), now=0, window=10)
    assert cid is not None
    eff = Capsule("effect", "ai+human:ops", "capture", on=(cid,), needs=frozenset({"charge"}))
    v = fab.click(eff)
    assert v.ok and v.requires_confirm


# --- SPEC §14 transaction: pending revert is free; committed reject is refused ---
def test_pending_then_committed_transaction():
    fab = Fabric()
    cid, _ = fab.propose(_root(), now=0, window=10)
    assert cid is not None
    assert fab.status(cid, now=5) is TxState.PENDING          # within window
    assert fab.revert(cid, now=5).ok                          # pre-commit reject is free
    # re-propose and let the window elapse
    cid2, _ = fab.propose(_root("again"), now=0, window=10)
    assert cid2 is not None
    assert fab.status(cid2, now=20) is TxState.COMMITTED       # window elapsed
    v = fab.revert(cid2, now=20)
    assert not v.ok and "cannot just reject" in v.reason       # SPEC §14


def test_supersede_marks_old_and_appends_new():
    fab = Fabric()
    cid, _ = fab.propose(_root("v1"), now=0, window=10)
    assert cid is not None
    new_cid, v = fab.supersede(cid, _root("v2"), now=20, window=10)
    assert v.ok and new_cid is not None and new_cid != cid
    assert fab.status(cid, now=20) is TxState.SUPERSEDED


# --- INV-1 CID is deterministic over canonical bytes (same meaning -> same id) ---
def test_cid_deterministic():
    a = Capsule("entity", "human", "x", grants=frozenset({"read"}))
    b = Capsule("entity", "human", "x", grants=frozenset({"read"}))
    assert a.cid() == b.cid()
    c = Capsule("entity", "human", "y", grants=frozenset({"read"}))
    assert a.cid() != c.cid()


# --- gauges are deterministic strict-math folds producing an actionable next step (0-AI) ---
def test_gauge_open_holes_is_actionable_and_deterministic():
    fab = Fabric()
    cid, _ = fab.propose(_root(), now=0, window=10)
    assert cid is not None
    fab.propose(Capsule("constraint", "human", "dispute policy?", on=(cid,), is_hole=True), now=0, window=10)
    g1 = gauge_open_holes(fab)
    g2 = gauge_open_holes(fab)
    assert g1 == g2 and g1["metric"] == 1 and "node the hole" in g1["next_step"]


def test_gauge_pending_ratio():
    fab = Fabric()
    fab.propose(_root(), now=0, window=10)
    g = gauge_pending_ratio(fab, now=0)            # still in window -> pending
    assert g["metric"] == 1.0
    g2 = gauge_pending_ratio(fab, now=99)          # window elapsed -> committed
    assert g2["metric"] == 0.0


# --- INV-1 0-AI: the verifier core imports no network/LLM module ---
def test_core_is_zero_ai():
    import lgwks_axiom as ax
    src = Path(ax.__file__).read_text()
    for banned in ("import requests", "openai", "anthropic", "urllib.request", "httpx"):
        assert banned not in src, f"verifier core must be 0-AI/offline; found {banned!r}"
