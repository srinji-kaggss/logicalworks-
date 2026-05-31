# LogicalWorks Language — Reconcile-First Design Doc (v0.1 draft)

> **Status:** DRAFT — §1–§6 complete. §5 anchors filled from a live read of
> `~/sales-landing-page @ 2e4d09d` (3 agents). Remaining before spec: director sign-off on the
> contradiction ledger (§3) and the sequencing fork (§7.1).
>
> **Core thesis the anchors confirmed:** the Canvas codebase already reaches for every target shape
> (schema-first ABI, actor/broker effect model, `MotionGraph` persistent node-graph, `ConfirmToken`
> proto-linear resource, `TrustBin` non-orderable, `no_std` WASM-small floor, fail-closed defaults)
> — but enforces them at **runtime convention**, leaving holes (forgeable JWT, dead capability
> check, `AssertSqlSafe` injection, ambient auth, fail-open rate-limit ordering). **The language's
> job is to lift these conventions into compile-time invariants** so the holes become unspellable.
>
> **Purpose (director's call, 2026-05-28):** merge every conflicting research artifact into ONE
> contradiction-free design, bound to real Canvas code, *before* writing the language spec.
>
> **Supersedes for design intent:** the scattered SCOPE.md / YAML / JSON research. Canonical
> two-idea design lives in memory `synetheier-language.md`; this doc is its reconciled, grounded
> expansion.

---

## §1 — Identity (LOCKED)

It is a **real, standalone, general-purpose programming language** — Go/Swift/Rust class — that
apps *and* the LogicalWorks platform are written in. It must stand on its own as a language.

**Why build our own** (the only two differentiators that justify a new language):
1. **Optimized for how our app is AI-generated** — the language makes AI "slop" structurally
   unrepresentable, not merely discouraged. The control-plane/cognition primitives (intent,
   risk, evidence, gate, provenance) are *baked into the language*, not a separate orchestration
   product.
2. **Optimized for writing code for our ecosystem/OS (Canvas)** — first-class fit with the
   Canvas substrate: capability gates, envelope/broker routing, node-mesh, schema-first kernel
   ABI, local-first governed data.

**It is NOT** (all four conflations the research kept drifting into — rejected):
- ❌ a control-plane-over-agents product *as its identity* (it's a language; the control-plane
  is the AI-semantics layer *inside* it — see §4)
- ❌ a translation/semantics service (`Untitled document-9.md`'s GNOSS/TypeDB/MUSE framing)
- ❌ a frontend-only DSL
- ❌ an execution substrate alone

**Deployment arc:** ChromeOS-style day-1 (software layer over existing OSes/web, lowers to
Rust→WASM + native) → dedicated hardware day-2 (own OS/silicon; our IR is the portable contract).

---

## §2 — Source artifact inventory + verdict

Every input, what it actually is, and what survives the reconcile.

| Source | What it is | Verdict | Lands as |
|---|---|---|---|
| memory `synetheier-language.md` | The canonical 2-idea design | ✅ Canonical | The spine (§4) |
| `Independent AI Insight.yaml` | Control-plane-for-cognition model (Intent/Context/Risk/Plan/Patch/Evidence/Memory/Gate; declare→…→package; semantic types; primitives) | ✅ Gold, **demoted from identity to layer** | **AI-semantics layer** (§4.2) |
| `Research1.yaml` / `logical_works_gh_issues_ai_overview.md` | Canvas backlog reality + dependency DAG + independent insights | ✅ Ground truth | §5 binding + §6 trends |
| `extract-data-…-2.json` | Exec substrate: WebGPU/WGSL, WASM+SAB, AI-native patterns, sandboxing (Firecracker/gVisor) | 🟡 Currency-sensitive | **Execution layer** notes (§4.4) |
| `extract-data-…-3.json` | "Binary DNA": interaction-combinator/HVM ISA, state-caging, WSKG | 🟡 Speculative | Day-2 IR candidates only (§4.4) |
| `extract-data-….json` | WebGPU/WASM/GSAP M2M render topology | 🟡 Narrow | Frontend/render target note |
| `Untitled document-9.md` | Neurosymbolic deterministic-translation frameworks | 🔴 Rejected framing | Reference only; do not let it re-define identity |
| `vision/research/machine-first-language/SCOPE.md` | Earlier machine-first substrate scope | ✅ Mostly absorbed | Design constraints (§4) |
| `vision/research/frontend-language/SCOPE.md` | Earlier frontend-DSL scope ("NodeUI") | 🟡 Partly absorbed | Render-target track; identity superseded |

---

## §3 — Contradiction ledger (must be contradiction-free before spec)

| # | Contradiction across artifacts | Resolution |
|---|---|---|
| C1 | Control-plane model says "Kubernetes for cognition" (the language IS the agent control plane) vs locked identity = standalone general-purpose language | **Standalone language wins.** Control-plane primitives are the *AI-semantics layer* compiled into a real language. Director: "needs to work as a standalone language." |
| C2 | `Untitled document-9.md` frames it as a deterministic translation/lexicon service | **Rejected.** Not the identity. Neurosymbolic determinism is an *influence* on the type/proof layer, not the product. |
| C3 | Exec substrate research pushes WebGPU/HVM/interaction-combinators as the core | **Day-1 = lower to Rust→WASM (proven).** HVM/interaction-combinators + own typed IR = day-2 maturity option, not now. WebGPU = compute/render concern (horizontal), not the language core. |
| C4 | "Neural mesh / everything flows by default" vs "no FTL, light-cone-bound, two hard walls" | **Classical mesh only.** No-communication theorem holds: CRDT/causality-bound sync. Two walls (PII vault + capability curbs) are non-negotiable. |
| C5 | "Quantum-native / stateless" vs "no broad fault-tolerant quantum advantage yet" | **Quantum-READY, not quantum-now.** Linear + reversible + proof-carrying = born ready; day-1 is classical. |
| C6 | Fixed-slot "valence stamp" on every atom vs "infer, only surface exceptions" | **Infer effects/capabilities; surface only missing/exceptional bonds.** No mandatory N-field ceremony (= the "garbage type layer" the director rejected). |
| C7 | "Bin into 9 bike lanes" / enumerate allowed paths vs "define valence, let structures assemble" | **Chemistry, not whitelist.** Define legal bonds (closed move-set); never enumerate allowed programs. |
| C8 | "Apple standards enforced at binary level" vs vendor lock-in | **"Apple" = refuse-to-ship-imperfection quality bar** (baked in). Domain compliance = loadable signed standard-packs (SOC2/HIPAA), swappable. |
| C9 | embeddings ≈ quantum states / single representation | **Multi-view stack:** vectors=retrieval, graphs=relations, IR=execution, provenance=trust. |

---

## §4 — The unified design

### §4.0 The two ideas (the whole thing collapses to these)
1. **One primitive: a linear (non-duplicable) resource.** capability = memory ownership =
   no-cloning = "authority only shrinks downhill." A unit holds resources, may pass a *subset*
   on, may never copy/amplify.
2. **The atom is a proof obligation.** Code does not exist until its math discharges —
   refinement types where clean, SMT/Z3 for the rest. "Done" is unreachable without a discharged
   proof. (Forcing function vs AI vibe-coding.)

### §4.1 Language-semantics layer
- Linear-resource core; refinement types + SMT; **effects inferred, carried in the type** (no
  declared-slot ceremony).
- Surface feel = **Swift + Rust** (value semantics, optionals, protocols, exhaustive match +
  ownership/no-GC/no-data-races; `unsafe`-style escape only in named, audited, traced regions).
- Lowers to **Rust → WASM** day-1; **own typed IR** designed from line-1 (likely the node-graph)
  so the Rust intermediary is discardable later.
- Design rule: **invalid programs unrepresentable by construction** — dangerous moves aren't in
  the alphabet (no ambient authority, no arbitrary-memory, no arbitrary-syscall in the atom's
  closed move-set). Containment, not recognition: door-check once at admission (re-derived from
  bytes, proof-carrying), then run free — no runtime security-GC.

### §4.2 AI-semantics layer  ← absorbs `Independent AI Insight.yaml`
The control-plane model becomes the language's governance of AI-authored code. Mapping:

| Control-plane primitive (the YAML) | Language realization |
|---|---|
| `verify` / `done_when` / proof_obligation | = **the proof-obligation atom** (§4.0.2). Same thing. |
| `capability` / `gate` / permission | = **the linear resource** (§4.0.1). Same thing. |
| `intent` / `non_goals` / `constraints` | typed root declaration; precedes any patch |
| `context` graph + `SourceAuthority` order | provenance is a *schema field*, authority-ranked (runtime evidence > compiled > tests > source > schema > config > logs > docs > comments > model-inference) |
| `assume` / `unknown` / `confidence` | uncertainty is **structural** (a type state), not prose |
| `risk` class → required gates | risk routes which proofs/gates are mandatory |
| `budget` (tokens/mutation/test) | bounded mutation scope; complexity budget per unit |
| `Evidence` (command/result/scope) | AI output enters as **unverified candidate bound to its verification result** (`AgentRun`, never truth); commit is proof-gated |
| `Memory` (provenance/ttl/invalidation) | typed, scoped, invalidatable; only verified facts promote |

**Slop-laws baked as runtime law** (grounded in M2M research: AI code 55.8% vulnerable; static
tools miss 97.8% of Z3-provable bugs; iterative refinement *degrades* 2.1→6.2 vulns by iter-8;
19.7% hallucinated packages):
- refinement cap = 3 passes → reset-to-seed (defeats refinement decay)
- proof-gated commit (no evidence → no "done")
- dependency requires existence-proof (kills slopsquatting)
- constant-time for secret-touching paths (by proof)

### §4.3 Core DB layer (M2M OS DB — touches everything)
- records carry **provenance + uncertainty AS SCHEMA**; PII vault emits **derived answers, never
  raw PII** (the one hard external data gate); sync = **CRDT, causality-bound** (no FTL);
  **identity content-addressed** (record IS its hash; keeper supersedes by publishing new hash);
  secret-touching paths constant-time by proof. **Fail-closed** by runtime policy.

### §4.4 Execution layer (day-1 vs day-2)
- **Day-1:** compile → Rust source → WASM (web/ChromeOS) + native (macOS). Reuses existing
  `backend-rust` spine; emitted Rust is locked (no `unsafe`; capabilities = Rust newtypes/traits
  so a missing capability is *also* a Rust compile error). Runtime must be **WASM-small**
  (Raspberry-Pi floor → cloud ceiling, same node contract).
- **Day-2 (candidates, not committed):** own IR → Cranelift/LLVM; interaction-combinator/HVM
  graph-reduction as execution model; quantum-ready linear+reversible ops. WebGPU/WGSL = compute
  acceleration concern, orthogonal to the core.

### §4.5 Security model — blast-radius-zero through decomposition + ephemerality  ★KEYSTONE (director, 2026-05-28)

**Reframe of "security":** not patching holes (those are *evidence* of the AI-code failure-class we
exist to prevent), and NOT the un-defendable claim "can't be hacked." The achievable, skeptic-proof
claim is **blast-radius-zero + recoverable**: compromising any unit yields nothing transferable and
persists nothing. Four structural guarantees produce it — each maps to an existing primitive:

1. **Decompose to the natural atom.** The world is millions of small units (widgets / nodes), each
   a **linear resource** carrying only its *attenuated* capabilities. A hack lands on *one widget in
   a mesh of millions*. **Decomposition ≠ binning:** the unit is the natural grain (a node), not an
   imposed N-field stamp; blast-radius comes from per-unit attenuation, not mandated bins.
2. **No amplification.** Linear resource + attenuation (§4.0.1): a compromised unit cannot gain
   authority it wasn't handed and **cannot bond outside its lane** (closed move-set, §4.1). Dangerous
   moves aren't in its alphabet.
3. **Ephemerality / reset-to-seed.** The running unit is disposable — reset = `/clear` = browser
   reload. No persistent foothold. **Ephemeral ≠ data-loss:** ephemeral *execution*,
   durable-by-supersession *data* (content-addressed node, PII vault, CRDT sync §4.3). Reset clears
   the instance; the canonical record is re-addressed fresh. (cf. ephemeral-sandbox research:
   Firecracker ~125ms boot, sandboxes destroyed periodically to prevent secret/IP accumulation; and
   the Canvas "sessions ephemeral, destroyed periodically" pattern.)
4. **Traced compromise = immune system.** An illegal attempt is both *can't-exist* (unspellable in
   the IR) AND *traced* — defense becomes intelligence (records the antigen).

**The IR/WASM floor is the enforcement boundary (why it "needs to be strong"):** the unit boundary
is only real if the runtime enforces it. A unit = a `no_std`, ~150KB-WASM-small sandbox (§5.2 floor
already proven); **WASM validation = door-check-once** (re-derived from bytes, proof-carrying, then
run free — no runtime patrol); **capabilities = imports the unit simply does not have.** Day-1: WASM
+ host sandbox (Seatbelt/AppContainer/gVisor/Firecracker per workload). Day-2: own IR → own
OS/silicon, hardware-rooted attestation (unattested Pi = low-trust tab, no sensitive keeper role).

**Two audiences (identity evolution):** "for us **and** to contribute to the world." This sharpens
the older OS-first-only note → **standalone general-purpose language that we also build on.** These
guarantees are language-level, not Canvas-specific, so they're contributable.

---

## §5 — Binding to Canvas reality  ⟨FILLING FROM AGENTS — DO NOT FINALIZE⟩

Each design element must point at real `file:line` in `~/sales-landing-page` and the Canvas issue
it formalizes. Slots below are filled by the 3 ground-truth agents.

### §5.1 Capability / linear-resource ↔ as-built  ✅ FILLED (security/capability agent)

**The right shape, built at runtime instead of compile-time:**
- ADR-009 boundary type system — `governance/adr-009-canonical-service-boundary.md`; impl
  `backend-rust/crates/canvas-backend/src/boundary/mod.rs:41-159`. Trust = three `u8` constants
  (`TRUST_EXTERNAL=0`, `TRUST_INTERNAL_AUTHENTICATED=1`, `TRUST_CONTROL_PLANE=2`); marker trait
  `BoundarySeam` on zero-size `Copy` structs; generic `CrossBoundaryCall<Caller, Callee>`
  (`mod.rs:104-127`) whose ctor enforces `caller.trust_level() >= callee.required_caller_trust()`.
  ✅ Monotone "authority shrinks downhill." ❌ Check is **runtime `u8` compare**, not a type error.
  → **Language move:** trust levels = phantom type params; `CrossBoundaryCall<External,
  ControlPlane>` must fail to typecheck. Make `BoundarySeam` tokens **linear** (consume/pass-down,
  never copy) so attenuation is a borrow-checker invariant.

**The proto-linear resource that already exists (the template):**
- `ConfirmToken` / `GateVerdict::RequireConfirm` — `effect_gate.rs:55-95`. Single-use, opaque,
  minted per call, must be redeemed before a side-effect runs. `OutboundComm` always confirms;
  `Destructive`+high-risk blocks. → **This is the shape of EVERY capability token in our language:**
  owned, non-`Clone`, consumed on use.

**ADR-057 AI-as-bounded-emitter (schema→capability→cost):**
- `governance/adr-057-ai-motion-intent-capability.md`; cap enum `packages/canvas-protocol/src/
  capability.ts:3-13` + `schema/Capability.json` (10 enumerated strings); gate
  `assertCapability(have: readonly Capability[], need)` `capability.ts:45-50`. ❌ `Capability` is a
  **string in a plain array** — copyable, replayable, serializable. Cost gate (cost = elem×ms/1000,
  10s window, cap 10k) is **spec-only, no Rust impl**. → **Language move:**
  `assert_capability(token: CapabilityToken<Need>) -> GrantedToken<Need>`, linear in, single-use out.

**#71 governance kernel / capability grants — schema exists, enforcement does NOT:**
- `CapabilityGrant` struct `canvas_model.rs:202-224` carries `scope: String` (glob),
  `expires_at`, `revocable`, **`revocation_epoch: u64`** (monotonic shrink-at-checkpoint) — the
  intended attenuation model. But it `derives Clone` → duplicable, not linear.
- `CapabilityContext` enum `policy/mod.rs:43-63` — closed/exhaustive (good) but `derives Clone` (bad).
- 🔴 **`DenyReason::CapabilityNotGranted` (`policy/mod.rs:124`) is DEAD CODE** — `DefaultPolicyEngine`
  only checks tenant_id + user_sub non-empty; it **never verifies the caller holds the capability**.
  Capability name flows to audit logs but is never gated. → **Language move:** the grant check is a
  *required syntactic step*, not an optional runtime call. Attenuation constructive: a passed token
  has scope ≤ parent, epoch ≤ parent — narrow only, never widen.

**VIOLATIONS the language must make unrepresentable (the wounds to cure):**
- 🔴 #163 — `signing-service/src/auth.rs:7-11,102-129`: JWT decoded via `base64`+`serde_json`, **no
  signature verification, no JWKS** → any well-formed token with any `sub` is accepted (forgeable).
- 🔴 #164 — `signing-service/src/auth.rs:69-83`: `SIGNING_DEV_ALLOW_ALL` env var injects
  `CallerIdentity{caller_id: Uuid::nil()}` and bypasses everything, toggleable at runtime.
  (Postmortem record: `canvas-backend/src/auth.rs:22-29` `#163-anchor`/`#164-anchor` comments.)
- 🟡 Ambient authority: `AuthContext{tenant_id, user_sub}` injected into request **extension map**
  by middleware (`auth.rs:42-45`), extracted by handlers — a handler that forgets the arg simply
  gets no check. → **authority must be a required argument, no ambient fallback.**
- 🟡 #302 cap-gate bypass — `Registry.swift:93-104` `registerCommandBar` checks only non-empty
  tenant/user, never `assertCapability(.intentEmit)`.
- 🟡 #303 tenant leak (Swift broker) — `Broker.swift:272` `registeredSubscriptions` returns ALL
  sessions, no tenant filter; `tenantId` absent from `SignalEnvelope`/`Subscription`/`IntentHandle`.
  (Rust path is OK: RLS `SET LOCAL app.current_tenant` `db.rs:47-61` + `TenantIsolationBoundary`
  `policy/isolation.rs:34-45`.)

### §5.2 Typed IR / effect-envelope ↔ as-built  ✅ FILLED (protocol/IR/effect agent)

**Schema-first ABI = the strongest "our typed IR" candidate (already exists):**
- The kernel ABI IS `packages/canvas-protocol/` — **JSON-Schema Draft-07 as single source of
  truth**, generating TS (`scripts/codegen-ts.mjs`), Zod validators (`codegen-zod.mjs`), and Swift
  (`apps/mac/scripts/codegen-swift.sh`, `quicktype --swift-version 6`). Generated files are
  **committed and CI drift-gated** (diff fails the build). → **Language move:** this drift-gate
  pattern IS "schema is source of truth"; our typed IR should be the schema, codegen its
  projection. **Gap:** no Rust codegen yet — Rust types are hand-mirrored + parity-checked
  (`check-rust-dep-parity.mjs`). Our compiler closes that.
- Branded nominal types already in use: `src/invariant.ts:1-66` — `WorkObjectId`/`SessionId`/
  `PolicyBundleId`/`TenantId`/`UserSub` as `string & {__brand}`. Universal `Result = {ok}|{ok,error}`.
- **Best concrete IR doc:** `schema/MotionTimeline.json` → runtime form `motion-core/src/graph.rs`
  `MotionGraph` = persistent **HAMT** node graph, monotonic `u64` version, structural sharing,
  per-property `ConflictPolicy{LastWrite|Compose|Error}`. Content-addressed *in behavior* (same
  inputs→same version) but **UUID-identified, not hash-identified**. → our IR makes the hash the id.

**Effect-envelope + actor model = already the execution model:**
- `SignalEnvelope.json` (base, discriminated on `source_kind: widget|system|ml|user`) is THE effect
  envelope; every cross-boundary act is an envelope. `IntentEnvelope`/`MotionIntent`/`MotionPatch`
  are variants. `MotionIntent` carries DAG causality (`parent_motion_intent_id`, `trace_id`).
- `SessionInvariant {work_object_id, session_id, policy_bundle_id, tenant_id, user_sub}` is stamped
  by the broker on every envelope, **caller values overwritten** (`Stamping.stamp()`) — the
  unforgeable **effect scope**. → **Language move:** encode this scope in the *type* of an effectful
  expression; effects can't leak across sessions because the scope is in the type.
- `apps/mac/Sources/CanvasBroker/Broker.swift` — Swift **`actor`**, the sole authority; widgets
  never call each other. `Registry.swift` mints distinct opaque handles (`RegisteredHandle`/
  `MlHandle`+`SignedMlGrant`Ed25519/`IntentHandle` singleton); widgets *cannot* claim `tape.read`/
  `view.inject`/`intent.emit`. `SignalPattern.json` = effect-subscription DSL (`kind_glob` +
  composable `PayloadPredicate{eq|neq|in|exists|and|or}`). → effect routing is already first-class
  and declarative; our effect system formalizes it.
- **The 3-layer enforcement chain = the effect handler:** (1) JSON-Schema/Zod parse → (2) broker
  capability check → (3) cost gate (`element_count * duration_ms / 1000`, 10s window, cap 10k).
  → an effect type carries its required capability; the broker is the handler that discharges it.

**WASM-small floor (#322 / G02) — already proven:**
- `motion-core` is `#![cfg_attr(not(feature="std"), no_std)]` (`src/lib.rs:6`), feature split
  `default=["std"]` / separable `alloc`; `glam` w/ `libm` for **deterministic cross-arch float**;
  release profile `opt-level="z"`, `lto=true`, `codegen-units=1`, `panic="abort"`, `strip=true`;
  **hard CI budget ≤150KB gzipped WASM, ≤200ms cold-start on Snapdragon-662-class** (D-14, ADR-056
  tiers S/A/B/C). `frame()` = single O(n) pass, zero alloc inside. → this IS the Raspberry-Pi-floor
  runtime contract our language must compile into.

**Reality note:** #287 node-mesh is a *North-Star direction* in ADR-004:78, not a codebase — the
real node-graph is `MotionGraph`. (See §5.4 issue-number caveat.)

### §5.3 Data / PII / provenance ↔ as-built  ✅ FILLED (data/PII/provenance agent)

**PII — the live wound + the wrong shape:**
- #63 PII-at-rest: `backend-rust/migrations/V2__pii_encryption.sql:1-47` adds `*_enc` cols +
  `email_hmac CHAR(64)` (HMAC lookup w/o plaintext). 🔴 **but it's additive dual-write — plaintext
  cols KEPT "for backfill"** → raw PII still flows. No vault, no derived-answer surface.
- 🔴 #166: `canvas-backend/src/auth.rs:26` `#166-anchor` records the fix (OIDC-only, no fallback);
  the live leak is `apps/landing/src/lib/founders.ts:18-43` — **real names/LinkedIn/GitHub/IG served
  from an unauthenticated `/api/content/[collection]` endpoint.** → **Language move:** PII is an
  opaque **vault handle from schema-definition time** (not a bare string encrypted later); a
  `PublicProfile` type must *explicitly opt into* public exposure.

**Provenance / export / sync — types exist, enforcement + content-addressing don't:**
- #79 export firewall: **not built** (CODEBOOK:111 "After Phase 1"). Closest:
  `telemetry/privacy.rs:24-167` — `RetentionPolicy::deny_by_default()` (export_allowed:false),
  `ExportControl{Blocked|AllowedWithRedaction|AllowedRaw}`, `MetadataMinimizationPolicy::minimize`.
  🟡 **minimization is substring-match on field names** ("raw"/"pii"/"content") → `customer_email`
  slips through. → **Language move:** taint is a **compile-time lattice on the type**, not a runtime
  string filter.
- #72 encrypted-local-DB + CRDT sync: **not built.** Schema `local.sync_queue` + SQLCipher named
  (CODEBOOK:180), but no SQLite/SQLCipher code, **no CRDT/causality anywhere**; `sync_status`
  enum has `ConflictDetected` but no resolution. → genuine greenfield; our DB layer specifies it.
- provenance (≈#263): no Merkle yet (ADR-054 defers to #231). `audit/mod.rs:151-268`
  `AuditIntegrityChain` = SHA-256 **chain** (`prev_hash`+`payload_hash`) but **verifies linkage,
  not payload content** (originals not retained). `verification/mod.rs:34-467` `ReleaseGateSuite` =
  9 gates, all-must-pass; `SecretResolutionContract` permanently forbids `InlineKey`. → **Language
  move:** content-addressed record (record IS its hash) closes the "linkage ≠ content" gap; make
  provenance a *schema field*, not an audit side-channel.

**Fail-closed (≈#262) — intent strong, one runtime hole:**
- ✅ `gateway_middleware.rs:212-275` JWKS-down→503 deny; missing-auth→401. `0002_canvas_model.sql:51`
  `offline_behavior DEFAULT 'fail_closed'` (CHECK-constrained vocab) — the most precise
  provenance-as-schema primitive in the repo. `boundary/mod.rs` under-trust→`Err`.
- 🔴 **but `GovernorLayer` (rate-limit) is mounted BEFORE `AuthContext` exists** (E1-E11 report :30)
  → per-tenant rate limiting is functionally **fail-OPEN**; `RequestBodyLimitLayer` declared but
  never mounted (DoS vector). → **Language move:** middleware *dependency ordering* must be a type
  constraint, not runtime convention (a layer needing `AuthContext` can't compose before it exists).

**Injection — the type system's clearest failure today:**
- 🔴 #304: `db.rs:47-60` `sqlx::query(sqlx::AssertSqlSafe(format!("SET LOCAL app.current_tenant =
  '{safe}'")))` — raw interpolation after quote-doubling; `AssertSqlSafe` explicitly opts OUT of
  sqlx's safety check (CVSS 8.8). Postgres `SET LOCAL` has no bind-param form → root cause is real.
  Contrast `governance.rs:126-149` uses `QueryBuilder.push_bind()` correctly. → **Language move:**
  parameterized binding is the *only* constructible DB op; `AssertSqlSafe`-style escape hatch only
  inside a named/audited/traced region (the generalized-`unsafe` law).

**Data classification:** `canvas_model.rs:50-67` `TrustBin{System|Managed|Generated|Untrusted}`
**deliberately omits `PartialOrd`** to forbid ordering (right instinct); `Generated` "MUST NOT
receive auth handles, DB connections, or filesystem handles." `CanvasCommand.risk_level: u8` (0-9).
→ **Language move:** express trust as a **lattice type** that cannot be coerced/cast — not an enum
that merely lacks a trait.

### §5.4 ⚠️ Issue-number caveat (honest reality-check)
Several issue numbers in the research dump don't exist verbatim in the repo — they map to ADRs or
other constructs: **#262/#263/#287/#315/#316 not found by number.** #262≈fail-closed contracts,
#263≈`ReleaseGateSuite`, #287≈ADR-004 North Star, #315/#316≈E1-E11 findings #7/#8/#14/#15. The
*concepts* are real and anchored above; the *numbering* in the dump is approximate. Bind the spec
to the ADRs/files, not the issue numbers.

---

## §6 — Concerning trends & feedback from the reports  ⟨director-requested⟩

What the analysis reports (`gh_issues_ai_overview` + `Independent AI Insight`) actually flag, and
the honest strategic read. Detailed headline goes to director in chat; captured here for the record.

### §6.1 Concerning trends in the Canvas project (from the GH-issue report)
1. **🔴 Live P0 security holes parked as ordinary Todos** — #163 (JWT sig not verified), #164
   (`SIGNING_DEV_ALLOW_ALL` disables auth), #165 (cross-tenant bulk export, unaudited), #166
   (unauth endpoint returns hardcoded PII), #167 (unvalidated `X-Forwarded-For`), #304 (SQL
   concatenation), #302 (cap-gate bypass), #303 (tenant isolation leak). These are
   *release-blockers*, exploitable now. Report rec: one "Security Release Blocker" epic.
1b. **🔴 New holes the code-read surfaced (not in the original report):** (i) `db.rs:47-60`
   `AssertSqlSafe(format!())` tenant injection (CVSS 8.8); (ii) PII **dual-write** —
   `V2__pii_encryption.sql` keeps plaintext cols alongside ciphertext; (iii) `founders.ts:18-43`
   real-person PII served from an **unauthenticated** content endpoint; (iv) `GovernorLayer`
   rate-limit mounted **before** `AuthContext` → per-tenant limiting is **fail-OPEN**;
   `RequestBodyLimitLayer` declared but never mounted (DoS); (v) `CapabilityNotGranted` is **dead
   code** — grants are never actually checked.
2. **🟡 Architecture-vs-code drift** — Done PRs ahead of the still-Todo architecture map (#258).
   Future AI agents may rebuild obsolete assumptions. (World-map cv/impl contract is the mitigant.)
3. **🟡 Scope sprawl — "several products at once"** — ZK-DAE (#117–133) is an R&D program posing
   as a feature epic; catalog/calculator (#99–108) risks becoming a parallel product; landing app
   keeps absorbing architecture. Without dependency gates the roadmap gets eaten.
4. **🟡 Signing looks done but trust is incomplete** — advanced signing while auth hardening
   (#163/#164, eIDAS #299, bypass #300) is open. Don't market it high-trust yet.
5. **🟡 Governance-as-theatre risk** — strong governance *intent* but controls (#27–#33) sit as
   policy Todos while telemetry/AI work expands. ("risk_without_policy" failure mode.)
6. **🟡 Hygiene** — 0 assignees across 313 records; little visible sequencing → an AI agent picks
   attractive features over dependency-critical ones. Rec: backlog → DAG with blocked_by/unlocks/
   runtime/trust_level/release_gate.
7. **Highest-leverage move per the report:** *stop adding features; build a machine-readable
   `repo_contract.yaml` first* (canonical product def, live/deprecated paths, security blockers,
   capability + data-classification model, AI-forbidden-assumptions, issue DAG).

### §6.2 AI-generated-code trends the LANGUAGE must counter (from Independent AI Insight)
semantic-flattening · premature-implementation · false-completion · dependency-inflation
(slopsquatting) · architecture-drift · context-overstuffing · silent-assumption ·
verification-theatre · unsafe-generalization · large-patch-bias · tool-overtrust ·
memory-pollution. → Each maps to a §4.2 mechanism. The language's reason-to-exist is to make
these *structurally impossible*, not policed after the fact.

### §6.3 The strategic flag (honest pushback — finance-major conflict-layer)
The reports *unanimously* say the highest-leverage move is **harden security + declare
architecture first**, not build new surface area. We are starting a **new language**. Tension:
the language is the long-term differentiator, but it does **not** patch #163/#164/#166 — which are
exploitable in the *shipping* product *today*. **Reconciliation (the bridge):** the language is
precisely the structural cure for the *class* of bug those holes are (ambient auth, unverified
tokens, raw-PII egress, SQL concatenation). So the work isn't opposed to security *if* the
language's first proof-of-value is to make those exact holes unrepresentable — i.e., a vertical
slice on #71 capability grants / #163-#164 auth. Decision for director: §7.

---

## §7 — Open forks / next (spec phase decides)

1. **Sequencing fork — RESOLVED (director, 2026-05-28):** the live P0 holes are NOT this effort's
   work ("they're for me"). They are *evidence* of the AI-code failure-class — much of it written by
   frontier models — that the language nips at the bud. They become **test-cases / proof targets**
   (a v0.1 must demonstrate they're unspellable), not patch work. Security is redefined as the §4.5
   **blast-radius-zero containment model, built in from line 1**, not hole-patching. → Proceed to
   the language-semantics spec.
2. Emit Rust *source-text* vs proc-macro/library DSL (day-1 lowering form).
3. Is the typed IR literally the #236 kernel ABI / #287 node-mesh? (Pending §5.2 anchors.)
4. Day-1 surface: web-only vs web+macOS.
5. Name (still TBD; "Synetheier" was a typo).
6. Resume paused prior-art fan-out (capability langs/OSes, Unison content-addressing at scale,
   attestation, Mojo adoption play) to de-risk — before or during spec?
