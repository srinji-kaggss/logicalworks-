# Architecture — two-DB multi-tenant concurrency: where we lack · 2026-06-11 (session 6)

Director question (session 6): concurrency is **within one tenant AND across tenants**; the complexity is the
**two databases** — one shared world DB everyone has ("the Google") and one private DB per human+AI pair.
*"That's the security load. Think FIGMA / Google Workspace daemons. Where do we lack."* This doc answers it:
the topology, the Figma/Workspace mapping, and a code-grounded gap table. It is the umbrella for the I8/I9
packets ([PLANS-NEXT-5.md](PLANS-NEXT-5.md)); genuinely-future items go to [SCOPE-DEFERRED.md](SCOPE-DEFERRED.md).

## The topology is already specified — we lack the enforcement, not the design

`INGESTION-LAYER.md §1` already names the two tiers and the invariant. We formalize, not invent:

```
WORLD-NODES DB ("the Google")     store/substrate-global/   global, append-only, content-addressed facts
   ▲ promote (explicit, audited)                            shared by everyone; the package index / world model
TENANT / PROJECT FOLDERS          store/projects/<tenant>/  private per human+AI pair: own graph+vectors+chain
```

- **Write model (resolves the "can tenants write the Google?" question):** tenants write their **private**
  tier; content reaches the shared world DB **only by explicit, audited promotion** (§1, `▲ promote`). No
  direct tenant→world write. This is the Figma "publish to community" / Workspace "share to shared drive"
  pattern — the commons is curated by promotion, not open-write.
- **§1-INV (T0 — the security load):** a read in tenant A can **never** observe tenant B's rows; enforced by
  a **capability token verified cryptographically**, *not* `if tenant == ...`; cross-tenant flow happens
  **only** by promotion. Verify: 10⁴ randomized A/B queries → zero B-cid in any A result; every uncapped
  cross-read rejected.

## Figma / Google Workspace mapping (the mental model, made concrete)

| Workspace/Figma concept | lgwks equivalent | status |
|---|---|---|
| Shared community / org drive | world-nodes DB (`store/substrate-global/`) | dir exists; concurrency + provenance unbuilt |
| Your private file / personal drive | tenant tier (`store/projects/<tenant>/`) | dir exists; **read-isolation unenforced** |
| Multiplayer concurrent edit | CRDT merge (I9: G-Set world / OR-Set+LWW tenant) | module exists (PR #76); **not wired to the stores** |
| Publish / share-to-commons | promotion (tenant → world, audited) | **no provenance/audit record on promote** |
| Per-user background daemon | the ingestion daemon serving many tenants | single-process, in-memory queue; **drops on full** |
| ACL / who-can-open-this | capability token | exists; **single-scope, not tier-aware, not wired** |
| Per-user quota / fair share | per-tenant admission | **fail-OPEN** (RECONCILE.md:318,360) |

## Where we lack (gap table — severity · code anchor)

| # | Gap | Why it's a lack in the two-DB model | Severity | Anchor |
|---|---|---|---|---|
| **L1** | **§1-INV unenforced — A can read B today** | `get_record`/`query_by_source` never filter on `tenant`; `guard()` binds to nothing. The whole security load rests on an invariant that is asserted, not enforced. | **T0 / critical** | `lgwks_vector.py:248,260`; `lgwks_capability.py:103` |
| **L2** | **World/tenant seam not modeled in the access path** | Nothing tags an op as world-read vs tenant-read vs promote, or routes writes to the right tier. The seam is exactly where a private fact leaks to the commons or a query crosses tiers. §1 says "promotion only" but no code enforces it. | high | (no router exists) `lgwks_substrate_config.py:18` (`GLOBAL_ROOT` only) |
| **L3** | **Admission is global, not per-tenant — and fails OPEN** | One global token bucket. RECONCILE already documents the limiter runs before auth context → no tenant to limit → fail-open. One tenant can starve all others / flood the world DB. | high | `lgwks_admission.py:126`; RECONCILE.md:318,360 |
| **L4** | **Concurrency is single-process, in-memory, drop-on-full** | Workspace daemons are multi-process across many tenants; the crawler is a separate process (`crawler/src/main.rs`). An in-memory `deque` can't coordinate them and `Rejected429` *drops* work. No durable cross-process queue. | high | `lgwks_admission.py:143,154` |
| **L5** | **No provenance/audit on promotion to the world DB** | §1 calls promotion "audited" but nothing records which tenant promoted which cid, when, under what cap. Blocks abuse control, attribution, and private-view retraction. | med | (none) reuse `lgwks_cognition.py:65` chain |
| **L6** | **CRDT not deployed on the two stores** | `lgwks_crdt.py` (G-Set/OR-Set/LWW) is a tested module but not the live merge path for concurrent multi-tenant writers on `substrate-global` or concurrent human+AI on a tenant store. | med | `lgwks_crdt.py` (issue #73) |
| **L7** | **Capability token is single-scope, not tier-aware** | A real token must grant *rw on owner's tenant tier* + *r (gated promote) on the world tier*. Today it's a flat `tenant`+sig — can't express the two-DB scopes. | med | `lgwks_capability.py:48` |
| **L8** | **Cross-workspace sharing / ACL** (Figma invite, shared drives) | Sharing one tenant's private store with another principal. Not needed for the local human+AI case yet. | deferred | → SCOPE-DEFERRED.md |
| **L9** | **Network/MCP/HTTP transport + external 429 + federation** | The remote surface and cross-machine sync. "Maybe in the end, not now." | deferred | → SCOPE-DEFERRED.md |

## The hardest surface to close (build for this; the rest is free)

**The §1-INV holding under concurrent multi-tenant load** — i.e. **L1 + L2 + L7 (isolation + seam +
tier-scoped caps) enforced through L3 + L4 (per-tenant durable concurrency).** This is where Figma/Workspace
spend their hardest engineering: the boundary must hold not just for a single sequential read but under many
concurrent daemons, mid-crash, with no work dropped and no tenant starved. If the access layer is built so
**every store op is (a) tier-tagged, (b) capability-verified, (c) tenant-filtered at the store for private
reads, (d) per-tenant admission-controlled — and the §1-INV is proven against the live two-tier store under
concurrent load** — then the single-operator single-tenant case is a trivial special case, and the later
network/MCP surface only adds a transport adapter in front of an already-safe core.

## How this threads into the packets
- **I8 (#72) — does the hard surface:** the tier-routing access layer + tenant-scoped private reads (L1/L2),
  tier-scoped capability (L7), per-tenant durable no-drop fair queue (L3/L4, fixes fail-open), and a minimal
  promotion-audit record (L5). Spec: [PLANS-NEXT-5.md](PLANS-NEXT-5.md). Build order inside I8: enforce the
  invariant (L1/L2) → per-tenant admission (L3) → durable concurrency (L4) → promotion audit (L5).
- **I9 (#73) — deploys CRDT (L6):** G-Set as the world-DB convergence, OR-Set/LWW as the tenant-DB
  convergence, wired to the live stores so concurrent writers (multi-tenant on world, human+AI on tenant)
  converge byte-identically. The queue (I8) must hand work to CRDT-merge commits.
- **Deferred (L8/L9):** SCOPE-DEFERRED.md.
