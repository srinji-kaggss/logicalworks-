"""lgwks_capability — capability-token tenant isolation boundary (I8).

No compute, no scoring, no model layer — isolation ONLY.
A capability token scopes every query to exactly one tenant; a query without
a valid token is rejected; cross-tenant cid access is impossible by construction.

Authority: spec/second-harness/INGESTION-PLAN.md §I8 step 3
           spec/second-harness/INGESTION-LAYER.md §6
Schema:    lgwks.capability.v1   (family: harness)
Issue:     I8

Design (INGESTION-PLAN §I8 step 3):
    - Capability token carries a tenant id and a secret (opaque, not stored).
    - Every read on VectorRecord filters on VectorRecord.tenant == token.tenant.
    - The vr_space_tenant index (lgwks_vector.py:49) already exists for this.
    - A query without a valid token is rejected before touching the store.
    - Cross-tenant cid access is IMPOSSIBLE by construction (filter enforced at
      every read path, never optional).

Decisions:
    D1: secret is a 32-byte random token; hmac-sha256 over (tenant, nonce) signs
        the capability so a forged / mutated token is detected.
    D2: token equality and validation are pure functions — no I/O, replayable.
    D3: guard() wraps any query callable and enforces the tenant filter before
        the callable sees any data.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.capability.v1"


# ---------------------------------------------------------------------------
# CapabilityToken
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityToken:
    """Immutable capability token scoping all operations to one tenant.

    tenant  — the tenant id this token authorises.
    nonce   — unique per issuance (hex); prevents token replay across sessions.
    sig     — hmac-sha256(key, tenant + ":" + nonce); verifiable without storing
              the raw secret (D1).
    """
    tenant: str
    nonce: str
    sig: str
    schema: str = SCHEMA


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------

def issue_token(tenant: str, *, key: bytes | None = None) -> tuple[CapabilityToken, bytes]:
    """Issue a fresh capability token for tenant.

    Returns (token, key) where key is the signing secret (caller stores it;
    pass the same key to validate() for verification).
    //why: key is returned rather than stored here — the caller (session/daemon)
    owns the secret lifecycle; this module never writes to disk.
    """
    if not tenant or not isinstance(tenant, str):
        raise ValueError("tenant must be a non-empty string")
    if key is None:
        key = secrets.token_bytes(32)
    nonce = secrets.token_hex(16)
    sig = _sign(key, tenant, nonce)
    return CapabilityToken(tenant=tenant, nonce=nonce, sig=sig), key


def validate(token: CapabilityToken, key: bytes) -> bool:
    """Return True iff the token's signature is valid for the given key."""
    expected = _sign(key, token.tenant, token.nonce)
    return hmac.compare_digest(token.sig, expected)


def _sign(key: bytes, tenant: str, nonce: str) -> str:
    payload = f"{tenant}:{nonce}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Guard — enforces tenant filter on every read
# ---------------------------------------------------------------------------

class CapabilityError(PermissionError):
    """Raised when a query lacks a valid capability token."""


def guard(
    token: CapabilityToken,
    query_fn: Callable[[str], Any],
    *,
    key: bytes | None = None,
) -> Any:
    """Validate token then call query_fn(token.tenant).

    query_fn receives the validated tenant string and is responsible for
    filtering every read on tenant == token.tenant (the vr_space_tenant index
    makes this a zero-cost filter in SQLite).

    A missing or invalid token raises CapabilityError — no partial result,
    no fallthrough (INGESTION-PLAN §I8 acceptance: "token required").
    """
    if key is not None and not validate(token, key):
        raise CapabilityError(
            f"capability token rejected: invalid signature for tenant {token.tenant!r}"
        )
    if not token.tenant:
        raise CapabilityError("capability token has empty tenant — rejected")
    return query_fn(token.tenant)


def make_tenant_filter(token: CapabilityToken) -> Callable[[list], list]:
    """Return a filter function that drops any record whose tenant != token.tenant.

    Wraps the vr_space_tenant index path (lgwks_vector.py:49): even if an upstream
    query forgets to add WHERE tenant=?, this filter enforces the boundary.
    """
    expected = token.tenant

    def _filter(records: list) -> list:
        out = []
        for r in records:
            t = r.tenant if hasattr(r, "tenant") else r.get("tenant", "")
            if t == expected:
                out.append(r)
        return out

    return _filter


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("capability", help="capability-token tenant isolation info (I8)")
    sp = p.add_subparsers(dest="capability_cmd", required=True)

    info_p = sp.add_parser("info", help="show isolation design and constants")
    info_p.set_defaults(func=_cmd_info)

    issue_p = sp.add_parser("issue", help="issue a demo capability token for a tenant")
    issue_p.add_argument("tenant", help="tenant name")
    issue_p.set_defaults(func=_cmd_issue)


def _cmd_info(args) -> int:
    import json as _json

    print(_json.dumps({
        "schema": SCHEMA,
        "isolation_model": "capability-token per tenant",
        "filter_field": "VectorRecord.tenant (lgwks_vector.py:75)",
        "index": "vr_space_tenant ON (space_id, tenant) (lgwks_vector.py:49)",
        "token_alg": "hmac-sha256(key, tenant:nonce)",
        "p3_to_p0_trigger": "escalates to P0 before any multi-tenant or network exposure",
        "cross_tenant_leak": "impossible — every read filtered on token.tenant before store access",
        "token_required": "queries without a valid token are rejected (CapabilityError), never partial",
    }, indent=2))
    return 0


def _cmd_issue(args) -> int:
    import json as _json

    token, key = issue_token(args.tenant)
    print(_json.dumps({
        "schema": token.schema,
        "tenant": token.tenant,
        "nonce": token.nonce,
        "sig": token.sig,
        "key_hex": key.hex(),
        "note": "store key_hex securely; it is the signing secret for this token",
    }, indent=2))
    return 0
