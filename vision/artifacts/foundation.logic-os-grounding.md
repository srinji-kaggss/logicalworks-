---
id: foundation.logic-os-grounding
track: wedge
title: Logic OS Grounding - Foundational Model
model: codex
confidence: 0.72
provenance: elicited
grounding:
  - vision/prompts/GLOBAL.md
  - vision/viz-data/SCHEMA.md
  - vision/artifacts/viz/00-world-map.md
  - vision/artifacts/viz/01-t6-assumptions-understandings.md
  - vision/research/machine-first-language/SCOPE.md
  - vision/research/machine-first-language/LGWK_MAPPER.md
  - /Users/srinji/sales-landing-page/CODEBOOK.md
  - /Users/srinji/sales-landing-page/laws/governance/README.md
  - /Users/srinji/sales-landing-page/laws/governance/adr-062-intent-outcome-gating.md
  - /Users/srinji/sales-landing-page/laws/governance/adr-063-mathematical-bounding.md
  - /Users/srinji/sales-landing-page/laws/governance/adr-064-hash-chained-telemetry.md
  - /Users/srinji/sales-landing-page/laws/governance/adr-066-logic-os-foundation-substrate.md
  - /Users/srinji/sales-landing-page/laws/governance/adr-067-logic-os-kernel-engine-map.md
  - /Users/srinji/sales-landing-page/laws/governance/terminology.md
  - /Users/srinji/sales-landing-page/laws/governance/signal-network-standard.md
maps_to_vision: [gate, tape, sovereignty, anti-hack, ml, protocol]
feeds: [decision, build, ml]
expand_axes:
  - typed-authority-lineage
  - machine-first-language-as-governance
  - vocabulary-registry-composition-rules
  - local-first-telemetry-proof
  - mapper-to-os-intel-promotion
---

# Logic OS Grounding - Foundational Model

## TL;DR

- Logic OS is best understood as a governed action substrate, not as an AI assistant, app shell, or generic backend.
- The core asset is a closed, typed, replayable capability world where models propose and deterministic engines dispose.
- The world-map says OS-layer attempts die at the governance wall; the governance docs say that wall must become native engine machinery.
- The machine-first language is the design pressure valve: human syntax is secondary; the canonical artifact is typed graph/AST/effect IR.
- The next grounding move is to make every idea reducible to four questions: what is the entity, what capability is being attempted, what authority lineage permits it, and what proof remains after it acts?

## 1. Core Thesis

Logic OS is a "plugin to the internet" only if it can sit between intent and effect without becoming another opaque automation layer. Its durable advantage is not chat UX, model quality, or owning a distribution channel. The durable advantage is that the OS makes action governable by construction.

The current evidence base points to this foundation:

```text
Intent -> typed envelope -> identity/time root -> vocabulary check -> authority check
       -> tenant/data boundary -> intent/outcome gate -> resource arbiter
       -> durable journal -> effect -> hash-chained audit
```

That chain is the product's real substrate. The UI, model, browser extension, Mac shell, and SDK are surfaces around it.

## 2. What The World-Map Changed

The earlier assumption was that the technical wedge was the hard part: own a high-frequency entry point, build a runtime, add compliance later. The T6 synthesis reverses that. Across super-app and OS-layer precedents, scale breaks first at governance: financial regulation, privacy, competition, national-security, identity, and platform control.

The useful conclusion is not "be compliant." It is narrower and more technical:

```text
Governance must be an engine primitive before product logic becomes powerful.
```

For Logic OS, "governance" means:

- gate before execution, not audit after;
- consent and authority are scoped, revocable, and context-specific;
- ranking/defaults/steering become governed surfaces;
- payment-like and signing-like effects are separated as regulated infrastructure;
- autonomous peers are authorized at intent/outcome level, not just API-permission level;
- every deny and every effect leaves tamper-evident evidence.

## 3. The Language Is Not Syntax

The machine-first language scope says the language is not primarily a nicer human syntax. It is a constrained operating substrate for AI-authored software. That maps directly onto the governance kernel.

The language should not begin with:

```text
component, function, route, handler
```

It should begin with:

```text
entity, relation, capability, authority, effect, evidence
```

Human syntax can project to TSX, SwiftUI, or Rust. The canonical source of truth should be the graph/AST/effect IR that can answer:

- Which entity owns this data?
- Which work object and session scope it?
- Which policy bundle is in force?
- Which capability is being attempted?
- Which subject holds authority right now?
- Which outcome bounds are allowed?
- Which journal and audit records prove the transition?

This is the key distinction: a language for humans optimizes expression; a language for Logic OS optimizes bounded action.

## 4. Foundational Vocabulary

These are the terms that should stay stable across docs, prompts, generated code, and mapper output.

| Term | Grounded meaning |
|---|---|
| Logical Works | Company and ecosystem umbrella. |
| Logic OS | User-facing governed work substrate. |
| Logic | Human-facing machine identity. |
| Canvas | Internal engineering substrate/code name. |
| Work Object | Durable tenant-scoped anchor: case, client, proposal, deal, ticket, matter. |
| Session | Bounded activity window linked to a work object. |
| Policy Bundle | Versioned governance declaration bound to work/session. |
| Capability Vocabulary | Closed, typed, versioned registry of nameable actions, parameter schemas, and legal compositions. |
| Envelope | Immutable typed packet routed through the broker. |
| Broker | Stateless router that validates, stamps, gates, and fans out envelopes. |
| Governance Kernel | Boundary engine that returns ALLOW/DENY/LOCAL_ONLY/METADATA_ONLY/CONFIRMATION decisions. |
| Root Overseer | Attestable identity and time root. |
| Durable Journal | Record-before-effect recovery and replay log. |
| Audit Plane | Hash-chained WORM evidence layer. |
| The Shadow | Local vault/runtime isolate. |
| Closed-Action Guarantee | The substrate never emits an unaccounted action. |

## 5. Eleven Engines As The Kernel Map

ADR-067 is the best current kernel decomposition. The important grounding point is that these are not optional modules. They are distinct axes of failure.

| Order | Engine | Question answered |
|---:|---|---|
| 1 | Identity & Trusted-Time Root | Who is acting, and when, from an attestable source? |
| 2 | Capability Vocabulary | Is this action nameable in the closed registry? |
| 3 | Authority / Rights Calculus | Does this subject hold this scoped right now? |
| 4 | Tenant Isolation | Is this row/object inside their tenant boundary? |
| 5 | Effect / Irreversibility Gate | May this side effect fire silently, require confirmation, or block? |
| 6 | IPC / Boundary Transport | Did the message cross domains through a mediated, re-stamped seam? |
| 7 | Resource / Cost Arbiter | Is the action inside budget, quota, and kill-switch constraints? |
| 8 | Durable Journal | Was the planned state transition recorded before the effect? |
| 9 | Audit / Transparency Plane | Is there externally verifiable evidence? |
| 10 | Key Custody / E2EE | Can the substrate govern data it cannot decrypt? |
| 11 | Lifecycle / Admission Supervisor | Did boot, restart, and hydration establish trust in order? |

The unifying object is not one opaque `execute(payload)` call. The unifying object is the authority lineage plus the audit contract.

## 6. Signal Network Model

The Signal Network Standard is the most compact "machine physics" statement:

```text
source -> signal packet -> broker/router -> handle/address -> effect
```

Three rules matter for the foundation:

- Every packet carries proof of authorization.
- Handles are addresses, not capabilities.
- Code is invariants, not instructions.

That third rule should become a language design law. A field is not "data"; it is a constraint statement. If the field cannot be expressed as set membership, inequality, causal ordering, or authority relation, it is probably product prose leaking into the protocol.

## 7. Machine-First IR Shape

A useful first canonical IR can stay small:

```jsonc
{
  "entity": {
    "id": "opaque-id",
    "kind": "work_object|session|policy_bundle|capability|effect|evidence",
    "tenant_scope": "tenant-id",
    "sensitivity": "class",
    "policy_bundle_id": "policy-id"
  },
  "relation": {
    "from": "entity-id",
    "to": "entity-id",
    "rel": "owns|scopes|authorizes|attempts|produces|records|supersedes"
  },
  "capability_attempt": {
    "subject": "principal-id",
    "capability": "domain.verb.object",
    "object": "entity-id",
    "intent": "semantic reason",
    "outcome_bound": {
      "max_rows": 1,
      "max_cost": 0,
      "reversible": true
    }
  },
  "proof": {
    "journal_record_id": "id",
    "audit_chain_hash": "sha256",
    "source_trace": ["intent", "ir-node", "target-source-lines", "test"]
  }
}
```

This is not a proposed final schema. It is a grounding scaffold for thinking. It forces design work to say which entities and proofs exist before discussing implementation language.

## 8. What The Mapper Should Promote

`lgwk mapper` should become the local ingestion loop for this foundation. The promotion rule should be strict:

- Triage may contain candidate concepts.
- OS intel may contain only claims that can be grounded to entities, relations, capabilities, authority rules, or evidence obligations.
- A candidate that cannot name its governed effect remains sandboxed.

Promoted OS-intel rows should prefer these kinds:

| Kind | Promotion criterion |
|---|---|
| entity | Has stable identity, scope, and owner boundary. |
| relation | Has typed direction and enforcement implication. |
| capability | Names a closed action and parameter surface. |
| gate | Has deterministic allow/deny/confirm conditions. |
| proof | Leaves journal/audit/trace evidence. |
| blindspot | Names the missing fact that would change architecture. |

## 9. Axioms To Carry Forward

1. No ambient authority. Every effect needs a scoped proof packet.
2. No untyped action. If it is not in the Capability Vocabulary, it cannot execute.
3. No hidden state transition. Record before effect, then audit after effect.
4. No trust by caller identity alone. Re-stamp identity at every boundary.
5. No product bypass. Products compose capabilities; they do not patch kernel gates.
6. No model on the hot path. Models propose; deterministic engines validate, execute, and replay.
7. No governance afterthought. Purpose, consent, residency, ranking, and side-effect policy must be in the execution path.
8. No plaintext assumption. The substrate should govern ciphertext and metadata without requiring operator access to user content.
9. No one-syscall mythology. Distinct gates answer distinct questions; one ledger unifies evidence.
10. No human-syntax primacy. The canonical artifact is machine-checkable IR; syntax is a projection.

## 10. Build Implications

These are architectural directives, not factual claims:

| Priority | Directive | Target | Falsifier |
|---|---|---|---|
| P0 | Define the Capability Vocabulary as generated shared types across protocol and backend. | protocol/gate | Backend can already prove action, params, and legal composition from a shared registry. |
| P0 | Make authority lineage linear and non-cloneable across envelopes, journal records, and audit events. | gate/tape | A cloned or caller-supplied authority token can still cross a boundary. |
| P0 | Implement intent/outcome preflight for every mutation. | gate | Mutations can execute without semantic reason and projected outcome bounds. |
| P0 | Replace stub/no-op audit sinks before production-like deployments. | tape | WORM sink failure cannot drop or fake evidence. |
| P1 | Add mapper promotion rules that reject sandboxed speculation from OS intel. | ml | `notes/os-intel.jsonl` contains unverified speculative nodes. |
| P1 | Treat local telemetry as hash-chained, enclave-signed input to learning. | ml/tape | Model-training signals can be deleted or injected without detection. |
| P1 | Formalize field contracts as invariants before schema expansion. | protocol | Protocol fields cannot be expressed as a set, bound, causal rule, or authority relation. |

## 11. Open Gaps

- The consumer-device inference cost curve remains an open high-severity blindspot in the world-map.
- The Capability Vocabulary exists conceptually but is not yet proven as shared generated types across every runtime boundary.
- Authority/Rights Calculus is still distinct from, and currently weaker than, trust-tier validation.
- Durable Journal and replay are foundational to determinism but not yet the same maturity as the audit chain.
- E2EE key custody and residency enforcement need a stronger proof model than "ciphertext exists."
- The machine-first language still needs a minimal grammar and IR validator that can reject invalid entity/effect graphs before source generation.

## 12. One-Sentence Grounding

Logic OS is a machine-checkable law of motion for governed work: every intent becomes a typed packet, every packet proves authority, every authority is bounded by outcome, every effect is journaled before it happens, and every decision leaves evidence.
