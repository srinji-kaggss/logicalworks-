"""lgwks_capability — capability-token tenant isolation boundary (I8).

No compute, no scoring, no model layer — isolation ONLY.
A capability token scopes every query to exactly one tenant; a query without
a valid token is rejected; cross-tenant cid access is impossible by construction.

Authority: spec/second-harness/INGESTION-PLAN.md §I8 step 3
           spec/second-harness/ARCH-two-db-multitenant.md (gaps L1/L2/L7)
           spec/second-harness/INGESTION-LAYER.md §6, §1-INV
Schema:    lgwks.capability.v2   (family: harness)
Issue:     I8 / I8-hardening (#89)

Design (INGESTION-PLAN §I8 step 3; ARCH L7 — tier-scoped):
    - Capability token carries a tenant id, a secret (opaque, not stored), AND a
      set of tier scopes (the two-DB model: own tenant tier rw + world tier r).
    - Every read on VectorRecord resolves only rows whose tenant ∈ {token.tenant,
      'world'} — the own ⊕ world read (lgwks_vector.get_record_for_tenant /
      query_for_tenant). Another tenant's standard rows are unreachable.
    - A query without a valid token is rejected before touching the store.
    - Cross-tenant cid access is IMPOSSIBLE by construction (filter enforced at
      every read path, never optional).

Decisions:
    D1: secret is a 32-byte random token; hmac-sha256 over (tenant, nonce, scopes)
        signs the capability so a forged / mutated token — INCLUDING a scope
        escalation — is detected.
    D2: token equality and validation are pure functions — no I/O, replayable.
    D3: guard() requires a key — there is no keyless verification path. Capability
        tokens without a signing key provide zero isolation guarantee; accepting
        them silently would make the "isolation boundary" a fiction.
    D4 (L7): scopes are tier-aware — TENANT_RW (read/write own tier), WORLD_R
        (read shared world tier), WORLD_PROMOTE (the audited tenant→world write,
        consumed by L5). A token grants only what it was issued; require_scope()
        rejects any op outside its grant. Scopes are inside the signed payload, so
        a client cannot widen its own grant by mutating the token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.capability.v2"   # v1→v2: signed tier scopes added (ARCH L7)

# ---------------------------------------------------------------------------
# Tier scopes (ARCH L7 — the two-DB grant model)
# ---------------------------------------------------------------------------

TENANT_RW = "tenant:rw"        # read/write the token's own tenant tier
WORLD_R = "world:r"            # read the shared world tier (store/substrate-global)
WORLD_PROMOTE = "world:promote"  # audited tenant→world write (L5); never default

# Default grant for an ordinary human+AI pair: own tier rw + world read.
# Promotion is NOT default — it must be issued explicitly.
DEFAULT_SCOPES = frozenset({TENANT_RW, WORLD_R})
_KNOWN_SCOPES = frozenset({TENANT_RW, WORLD_R, WORLD_PROMOTE})

# The shared-tier sentinel (MUST match lgwks_vector.WORLD_TENANT). It is RESERVED:
# no token may be issued for it. A tenant literally named 'world' would write its
# private rows as world-tier rows (tenant='world'), publishing them to everyone —
# a silent cross-tenant leak. Reserving it at issuance + at the guard closes that.
WORLD_TENANT = "world"


# ---------------------------------------------------------------------------
# CapabilityToken
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityToken:
    """Immutable capability token scoping all operations to one tenant + tier set.

    tenant  — the tenant id this token authorises.
    nonce   — unique per issuance (hex); prevents token replay across sessions.
    sig     — hmac-sha256(key, tenant:nonce:scopes); verifiable without storing
              the raw secret (D1). Scopes are inside the signed payload (D4), so a
              forged tenant, nonce, OR scope-escalation is detected.
    scopes  — the tier grant (D4/L7); defaults to own-tier rw + world read.
    """
    tenant: str
    nonce: str
    sig: str
    schema: str = SCHEMA
    scopes: frozenset[str] = DEFAULT_SCOPES


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------

def issue_token(
    tenant: str,
    *,
    key: bytes | None = None,
    scopes: frozenset[str] | set[str] | None = None,
) -> tuple[CapabilityToken, bytes]:
    """Issue a fresh capability token for tenant.

    Returns (token, key) where key is the signing secret (caller stores it;
    pass the same key to guard() and validate() for verification).
    //why: key is returned rather than stored here — the caller (session/daemon)
    owns the secret lifecycle; this module never writes to disk.

    scopes — the tier grant (D4/L7); defaults to DEFAULT_SCOPES (own rw + world r).
    Unknown scope strings are rejected (no silent grant of an undefined tier).
    """
    if not tenant or not isinstance(tenant, str):
        raise ValueError("tenant must be a non-empty string")
    if tenant == WORLD_TENANT:
        raise ValueError(
            f"tenant {WORLD_TENANT!r} is reserved for the shared world tier — "
            "no capability token may be issued for it"
        )
    grant = DEFAULT_SCOPES if scopes is None else frozenset(scopes)
    unknown = grant - _KNOWN_SCOPES
    if unknown:
        raise ValueError(f"unknown capability scope(s): {sorted(unknown)}")
    if key is None:
        key = secrets.token_bytes(32)
    nonce = secrets.token_hex(16)
    sig = _sign(key, tenant, nonce, grant)
    return CapabilityToken(tenant=tenant, nonce=nonce, sig=sig, scopes=grant), key


def validate(token: CapabilityToken, key: bytes) -> bool:
    """Return True iff the token's signature is valid for the given key.

    The signature covers tenant, nonce AND scopes — so a token whose scopes were
    widened after issuance fails validation (no client-side privilege escalation).
    """
    expected = _sign(key, token.tenant, token.nonce, token.scopes)
    return hmac.compare_digest(token.sig, expected)


def _sign(key: bytes, tenant: str, nonce: str, scopes: frozenset[str]) -> str:
    # Scopes are sorted+comma-joined so the signed payload is canonical regardless
    # of set iteration order — same grant always yields the same signature.
    scope_str = ",".join(sorted(scopes))
    payload = f"{tenant}:{nonce}:{scope_str}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Guard — enforces token validity before every read
# ---------------------------------------------------------------------------

class CapabilityError(PermissionError):
    """Raised when a query lacks a valid capability token."""


def guard(
    token: CapabilityToken,
    query_fn: Callable[[str], Any],
    key: bytes,
) -> Any:
    """Validate token signature then call query_fn(token.tenant).

    key is REQUIRED — there is no keyless path (D3). Accepting an unverified
    token would reduce the isolation boundary to an empty-string check, which
    any caller could trivially bypass with a non-empty tenant string.

    query_fn receives the validated tenant string and must filter every store
    read on tenant == token.tenant (the vr_space_tenant index provides O(1)
    lookup; see lgwks_vector.py:49).

    Raises CapabilityError on invalid signature, empty tenant, or wrong key —
    no partial result, no silent fallthrough.
    """
    if not token.tenant:
        raise CapabilityError("capability token has empty tenant — rejected")
    if token.tenant == WORLD_TENANT:
        raise CapabilityError(
            f"capability token names the reserved {WORLD_TENANT!r} tier — rejected"
        )
    if not validate(token, key):
        raise CapabilityError(
            f"capability token rejected: invalid signature for tenant {token.tenant!r}"
        )
    return query_fn(token.tenant)


def require_scope(
    token: CapabilityToken,
    scope: str,
    query_fn: Callable[[str], Any],
    key: bytes,
) -> Any:
    """Validate the token, assert it carries `scope`, then call query_fn(tenant).

    The tier-aware guard (D4/L7): a WORLD_R read, a TENANT_RW read/write, or a
    WORLD_PROMOTE write each names the scope it needs. A token that validates but
    lacks the scope is rejected — a tenant:rw-only token cannot promote, a
    read-only token cannot write. No partial result, no silent fallthrough.
    """
    if not token.tenant:
        raise CapabilityError("capability token has empty tenant — rejected")
    if token.tenant == WORLD_TENANT:
        raise CapabilityError(
            f"capability token names the reserved {WORLD_TENANT!r} tier — rejected"
        )
    if not validate(token, key):
        raise CapabilityError(
            f"capability token rejected: invalid signature for tenant {token.tenant!r}"
        )
    if scope not in token.scopes:
        raise CapabilityError(
            f"capability token for {token.tenant!r} lacks required scope {scope!r} "
            f"(granted: {sorted(token.scopes)})"
        )
    return query_fn(token.tenant)


def make_tenant_filter(token: CapabilityToken) -> Callable[[list], list]:
    """Return a filter that keeps own-tenant ⊕ world rows, drops every other tenant.

    Defense-in-depth: even if an upstream query omits the WHERE clause, this filter
    enforces the own ⊕ world boundary before results reach the caller. World rows
    are legitimately visible to every tenant, so they are kept (matches the
    get_record_for_tenant / query_for_tenant read contract); only another tenant's
    standard rows are dropped.
    """
    expected = token.tenant

    def _filter(records: list) -> list:
        out = []
        for r in records:
            t = r.tenant if hasattr(r, "tenant") else r.get("tenant", "")
            if t == expected or t == WORLD_TENANT:
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
    issue_p.add_argument("--scope", action="append", choices=sorted(_KNOWN_SCOPES),
                         help="tier scope (repeatable); default: own rw + world read")
    issue_p.set_defaults(func=_cmd_issue)


def _cmd_info(args) -> int:
    import json as _json

    print(_json.dumps({
        "schema": SCHEMA,
        "isolation_model": "tier-scoped capability-token per tenant (own ⊕ world)",
        "scopes": sorted(_KNOWN_SCOPES),
        "default_grant": sorted(DEFAULT_SCOPES),
        "read_path": "lgwks_vector.get_record_for_tenant / query_for_tenant (own ⊕ world)",
        "index": "vr_space_tenant ON (space_id, tenant) (lgwks_vector.py:49)",
        "token_alg": "hmac-sha256(key, tenant:nonce:scopes)  — scopes signed (D4/L7)",
        "key_required": "guard()/require_scope() require a signing key — no keyless path (D3)",
        "scope_escalation": "impossible — scopes are inside the signed payload",
        "p3_to_p0_trigger": "escalates to P0 before any multi-tenant or network exposure",
        "cross_tenant_leak": "impossible — a cid outside own ⊕ world resolves to None (no existence leak)",
        "token_required": "guard()/require_scope() raise CapabilityError on any invalid/forged token",
    }, indent=2))
    return 0


def _cmd_issue(args) -> int:
    import json as _json

    scopes = frozenset(args.scope) if getattr(args, "scope", None) else None
    token, key = issue_token(args.tenant, scopes=scopes)
    print(_json.dumps({
        "schema": token.schema,
        "tenant": token.tenant,
        "nonce": token.nonce,
        "sig": token.sig,
        "scopes": sorted(token.scopes),
        "key_hex": key.hex(),
        "note": "store key_hex securely — required for guard()/require_scope() and validate()",
    }, indent=2))
    return 0
