"""lgwks_promote — audited tenant→world promotion (ARCH L5, I8-hardening #89).

The tenant→world write is the ONLY cross-tier path in the two-DB model
(ARCH-two-db-multitenant.md §1, L5). This module makes that path auditable:
every promotion is gated by the `world:promote` capability scope (L7) and logged
as a hash-chained record on the cognition chain (lgwks_cognition) — who (tenant +
cap nonce), what (cid + source_cid + space_id), when (chain ts), under-which-cap
(scope + nonce). The audit is a precondition for the move committing, so no
promotion is ever durable without its provenance record.

Authority: spec/second-harness/ARCH-two-db-multitenant.md (gap L5)
           spec/second-harness/HANDOFF.md (session 10 — L5 tail of #89)
Consumes:  lgwks.capability.v2 (WORLD_PROMOTE scope), lgwks_cognition ("promotion" kind)
Issue:     I8-hardening (#89)

Design:
    D1: promotion is a MOVE (tenant T -> 'world'), not a copy. The cid is
        content-addressed over (source_cid, modality, space_id, embedding) and
        does NOT include tenant (lgwks_vector._canonical_bytes), so a copy would
        collide on the cid PK. The same content-addressed fact is reassigned to
        the shared tier — the Figma "publish to community" semantic.
    D2: gated by require_scope(WORLD_PROMOTE). The scope is inside the signed
        capability payload (L7), so a tenant cannot widen its own grant to promote.
    D3: own-row only. A tenant can promote only a row it owns; promoting another
        tenant's row or a world row is refused. The refusal message does not
        distinguish not-found from not-owned — no existence side-channel (matches
        lgwks_vector.get_record_for_tenant's None-not-raise contract).
    D4: no raw secret in the audit. The cap is identified by its nonce; the
        signing key never enters the log.
    D5: audit-gates-commit ordering. Stage the move (no commit) -> verify exactly
        one owned row staged -> append the audit -> commit. Any refusal raises
        BEFORE an audit is written (no chain spam, no silent failure). On any
        exception the staged move is rolled back.
"""

from __future__ import annotations

from typing import Optional

import lgwks_capability as capability
import lgwks_cognition as cognition
import lgwks_vector as vector


class PromotionError(PermissionError):
    """Raised when a promotion is refused or cannot be completed atomically."""


# Unified refusal — does not reveal whether the cid exists under another tenant
# (closes the existence side-channel; see D3).
_NOT_PROMOTABLE = "cid not promotable by this tenant (not found in your tier or not owned)"


def promote(
    conn,
    cid: str,
    token: capability.CapabilityToken,
    key: bytes,
    *,
    stream: str = "main",
    cognition_key: Optional[bytes] = None,
) -> dict:
    """Promote one of `token.tenant`'s private records (by cid) to the world tier.

    Gated by the WORLD_PROMOTE scope (require_scope); on success the row's tenant
    flips T -> 'world' and an audited "promotion" record is appended to the
    cognition chain `stream`. Returns the audit summary
    {schema, promoted, tenant, source_cid, space_id, scope, nonce, audit_seq,
     audit_hash, chain}.

    Raises capability.CapabilityError if the token is invalid or lacks
    WORLD_PROMOTE. Raises PromotionError if the cid is not a promotable owned row,
    or if the audit could not be committed atomically with the move.

    key            — capability signing key (verifies the token).
    cognition_key  — optional explicit cognition signing key; default uses
                     lgwks_sign.signing_key() (keyed or unanchored, surfaced there).

    Transaction ownership: promote() COMMITS (on success) or ROLLS BACK (on
    failure) `conn`. The caller must not have other uncommitted writes pending on
    the same connection — promote owns the transaction boundary for this op. This
    relies on a non-autocommit connection (lgwks_vector.create_store /
    lgwks_sqlite.connect use the default isolation_level, so DML stages until
    commit); on an autocommit connection the rollback guarantee below would not hold.

    Honest limit (the one orphan-audit window): the cognition audit and the vector
    store are two stores with no shared transaction. The ordering writes the audit
    BEFORE committing the move, so a committed promotion ALWAYS has a durable audit.
    The reverse edge — audit appended, then conn.commit() itself fails — leaves an
    orphan audit (a logged promotion whose world row was rolled back). That is the
    safe direction (no isolation breach; reconcilable: an audit cid not at
    tenant='world' is a rolled-back promotion) and is surfaced by the raised error.
    """

    def _do(tenant: str) -> dict:
        # Pre-check ownership on an UNSCOPED read: we must see the row's real
        # tenant to verify it is T's own (not world, not another tenant's). The
        # WORLD_PROMOTE scope already authorised this privileged inspection.
        record = vector.get_record(conn, cid)
        if record is None or record.tenant != tenant:
            # Same message whether absent or foreign-owned — no existence leak (D3).
            raise PromotionError(_NOT_PROMOTABLE)

        # Stage the move (no commit yet) — audit must land before this is durable.
        try:
            moved = vector.promote_cid_to_world(conn, cid, tenant)
            if not moved:
                # Lost a race between the read and the update (e.g. concurrently
                # promoted/deleted). Nothing committed, no audit written.
                conn.rollback()
                raise PromotionError(_NOT_PROMOTABLE)

            log = cognition.CognitionLog(stream, key=cognition_key)
            entry = log.append("promotion", {
                "tenant": tenant,
                "cid": cid,
                "source_cid": record.source_cid,
                "space_id": record.space_id,
                "scope": capability.WORLD_PROMOTE,
                "nonce": token.nonce,
            })
            conn.commit()
        except PromotionError:
            raise
        except Exception as exc:
            # Audit append or commit failed — undo the staged move so we never
            # have a committed promotion without a durable audit (D5).
            conn.rollback()
            raise PromotionError(f"promotion aborted, move rolled back: {exc}") from exc

        return {
            "schema": vector.SCHEMA,
            "promoted": cid,
            "tenant": tenant,
            "source_cid": record.source_cid,
            "space_id": record.space_id,
            "scope": capability.WORLD_PROMOTE,
            "nonce": token.nonce,
            "audit_seq": entry["seq"],
            "audit_hash": entry["hash"],
            "chain": stream,
        }

    return capability.require_scope(token, capability.WORLD_PROMOTE, _do, key)
