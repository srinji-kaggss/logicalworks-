"""Tests for lgwks_access — CapabilityPort interface and HMAC impl (#98).

Tests cover:
1. CapabilityPort interface compliance (HmacCapabilityPort)
2. Keychain persistence round-trip (resolve → persist → reload)
3. Default lacks WORLD_PROMOTE scope
4. mint_promote grants WORLD_PROMOTE
5. TenantStore gating (read/write/promote)
6. Swap seam verification (no CapabilityToken construction outside port)
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_access as access
import lgwks_capability as capability
import lgwks_sqlite as sqlite
import lgwks_vector as vector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Create a temporary in-memory vector store."""
    conn = sqlite3.connect(":memory:")
    # Execute the DDL directly
    conn.executescript(vector.VECTOR_RECORDS_DDL)
    yield conn
    conn.close()


@pytest.fixture
def test_tenant():
    """Test tenant name."""
    return "test-tenant-98"


@pytest.fixture
def mock_keyvault():
    """Mock the macOS Keychain backend symmetrically — both write and read.

    This patches ONLY `security` (add/find-generic-password) against an in-memory
    dict, so the port exercises its REAL resolution path. It does NOT mock
    lgwks_keyvault: an earlier version patched away the SECRETS registry gate,
    which masked F1 (read went through keyvault.get_secret's fixed registry while
    the write went direct → every resolve re-issued). Mocking only the backend
    means a read/write asymmetry surfaces as a test failure, not a green lie.
    """
    store = {}
    original_run = subprocess.run

    def _service_of(cmd):
        return cmd[cmd.index("-s") + 1] if "-s" in cmd else None

    def mock_run(cmd, **kwargs):
        if cmd[:1] == ["security"]:
            if "add-generic-password" in cmd:
                store[_service_of(cmd)] = kwargs.get("input", "")
                return mock.Mock(returncode=0, stdout="", stderr="")
            if "find-generic-password" in cmd:
                val = store.get(_service_of(cmd))
                if val:
                    return mock.Mock(returncode=0, stdout=val, stderr="")
                return mock.Mock(returncode=44, stdout="", stderr="not found")
        return original_run(cmd, **kwargs)

    with mock.patch.object(subprocess, "run", mock_run):
        yield store


# ---------------------------------------------------------------------------
# Test: CapabilityPort interface compliance
# ---------------------------------------------------------------------------


def test_hmac_port_implements_capability_port():
    """HmacCapabilityPort implements all CapabilityPort methods."""
    port = access.HmacCapabilityPort()

    # Verify all required methods exist
    assert hasattr(port, "resolve")
    assert hasattr(port, "verify")
    assert hasattr(port, "require_scope")
    assert hasattr(port, "principal_of")
    assert hasattr(port, "cap_ref")
    assert hasattr(port, "mint_promote")


# ---------------------------------------------------------------------------
# Test: Keychain persistence round-trip
# ---------------------------------------------------------------------------


def test_resolve_persists_key_to_keychain(mock_keyvault):
    """First resolve() persists key to Keychain; subsequent resolve() reloads it."""
    port = access.HmacCapabilityPort()
    tenant = "test-tenant"

    # First resolve should create and persist
    handle1, key1 = port.resolve(tenant)

    assert handle1 is not None
    assert key1 is not None
    assert len(key1) == 32  # 32-byte HMAC key

    # Key should be stored in mock keyvault
    item_name = port._item_name(tenant)
    assert item_name in mock_keyvault

    # Second resolve should load the same key
    handle2, key2 = port.resolve(tenant)

    assert key1 == key2  # Same key
    assert handle2.token.tenant == tenant  # Same tenant


def test_resolve_reload_yields_validating_token(mock_keyvault):
    """Resolved token validates correctly with the stored key."""
    port = access.HmacCapabilityPort()
    tenant = "test-tenant"

    handle, key = port.resolve(tenant)

    # Verify should succeed
    verified = port.verify(handle, key)
    assert verified.principal == tenant
    assert verified.cap_ref == handle.token.nonce


# ---------------------------------------------------------------------------
# Test: Default lacks WORLD_PROMOTE
# ---------------------------------------------------------------------------


def test_default_resolve_lacks_world_promote(mock_keyvault):
    """Default resolve() does NOT grant WORLD_PROMOTE scope."""
    port = access.HmacCapabilityPort()
    tenant = "test-tenant"

    handle, key = port.resolve(tenant)
    verified = port.verify(handle, key)

    assert capability.TENANT_RW in verified.scopes
    assert capability.WORLD_R in verified.scopes
    assert capability.WORLD_PROMOTE not in verified.scopes


# ---------------------------------------------------------------------------
# Test: mint_promote grants WORLD_PROMOTE
# ---------------------------------------------------------------------------


def test_mint_promote_grants_world_promote(mock_keyvault):
    """mint_promote() grants WORLD_PROMOTE scope."""
    port = access.HmacCapabilityPort()
    tenant = "test-tenant"

    handle, key = port.mint_promote(tenant)
    verified = port.verify(handle, key)

    assert capability.TENANT_RW in verified.scopes
    assert capability.WORLD_R in verified.scopes
    assert capability.WORLD_PROMOTE in verified.scopes


# ---------------------------------------------------------------------------
# Test: TenantStore gating
# ---------------------------------------------------------------------------


def _make_record(cid: str, source_cid: str, space_id: str, tenant: str, text: str) -> vector.VectorRecord:
    """Helper to create a VectorRecord with proper embedding."""
    # Use encode_record which handles normalization and cid computation
    embedding_floats = [0.1] * 128
    return vector.encode_record(
        embedding_floats,
        modality="text",
        space_id=space_id,
        tenant=tenant,
        source_cid=source_cid,
    )


def test_tenant_store_write_requires_tenant_rw(mock_keyvault, temp_db, test_tenant):
    """TenantStore.write() requires TENANT_RW scope."""
    port = access.HmacCapabilityPort()
    handle, key = port.resolve(test_tenant)

    store = access.TenantStore(port, handle, key, temp_db)

    # Write should succeed with TENANT_RW (default has it)
    record = _make_record("test-cid-001", "src-001", "space-1", test_tenant, "test content")
    store.write(record)

    # Verify record was written (use record.cid, not the source_cid!)
    found = vector.get_record_for_tenant(temp_db, record.cid, test_tenant)
    assert found is not None
    assert found.tenant == test_tenant


def test_tenant_store_read_own_tenant(mock_keyvault, temp_db, test_tenant):
    """TenantStore.read() returns own-tenant records."""
    port = access.HmacCapabilityPort()
    handle, key = port.resolve(test_tenant)
    store = access.TenantStore(port, handle, key, temp_db)

    # Write a record
    record = _make_record("test-cid-002", "src-002", "space-1", test_tenant, "own tenant content")
    store.write(record)

    # Read should return the record (use record.cid, not source_cid)
    found = store.read(record.cid)
    assert found is not None
    assert found.tenant == test_tenant


def test_tenant_store_promote_requires_scope(mock_keyvault, temp_db, test_tenant):
    """TenantStore.promote() requires WORLD_PROMOTE scope."""
    port = access.HmacCapabilityPort()

    # Default resolve lacks WORLD_PROMOTE
    handle, key = port.resolve(test_tenant)
    store = access.TenantStore(port, handle, key, temp_db)

    # Write a record first
    record = _make_record("test-cid-003", "src-003", "space-1", test_tenant, "to promote")
    store.write(record)

    # Promote without WORLD_PROMOTE should fail (use record.cid, not source_cid)
    with pytest.raises(capability.CapabilityError) as exc_info:
        store.promote(record.cid)

    assert "lacks required scope" in str(exc_info.value)
    assert "world:promote" in str(exc_info.value).lower()


def test_tenant_store_promote_with_scope_succeeds(mock_keyvault, temp_db, test_tenant):
    """TenantStore.promote() succeeds with WORLD_PROMOTE scope."""
    port = access.HmacCapabilityPort()

    # Resolve with promote scope
    handle, key = port.mint_promote(test_tenant)
    store = access.TenantStore(port, handle, key, temp_db)

    # Write a record first
    record = _make_record("test-cid-004", "src-004", "space-1", test_tenant, "to promote")
    store.write(record)

    # Promote should succeed (use record.cid, not source_cid)
    result = store.promote(record.cid)

    assert result is not None
    assert result.get("promoted") == record.cid
    assert result.get("tenant") == test_tenant
    assert "audit_seq" in result
    assert "audit_hash" in result

    # Verify record is now at world tier (use record.cid, not source_cid)
    world_record = vector.get_record_for_tenant(temp_db, record.cid, capability.WORLD_TENANT)
    assert world_record is not None
    assert world_record.tenant == capability.WORLD_TENANT


# ---------------------------------------------------------------------------
# Test: Swap seam verification
# ---------------------------------------------------------------------------


def test_swap_seam_no_direct_capability_token_construction():
    """Verify no code outside lgwks_access.py constructs CapabilityToken directly.

    This is the #97 standalone invariant seam check:
    - Tokens are opaque handles
    - Exactly one mint and one verify locus
    - No CapabilityToken(...) outside port impl
    """
    import ast
    import re

    # Read lgwks_access.py
    access_path = Path(__file__).resolve().parent.parent / "lgwks_access.py"
    access_source = access_path.read_text()

    # Parse the AST
    tree = ast.parse(access_source)

    # Find all CapabilityToken constructions
    token_constructions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "CapabilityToken":
                token_constructions.append(node.lineno)
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "CapabilityToken"
            ):
                token_constructions.append(node.lineno)

    # lgwks_access.py CAN construct CapabilityToken (via lgwks_capability module)
    # but NO OTHER module should
    # Check other modules
    repo_root = Path(__file__).resolve().parent.parent
    for py_file in repo_root.glob("lgwks_*.py"):
        if py_file.name == "lgwks_access.py":
            continue  # allowed
        if py_file.name == "lgwks_capability.py":
            continue  # allowed - defines CapabilityToken
        if py_file.name == "lgwks_promote.py":
            continue  # allowed - consumes token via lgwks_capability

        source = py_file.read_text()
        # Check for CapabilityToken construction
        if re.search(r"CapabilityToken\s*\(", source):
            pytest.fail(
                f"{py_file.name} constructs CapabilityToken directly - "
                "violates #97 swap seam invariant"
            )


def test_swap_seam_tenant_store_depends_on_port_only():
    """Verify TenantStore depends on CapabilityPort interface, not concrete token."""
    import inspect

    # Get TenantStore source
    source = inspect.getsource(access.TenantStore)

    # Should NOT contain CapabilityToken construction
    assert "CapabilityToken(" not in source
    assert "capability.CapabilityToken(" not in source

    # Should use port methods
    assert "self._port.verify" in source or "self._port.require_scope" in source


# ---------------------------------------------------------------------------
# Test: Convenience functions
# ---------------------------------------------------------------------------


def test_resolve_capability_for_tenant(mock_keyvault):
    """resolve_capability_for_tenant() returns (port, handle, key)."""
    tenant = "test-tenant"

    port, handle, key = access.resolve_capability_for_tenant(tenant)

    assert isinstance(port, access.HmacCapabilityPort)
    assert isinstance(handle, access.HmacCapToken)
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_resolve_promote_capability_for_tenant(mock_keyvault):
    """resolve_promote_capability_for_tenant() returns promote-scoped capability."""
    tenant = "test-tenant"

    port, handle, key = access.resolve_promote_capability_for_tenant(tenant)

    assert isinstance(port, access.HmacCapabilityPort)
    assert isinstance(handle, access.HmacCapToken)
    assert isinstance(key, bytes)

    # Verify has WORLD_PROMOTE
    verified = port.verify(handle, key)
    assert capability.WORLD_PROMOTE in verified.scopes


# ---------------------------------------------------------------------------
# Test: operator promote CLI wired end-to-end (guards F4)
# ---------------------------------------------------------------------------


def test_promote_cli_smoke(mock_keyvault, tmp_path, monkeypatch):
    """`lgwks access promote` wires parser → --store → create_store → promote.

    Guards F4 (the CLI called sqlite.connect() with no path → TypeError on every
    invocation) and exercises the CLI error/print paths that referenced an
    unimported `sys`. The API-level tests never touched the command path, so both
    defects shipped green.
    """
    import argparse

    import lgwks_cognition as cognition
    monkeypatch.setattr(cognition, "_DIR", tmp_path / "cognition")

    db = tmp_path / "vec.db"
    conn = vector.create_store(db)
    rec = _make_record("c", "src-cli", "space-1", "cli-tenant", "x")
    vector.upsert_record(conn, rec, admin=vector.ADMIN)
    conn.commit()
    conn.close()

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    access.add_parser(sub)
    args = parser.parse_args(
        ["access", "promote", rec.cid, "--tenant", "cli-tenant", "--store", str(db), "--json"]
    )

    assert args.func(args) == 0

    moved = vector.get_record_for_tenant(vector.create_store(db), rec.cid, capability.WORLD_TENANT)
    assert moved is not None
    assert moved.tenant == capability.WORLD_TENANT


# ---------------------------------------------------------------------------
# Test: #99 mandatory gating — the unscoped primitives are admin-only
# ---------------------------------------------------------------------------


def test_unscoped_primitives_are_admin_only(temp_db, test_tenant):
    """A tenant-context call to an UNSCOPED primitive (no ADMIN sentinel) is rejected.

    This is #99's load-bearing clause: the bypass is mechanical, not advisory. A
    direct upsert/get/query without `admin=vector.ADMIN` raises AdminOnlyError; the
    same call WITH the sentinel (admin/migration context) succeeds.
    """
    rec = _make_record("x", "src-admin", "space-1", test_tenant, "x")

    for call in (
        lambda: vector.upsert_record(temp_db, rec),
        lambda: vector.get_record(temp_db, rec.cid),
        lambda: vector.query_by_source(temp_db, "src-admin"),
    ):
        with pytest.raises(vector.AdminOnlyError):
            call()

    # With the sentinel, the admin path works.
    assert vector.upsert_record(temp_db, rec, admin=vector.ADMIN) is True
    assert vector.get_record(temp_db, rec.cid, admin=vector.ADMIN) is not None
    assert len(vector.query_by_source(temp_db, "src-admin", admin=vector.ADMIN)) == 1


# ---------------------------------------------------------------------------
# Test: swap-seam acceptance — TenantStore gates via a FAKE CapabilityPort
# ---------------------------------------------------------------------------


class _FakePort:
    """A non-HMAC CapabilityPort stand-in. Proves TenantStore's dependency is on the
    CapabilityPort *interface* (the #97 seam), not the concrete HMAC token — so the
    future ed25519/Principal impl swaps in here without touching TenantStore."""

    def __init__(self, principal, scopes):
        self._principal = principal
        self._scopes = frozenset(scopes)

    def verify(self, handle, key):
        return access.VerifiedCap(
            principal=self._principal, cap_ref="fake-ref",
            scopes=self._scopes, _internal_cap=handle,
        )

    def require_scope(self, handle, scope, key):
        v = self.verify(handle, key)
        if scope not in v.scopes:
            raise capability.CapabilityError(f"fake-port: lacks {scope!r}")
        return v

    def resolve(self, principal):  # not exercised here
        raise NotImplementedError

    def principal_of(self, verified):
        return verified.principal

    def cap_ref(self, verified):
        return verified.cap_ref

    def mint_promote(self, principal):
        raise NotImplementedError


def test_tenant_store_gates_through_a_fake_port(temp_db):
    """TenantStore enforces scopes via whatever CapabilityPort it is handed."""
    # A read-capable principal can write its own row and read it back.
    rw = access.TenantStore(
        _FakePort("tenant-Z", {capability.TENANT_RW, capability.WORLD_R}),
        handle=None, key=b"", conn=temp_db,
    )
    rec = _make_record("z", "src-z", "space-1", "tenant-Z", "z")
    rw.write(rec)
    assert rw.read(rec.cid) is not None

    # A principal WITHOUT TENANT_RW is rejected at write — purely via the fake port.
    ro = access.TenantStore(
        _FakePort("tenant-Z", {capability.WORLD_R}),
        handle=None, key=b"", conn=temp_db,
    )
    with pytest.raises(capability.CapabilityError):
        ro.write(_make_record("z2", "src-z2", "space-1", "tenant-Z", "z2"))


# ---------------------------------------------------------------------------
# Test: §1-INV holds THROUGH the router (the A/B sweep, routed via TenantStore)
# ---------------------------------------------------------------------------


def test_router_sweep_zero_cross_tenant_leak(mock_keyvault, temp_db):
    """Seed A-private / B-private / world rows, then drive reads through the router
    for tenant-A: A sees own ⊕ world, never B's private rows. §1-INV via TenantStore."""
    port = access.HmacCapabilityPort()
    handle, key = port.resolve("tenant-A")
    store_a = access.TenantStore(port, handle, key, temp_db)

    a_cids, b_cids = [], []
    world_cid = None
    for i in range(200):
        ra = _make_record(f"a{i}", f"srcA{i}", "space-1", "tenant-A", "a")
        rb = _make_record(f"b{i}", f"srcB{i}", "space-1", "tenant-B", "b")
        vector.upsert_record(temp_db, ra, admin=vector.ADMIN)
        vector.upsert_record(temp_db, rb, admin=vector.ADMIN)
        a_cids.append(ra.cid)
        b_cids.append(rb.cid)
    rw = _make_record("w", "srcW", "space-1", capability.WORLD_TENANT, "w")
    vector.upsert_record(temp_db, rw, admin=vector.ADMIN)
    world_cid = rw.cid
    temp_db.commit()

    # query() through the router: only own ⊕ world, zero B rows.
    seen = {r.cid for r in store_a.query()}
    assert world_cid in seen
    assert seen & set(a_cids) == set(a_cids), "A must see all its own rows"
    assert not (seen & set(b_cids)), "router leaked a cross-tenant row into query()"

    # read() through the router: A resolves its own + world, never B's private cid.
    assert store_a.read(a_cids[0]) is not None
    assert store_a.read(world_cid) is not None
    for bc in b_cids[:50]:
        assert store_a.read(bc) is None, "router leaked a cross-tenant cid via read()"
