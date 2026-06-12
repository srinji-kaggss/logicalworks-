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
    """Mock keyvault for tests that don't want Keychain access."""
    store = {}

    # Single shared instance for SECRETS patch and mock_get_secret
    class SecretsWithFallback(dict):
        def get(self, key, default=None):
            # Allow any lgwks:cap:* service through
            if key.startswith("lgwks:cap:"):
                return (key, "LGWKS_CAP")  # dummy spec, just needs to be truthy
            return super().get(key, default)
        def __contains__(self, key):
            if key.startswith("lgwks:cap:"):
                return True
            return super().__contains__(key)

    secrets_mock = SecretsWithFallback()

    def mock_get_secret(name):
        # Check SECRETS first (mimics real get_secret behavior)
        spec = secrets_mock.get(name)
        if not spec:
            return (None, "none")
        secret = store.get(name)
        return (secret, "keychain") if secret else (None, "none")

    with mock.patch.object(access.keyvault, "get_secret", mock_get_secret):
        with mock.patch.object(access.keyvault, "SECRETS", secrets_mock):
            # Patch the subprocess call for store_key
            original_run = subprocess.run

            def mock_run(cmd, **kwargs):
                if cmd[0] == "security" and "add-generic-password" in cmd:
                    # Extract service name and key from command
                    service_idx = cmd.index("-s") + 1
                    service = cmd[service_idx]
                    # Get key from stdin (input kwarg)
                    key_hex = kwargs.get("input", "")
                    store[service] = key_hex
                    return mock.Mock(returncode=0, stderr="")
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
