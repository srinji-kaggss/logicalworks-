"""lgwks_access — CapabilityPort interface and HMAC impl (#98 / #97 seam).

This is the load-bearing seam for the CIAM convergence epic (#97). The interface
is final; the HMAC impl is v2, and a future ed25519/Principal impl swaps in behind
it without changing callers.

Authority: #97 standalone invariant — tokens are opaque handles, one mint/verify
locus, identity is principal-shaped, no kernel import.
"""

from __future__ import annotations

import secrets
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import lgwks_capability as capability
import lgwks_vector as vector

# ---------------------------------------------------------------------------
# Verified capability — what require_scope returns after verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedCap:
    """A verified capability handle — opaque to callers, rich to the port.

    principal      — the identity (today tenant:str, tomorrow PrincipalId).
    cap_ref        — audit identifier (today nonce, tomorrow DelegationHop id).
    scopes         — the tier grant (frozenset of scope strings).
    _internal_cap  — the concrete token (HmacCapToken today); NEVER exposed outside port.
    """
    principal: str
    cap_ref: str
    scopes: frozenset[str]
    _internal_cap: Any  # CapabilityToken for HmacCapabilityPort


# ---------------------------------------------------------------------------
# CapabilityPort — the final interface (kernel-shaped, impl-agnostic)
# ---------------------------------------------------------------------------


class CapabilityPort(Protocol):
    """The capability port — the single authorization locus.

    This is the interface that #97's standalone invariant demands:
    - Tokens are opaque handles — callers never construct/read CapabilityToken(...)
    - Exactly one mint and one verify locus — the kernel migration replaces those two bodies
    - Identity is principal-shaped — passed by value, signature never changes
    - No kernel import — conformance is mirrored + tested locally
    """

    def resolve(self, principal: str) -> tuple[Any, bytes]:
        """Resolve a capability for principal.

        Returns (handle, key) where handle is opaque to callers and key is the
        signing key for require_scope. On first-run, issues and persists the key
        to the macOS Keychain.
        """
        ...

    def verify(self, handle: Any, key: bytes) -> VerifiedCap:
        """Verify a handle and return VerifiedCap.

        Raises capability.CapabilityError if invalid.
        """
        ...

    def require_scope(self, handle: Any, scope: str, key: bytes) -> VerifiedCap:
        """Verify handle has `scope`, return VerifiedCap.

        Raises capability.CapabilityError if invalid or lacks scope.
        """
        ...

    def principal_of(self, verified: VerifiedCap) -> str:
        """Extract the principal from a verified capability."""
        ...

    def cap_ref(self, verified: VerifiedCap) -> str:
        """Extract the audit reference (nonce / DelegationHop id) from verified."""
        ...

    def mint_promote(self, principal: str) -> tuple[Any, bytes]:
        """Issue a promote-scoped capability for principal.

        Returns (handle, key). The handle has WORLD_PROMOTE scope.
        """
        ...


# ---------------------------------------------------------------------------
# HmacCapabilityPort — v2 HMAC impl behind the final interface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HmacCapToken:
    """Internal HMAC capability token — NEVER leaks outside this module.

    This is the ONLY place that constructs/reads a CapabilityToken.
    The future kernel impl (PortCapabilityPort — ed25519 trail / Principal)
    is a second class behind the same CapabilityPort interface.
    """
    token: capability.CapabilityToken
    key: bytes


class HmacCapabilityPort:
    """HMAC-SHA256 capability port — v2 impl behind CapabilityPort interface.

    Keychain persistence: per-principal capability keys live in Keychain
    under `lgwks:cap:<principal>`. This matches the #98 scope:
    - Persistence via the macOS Keychain (`security` generic-password), read and
      write symmetric. NOT lgwks_keyvault.get_secret — that gates on a fixed
      registry and can't address dynamic per-principal names (see _load_key).
    - Resolution loads or first-run issues + persists
    - Session binding via lgwks_session begin/end
    - Operator CLI for promote
    """

    def __init__(self) -> None:
        self._keyvault_service = "lgwks:cap"

    def _item_name(self, principal: str) -> str:
        return f"{self._keyvault_service}:{principal}"

    def _load_key(self, principal: str) -> bytes | None:
        """Load the principal's capability key from the macOS Keychain, or None.

        Symmetric with _store_key: same `security` generic-password backend, same
        dynamic service name, same `-a lgwks` account. We deliberately do NOT route
        this through lgwks_keyvault.get_secret — that resolves a FIXED registry
        (keyvault.SECRETS) and returns None for any name not pre-registered, so it
        cannot address per-principal service names like `lgwks:cap:<principal>`.
        Routing the read through it (while the write went direct) made every
        resolve() miss and re-issue a fresh key. Convergence (#97): a future
        keyvault generic by-service accessor would fold both paths into one locus.
        """
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", "lgwks",
             "-s", self._item_name(principal), "-w"],
            text=True, capture_output=True, timeout=10,
        )
        out = proc.stdout.strip()
        if proc.returncode != 0 or not out:
            return None
        try:
            return bytes.fromhex(out)
        except ValueError:
            return None

    def _store_key(self, principal: str, key: bytes) -> None:
        """Persist key to Keychain for principal (hex-encoded, value off the argv)."""
        service = self._item_name(principal)
        key_hex = key.hex()
        # Use security add-generic-password with -w for the value
        proc = subprocess.run(
            ["security", "add-generic-password", "-U", "-a", "lgwks", "-s", service, "-w"],
            input=key_hex,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"failed to store capability key: {proc.stderr}")

    def resolve(self, principal: str) -> tuple[HmacCapToken, bytes]:
        """Resolve capability for principal — load or issue+persist.

        Returns (HmacCapToken, key). The token has DEFAULT_SCOPES (tenant:rw + world:r).
        WORLD_PROMOTE is NOT granted by default — must use mint_promote().
        """
        key = self._load_key(principal)
        if key is not None:
            # Load existing token by re-issuing with same key (nonce changes, but that's OK
            # for session-based resolution — the key is what persists across restarts)
            token, _ = capability.issue_token(principal, key=key)
            return HmacCapToken(token=token, key=key), key

        # First run: issue fresh token+key, persist key
        token, key = capability.issue_token(principal)
        self._store_key(principal, key)
        return HmacCapToken(token=token, key=key), key

    def verify(self, handle: HmacCapToken, key: bytes) -> VerifiedCap:
        """Verify handle, return VerifiedCap."""
        if not capability.validate(handle.token, key):
            raise capability.CapabilityError(
                f"capability token rejected: invalid signature for principal {handle.token.tenant!r}"
            )
        return VerifiedCap(
            principal=handle.token.tenant,
            cap_ref=handle.token.nonce,
            scopes=handle.token.scopes,
            _internal_cap=handle,
        )

    def require_scope(self, handle: HmacCapToken, scope: str, key: bytes) -> VerifiedCap:
        """Verify handle has `scope`, return VerifiedCap."""
        verified = self.verify(handle, key)
        if scope not in verified.scopes:
            raise capability.CapabilityError(
                f"capability token for {verified.principal!r} lacks required scope {scope!r} "
                f"(granted: {sorted(verified.scopes)})"
            )
        return verified

    def principal_of(self, verified: VerifiedCap) -> str:
        """Extract principal from verified capability."""
        return verified.principal

    def cap_ref(self, verified: VerifiedCap) -> str:
        """Extract audit reference (nonce) from verified capability."""
        return verified.cap_ref

    def mint_promote(self, principal: str) -> tuple[HmacCapToken, bytes]:
        """Issue a promote-scoped capability for principal."""
        key = self._load_key(principal)
        if key is None:
            # First run: create key
            key = secrets.token_bytes(32)
            self._store_key(principal, key)

        # Issue with WORLD_PROMOTE scope
        token, _ = capability.issue_token(
            principal,
            key=key,
            scopes=frozenset({capability.TENANT_RW, capability.WORLD_R, capability.WORLD_PROMOTE}),
        )
        return HmacCapToken(token=token, key=key), key


# ---------------------------------------------------------------------------
# TenantStore — the access router (#99 prep, built here for #98 wiring)
# ---------------------------------------------------------------------------


class TenantStore:
    """The single authorization locus for tenant-scoped vector store access.

    This is #99's access-router, built here to depend on CapabilityPort only
    (not the concrete token). The router feeds the existing checks — it's not
    a second authorizer.

    Depends on CapabilityPort only — never imports CapabilityToken or reads
    token fields. Construction takes a CapabilityPort + resolved opaque handle.
    """

    def __init__(self, port: CapabilityPort, handle: Any, key: bytes, conn: Any) -> None:
        self._port = port
        self._handle = handle
        self._key = key
        self._conn = conn

    def _verified(self) -> VerifiedCap:
        return self._port.verify(self._handle, self._key)

    def read(self, cid: str) -> Any | None:
        """Read a record by cid, gated by capability.

        Own-tenant rows: require TENANT_RW.
        World rows: require WORLD_R.
        """
        v = self._verified()
        # Gate: own-tenant rw or world r
        if capability.TENANT_RW not in v.scopes and capability.WORLD_R not in v.scopes:
            raise capability.CapabilityError(
                f"capability lacks read permission (granted: {sorted(v.scopes)})"
            )
        # Read through tenant-filtered query
        record = vector.get_record_for_tenant(self._conn, cid, v.principal)
        if record is not None:
            return record
        # Also check world tier if has WORLD_R
        if capability.WORLD_R in v.scopes:
            return vector.get_record_for_tenant(self._conn, cid, capability.WORLD_TENANT)
        return None

    def write(self, record: Any) -> None:
        """Write a record, gated by TENANT_RW scope."""
        v = self._verified()
        self._port.require_scope(self._handle, capability.TENANT_RW, self._key)
        # Ensure record.tenant matches principal (frozen dataclass -> replace)
        if hasattr(record, "tenant") and record.tenant != v.principal:
            from dataclasses import replace
            record = replace(record, tenant=v.principal)
        elif isinstance(record, dict) and record.get("tenant") != v.principal:
            record = {**record, "tenant": v.principal}
        # TenantStore is the sanctioned door: the cap is verified and the row is
        # pinned to the principal, so the privileged primitive is called with the
        # admin sentinel here (and ONLY here, for writes).
        vector.upsert_record(self._conn, record, admin=vector.ADMIN)
        self._conn.commit()

    def query(self, *, space_id: str | None = None, limit: int | None = None) -> list:
        """List this principal's rows ⊕ world rows under §1-INV, gated by read scope.

        Routes through the scoped resolver (query_for_tenant) — no admin sentinel,
        because the resolver is itself isolation-safe. This is the router path the
        §1-INV A/B sweep exercises.
        """
        v = self._verified()
        if capability.TENANT_RW not in v.scopes and capability.WORLD_R not in v.scopes:
            raise capability.CapabilityError(
                f"capability lacks read permission (granted: {sorted(v.scopes)})"
            )
        return vector.query_for_tenant(self._conn, v.principal, space_id=space_id, limit=limit)

    def promote(self, cid: str) -> dict:
        """Promote a cid to world tier, gated by WORLD_PROMOTE scope."""
        import lgwks_promote as promote
        v = self._verified()
        self._port.require_scope(self._handle, capability.WORLD_PROMOTE, self._key)
        # Delegate to lgwks_promote.promote with the internal token
        internal = v._internal_cap
        if not isinstance(internal, HmacCapToken):
            raise RuntimeError("unexpected token type in promote")
        return promote.promote(
            self._conn,
            cid,
            internal.token,
            self._key,
        )


# ---------------------------------------------------------------------------
# Convenience: resolve capability for session binding
# ---------------------------------------------------------------------------


def resolve_capability_for_tenant(tenant: str) -> tuple[HmacCapabilityPort, HmacCapToken, bytes]:
    """Resolve capability for tenant — returns (port, handle, key).

    This is the function lgwks_session.begin() calls to bind a capability
    to the session. The port persists the key in Keychain on first run.
    """
    port = HmacCapabilityPort()
    handle, key = port.resolve(tenant)
    return port, handle, key


def resolve_promote_capability_for_tenant(tenant: str) -> tuple[HmacCapabilityPort, HmacCapToken, bytes]:
    """Resolve promote-scoped capability for tenant — returns (port, handle, key).

    This is the function `lgwks promote` uses — it grants WORLD_PROMOTE.
    """
    port = HmacCapabilityPort()
    handle, key = port.mint_promote(tenant)
    return port, handle, key


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_parser(sub) -> None:
    p = sub.add_parser("access", help="capability-port access router (#98/#99)")
    ps = p.add_subparsers(dest="access_command", required=True)

    resolve_cmd = ps.add_parser("resolve", help="resolve capability for tenant")
    resolve_cmd.add_argument("--tenant", required=True, help="tenant to resolve for")
    resolve_cmd.add_argument("--promote", action="store_true", help="resolve with WORLD_PROMOTE scope")
    resolve_cmd.add_argument("--json", action="store_true", help="structured output")
    resolve_cmd.set_defaults(func=_access_resolve_command)

    promote_cmd = ps.add_parser("promote", help="promote a cid to world tier")
    promote_cmd.add_argument("cid", help="content id to promote")
    promote_cmd.add_argument("--tenant", required=True, help="tenant promoting the cid")
    promote_cmd.add_argument("--store", required=True, help="path to the vector store (.db)")
    promote_cmd.add_argument("--json", action="store_true", help="structured output")
    promote_cmd.set_defaults(func=_access_promote_command)

    verify_cmd = ps.add_parser("verify", help="verify a raw capability token")
    verify_cmd.add_argument("--token", required=True, help="JSON string or @file")
    verify_cmd.add_argument("--json", action="store_true", help="structured output")
    verify_cmd.set_defaults(func=_access_verify_command)


def _access_verify_command(args) -> int:
    import json as _json
    import lgwks_ui as ui
    import lgwks_inline
    from lgwks_capability import CapabilityToken

    on = ui.color_on()
    try:
        raw = lgwks_inline.resolve_payload(args.token)
        data = _json.loads(raw)
        
        tenant = data.get("tenant")
        if not tenant:
            raise ValueError("Token missing 'tenant' field")
            
        token = CapabilityToken(
            tenant=tenant,
            nonce=data["nonce"],
            scopes=frozenset(data["scopes"]),
            signature=data["signature"]
        )
        
        # In HmacCapabilityPort, the token is verified using the key stored in the keychain.
        # So we resolve the key for this tenant and then verify.
        port = HmacCapabilityPort()
        key = port._load_key(tenant)
        if not key:
            raise ValueError(f"No capability key found in keychain for tenant {tenant!r}")
            
        handle = HmacCapToken(token=token, key=key)
        verified = port.verify(handle, key)
        scopes = sorted(verified.scopes)
        
        if getattr(args, "json", False):
            print(_json.dumps({
                "tenant": tenant,
                "scopes": scopes,
                "cap_ref": verified.cap_ref,
                "verified": True
            }, indent=2))
        else:
            print(ui.spine(ui.fg("capability token verified", ui.EMERALD, on=on), on=on))
            print(ui.twig(f"tenant: {tenant}", 1, "info", on=on))
            print(ui.twig(f"scopes: {scopes}", 1, "info", on=on))
            print(ui.twig(f"cap_ref (nonce): {verified.cap_ref}", 1, "info", on=on))
        return 0
    except Exception as exc:
        if getattr(args, "json", False):
            print(_json.dumps({"error": str(exc), "verified": False}, indent=2))
        else:
            print(ui.spine(ui.fg(f"error: {exc}", ui.RUST, on=on), on=on), file=sys.stderr)
        return 1


def _access_resolve_command(args) -> int:
    """Resolve capability for tenant."""
    import json as _json
    import lgwks_ui as ui

    on = ui.color_on()
    tenant = args.tenant
    promote = getattr(args, "promote", False)

    try:
        if promote:
            port, handle, key = resolve_promote_capability_for_tenant(tenant)
        else:
            port, handle, key = resolve_capability_for_tenant(tenant)

        verified = port.verify(handle, key)
        scopes = sorted(verified.scopes)

        if getattr(args, "json", False):
            print(_json.dumps({
                "tenant": tenant,
                "scopes": scopes,
                "cap_ref": verified.cap_ref,
                "promote": promote,
                "key_source": "keychain",
            }, indent=2))
        else:
            print(ui.spine(ui.fg(f"capability resolved for tenant {tenant!r}", ui.EMERALD, on=on), on=on))
            print(ui.twig(f"scopes: {scopes}", 1, "info", on=on))
            print(ui.twig(f"cap_ref (nonce): {verified.cap_ref}", 1, "info", on=on))
            print(ui.twig("key stored in Keychain (lgwks:cap:{tenant})", 1, "info", on=on))
        return 0
    except Exception as exc:
        if getattr(args, "json", False):
            print(_json.dumps({"error": str(exc)}, indent=2))
        else:
            print(ui.spine(ui.fg(f"error: {exc}", ui.RUST, on=on), on=on), file=sys.stderr)
        return 1


def _access_promote_command(args) -> int:
    """Promote a cid to world tier."""
    import json as _json
    from pathlib import Path

    import lgwks_ui as ui

    on = ui.color_on()
    cid = args.cid
    tenant = args.tenant

    try:
        # Resolve promote capability
        port, handle, key = resolve_promote_capability_for_tenant(tenant)

        # Open the vector store at the operator-supplied path (no implicit default;
        # mirrors lgwks_inbound's --store contract).
        conn = vector.create_store(Path(args.store))

        # Create TenantStore and call promote
        store = TenantStore(port, handle, key, conn)
        result = store.promote(cid)

        if getattr(args, "json", False):
            print(_json.dumps(result, indent=2))
        else:
            print(ui.spine(ui.fg(f"promoted cid {cid!r} to world tier", ui.EMERALD, on=on), on=on))
            print(ui.twig(f"tenant: {result.get('tenant')}", 1, "info", on=on))
            print(ui.twig(f"audit_seq: {result.get('audit_seq')}", 1, "info", on=on))
            print(ui.twig(f"chain: {result.get('chain')}", 1, "info", on=on))

        conn.close()
        return 0
    except Exception as exc:
        if getattr(args, "json", False):
            print(_json.dumps({"error": str(exc)}, indent=2))
        else:
            print(ui.spine(ui.fg(f"error: {exc}", ui.RUST, on=on), on=on), file=sys.stderr)
        return 1
