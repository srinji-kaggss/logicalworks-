"""
The decidable click — the trust core. A capsule attaches IFF this returns ok. Pure, decidable, 0-AI,
edge-runnable: enum membership + capability-lattice ⊆ + interval bounds + base-first existence. No
theorem-proving, no model. SPEC §4.

Independent of the fabric: it takes a `resolve` callable (cid -> Capsule | None). The fabric (C7)
guarantees CID integrity on store (AUDIT F-01), so a resolved base is the genuine content of that CID.
Bases are immutable and never deleted (SPEC §14 git-model), so base-first = "the base CID EXISTS" —
nothing is ever stranded.

Capability is a real lattice rooted at a signed genesis (AUDIT F-03):
  - genesis capsule: its grants are authoritative ONLY if its HMAC signature verifies against trusted_key;
    an unsigned/forged genesis grants nothing (fail-closed).
  - non-genesis capsule: effective grants = declared grants ∩ what its lineage actually carries. Declaring
    grants beyond the lineage is forgery and REJECTS the capsule (you may re-grant only what you hold).
  - a capsule's `needs` must be ⊆ its lineage grants.
Holes (grants=∅, needs=∅ — enforced in capsule.py) pass needs/grants trivially and contribute ∅ to lineage,
so the F-02 laundering is structurally impossible. There is NO string self-grant path (AUDIT F-03).

stdlib-only; imports only sibling capsule.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace
from typing import Callable, Optional

from .capsule import Capsule, KINDS, EFFECTFUL

Resolver = Callable[[str], Optional[Capsule]]
_MAX_DEPTH = 256  # lineage recursion guard (DAG is acyclic by content-addressing, but bound it anyway)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""
    requires_confirm: bool = False  # effectful kinds route to human even when the click passes (SPEC §8)


def verify_signature(capsule: Capsule, trusted_key: Optional[bytes]) -> bool:
    """HMAC attestation over the capsule's unsigned canonical bytes (stdlib stand-in for ed25519).
    A genesis capsule's grants are authoritative only if this is True."""
    if not trusted_key or not capsule.signature:
        return False
    unsigned = replace(capsule, signature=b"").to_bytes()
    expected = hmac.new(trusted_key, unsigned, hashlib.blake2b).digest()
    return hmac.compare_digest(expected, capsule.signature)


def effective_grants(capsule: Capsule, resolve: Resolver, trusted_key: Optional[bytes], _depth: int = 0) -> frozenset[str]:
    """The capabilities this capsule legitimately carries downstream (rooted at signed genesis)."""
    if _depth > _MAX_DEPTH:
        return frozenset()
    if capsule.is_genesis:
        return frozenset(capsule.grants) if verify_signature(capsule, trusted_key) else frozenset()
    lineage: set[str] = set()
    for base_cid in capsule.on:
        base = resolve(base_cid)
        if base is not None:
            lineage |= effective_grants(base, resolve, trusted_key, _depth + 1)
    return frozenset(capsule.grants) & lineage  # re-grant only what the lineage actually carried


def verify(capsule: Capsule, resolve: Resolver, trusted_key: Optional[bytes] = None) -> Verdict:
    # structural invariants (hole grants/needs=∅, non-empty kind) — malformed cannot click
    try:
        capsule.validate_structure()
    except Exception as e:  # CapsuleError
        return Verdict(False, f"malformed capsule: {e}")

    # (1) kind ∈ closed vocabulary
    if capsule.kind not in KINDS:
        return Verdict(False, f"unknown kind '{capsule.kind}' (not in closed vocabulary)")

    # (2) base-first by EXISTENCE (immutable DAG → never stranded)
    for base_cid in capsule.on:
        if resolve(base_cid) is None:
            return Verdict(False, f"base '{base_cid}' does not exist (base-first violation)")

    # (3) genesis must be signed to carry authority
    if capsule.is_genesis and capsule.grants and not verify_signature(capsule, trusted_key):
        return Verdict(False, "unsigned/forged genesis grants no authority")

    # (4) lineage grants, and the capability lattice checks
    lineage: set[str] = set()
    for base_cid in capsule.on:
        base = resolve(base_cid)
        if base is not None:
            lineage |= effective_grants(base, resolve, trusted_key)

    if not capsule.is_genesis:
        # forgery check: cannot grant beyond what the lineage carried (AUDIT F-03)
        forged = set(capsule.grants) - lineage
        if forged:
            return Verdict(False, f"grants exceed lineage (forgery): {sorted(forged)}")

    # needs must be carried by the lineage (genesis self-satisfies via its own authoritative grants)
    available = set(capsule.grants) if capsule.is_genesis else lineage
    missing = set(capsule.needs) - available
    if missing:
        return Verdict(False, f"capability not in lineage: {sorted(missing)}")

    # (5) interval bounds (NaN/Inf already impossible — capsule.py rejects them at encode)
    for name, (val, lo, hi) in capsule.params.items():
        if not (lo <= val <= hi):
            return Verdict(False, f"param '{name}'={val} out of [{lo},{hi}]")

    return Verdict(ok=True, requires_confirm=capsule.kind in EFFECTFUL)
