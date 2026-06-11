# Scope-deferred ledger — logged out of the I8/I9 multi-tenant work · 2026-06-11 (session 6)

Per Director directive (session 6): *"Assume local ops but maybe mcp or http in the end not now. Any scope
creep should be logged sep."* This is that ledger. Items here are **real and intended eventually**, but
explicitly **out of scope** for the current I8 (multi-tenant concurrency + isolation) and I9 (CRDT
deployment) packets. They are parked, not forgotten. Authority: [ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md)
(gap L8/L9), [PLANS-NEXT-5.md](PLANS-NEXT-5.md) scope fences.

Promote an item out of this ledger by filing a GH issue; do not fold it back into I8/I9 mid-flight.

| id | deferred item | why parked now | trigger to revisit | depends on |
|----|---------------|----------------|--------------------|------------|
| **D1** | **External 429 + Retry-After path** (the boilerplate's `Rejected429`) | Internal producers get backpressure (never drop). 429 is a *client-retries* contract — only meaningful for an external caller. | first network/MCP/HTTP endpoint | I8 core (queue) |
| **D2** | **Network / MCP / HTTP transport** — a remote surface in front of the engine | "Maybe in the end, not now." The local core must be concurrency- and isolation-safe first; transport is then a thin adapter over an already-safe core (ARCH §"hardest surface"). | decision to expose beyond localhost | I8 (isolation + admission proven) |
| **D3** | **Cross-workspace sharing / ACL** (Figma multiplayer invite; Workspace shared drives) — share one tenant's private store with another principal | The local human+AI pair needs hard isolation, not sharing, first. Sharing is an ACL layer *on top of* a proven §1-INV. | a real "invite B into A's workspace" requirement | I8 (tier-scoped caps L7), I9 (CRDT) |
| **D4** | **Cross-machine federation / sync transport** — moving CRDT state between hosts | I9 builds the *merge semantics* (coordination-free by design); the *transport* that ships bytes between machines is a separate concern (I9 scope fence). | second host / device sync | I9 (CRDT merge live) |
| **D5** | **Promotion governance UI / review** — human approval flow for tenant→world promotion | I8 L5 records promotion provenance (who/what/when). A *review/approval* workflow on top is product surface, not the isolation core. | multi-operator world DB curation | I8 L5 (audit record) |
| **D6** | **Per-tenant resource accounting / billing** — cost attribution per tenant | Per-tenant admission (I8 L3) gives the fairness primitive; turning fair-share into accounting/quotas/billing is a separate product concern. | multi-tenant operation at cost | I8 L3 (per-tenant buckets) |

## Not scope creep — confirmations (so they are not re-litigated)
- The world DB is **promotion-only** (no direct tenant write) — this is `INGESTION-LAYER §1`, not a new
  decision. Direct-write-to-world is explicitly **not** a deferred option; it is rejected by the model.
- Tenant isolation (§1-INV) is **NOT** deferred — it is the security load and is core to I8 now.
