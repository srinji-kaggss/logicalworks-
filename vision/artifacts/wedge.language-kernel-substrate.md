---
id: wedge.language-kernel-substrate
track: wedge
title: Canvas Language Kernel — Translation as a Governed Resident Service
model: codex
confidence: 0.79
provenance: elicited
grounding:
  - "/Users/srinji/Downloads/Untitled document-9.md"
  - "/Users/srinji/Desktop/Translation.xml"
  - "/Users/srinji/logic-research/research/machine-first-language/SCOPE.md"
  - "/Users/srinji/logic-research/artifacts/machine-first-language.foundation.md"
  - "/Users/srinji/logicalworks-/vision/PROTOCOL.md"
  - "/Users/srinji/logicalworks-/vision/ARTIFACT_SCHEMA.md"
  - "/Users/srinji/logicalworks-/vision/artifacts/ecosystems.super-app-os-layer.md"
  - "/Users/srinji/logicalworks-/vision/artifacts/Competing_OS_Framework_Map.md"
  - "/Users/srinji/logicalworks-/vision/artifacts/canvas-architecture-recommendation.md"
  - "/Users/srinji/sales-landing-page/docs/canvas-architecture.md"
  - "/Users/srinji/sales-landing-page/apps/landing/src/i18n/catalog.ts"
grounding_tool: "firecrawl UNAVAILABLE — fell back to local repo/framework docs"
source_tiers: {primary: 0, secondary: 0, tertiary: 0}
adjudicated_by: explorer-subagent
convergence: stable-disagreement
maps_to_vision: [gate, tape, sovereignty, ml, scale]
feeds: [decision, build]
expand_axes:
  - "signed-language-bundle-abi"
  - "translation-lexicon-grid-schema"
  - "tenant-brand-overlay-policy"
  - "agentic-language-coordination-sandbox"
  - "document-node-ast-and-patch-stream"
---

## TL;DR

- The right target is **not site i18n** and not merely a machine-first code language. It is a **resident language service** with kernel APIs, policy bundles, provenance, fallback, and host adapters.
- The current landing seam is useful, but only as a **bootstrap provider**. It must not define the kernel shape.
- AI should be **coordination-only** on canonical surfaces: selecting and arranging approved candidates, not minting arbitrary strings.
- White-label should be treated as a **stacked overlay discipline**: base semantics -> locale -> brand -> tenant -> runtime policy.
- The canonical backend should eventually own **bundle integrity, policy, audit, and multi-surface distribution**, while web/native/shell surfaces bind to one stable ABI.

## MAP

Three internal lines of evidence converge:

1. **Framework direction**
   - `Untitled document-9.md` and `Translation.xml` describe a deterministic language substrate where AI is bounded by immutable semantic structures and compute tiers.

2. **Current machine-first language work**
   - `SCOPE.md` and `machine-first-language.foundation.md` are stronger on governed code generation than on language-kernel semantics.
   - The explorer review is right: the center of gravity there is still IR, codegen, auth, effects, and target projections, not locale/dialect/register/provenance/fallback as first-class kernel objects.

3. **Canvas substrate worldview**
   - `canvas-architecture.md` and `canvas-architecture-recommendation.md` already establish the right pattern for privileged infrastructure: broker, gate, tape, and strict chokepoints.
   - Language should follow the same rule: one native control plane, many host adapters.

### The main correction

The previous direction risks becoming:

- a frontend-friendly locale framework, or
- a machine-first app language with translation bolted on

The actual target should be:

**a resident governed language service**

That service resolves concepts into approved renderings across surfaces, enforces market/tenant/brand policy, records provenance, and degrades safely across compute tiers.

### Kernel primitives that must move to the center

- `Concept`
- `Term`
- `Message`
- `LocaleProfile`
- `FallbackGraph`
- `PolicyBundle`
- `TranslationRecord`
- `ProvenanceEntry`
- `BrandOverlay`
- `TenantOverlay`
- `TranslationCandidateSet`
- `TranslationEvaluationState`

### Recommended planes

| Plane | Responsibility | Day-1 provider | Future canonical owner |
|---|---|---|---|
| **Catalog Plane** | semantic bundles, locale bundles, namespace manifests, fallback graph | local filesystem | canonical backend |
| **Policy Plane** | brand/tenant/domain/jurisdiction controls | local config | canonical backend |
| **Execution Plane** | deterministic match, candidate ranking, coordinator sandbox | local runtime | hybrid local + backend |
| **Validation Plane** | similarity checks, fallback forcing, verification state, reject paths | local runtime rules | canonical backend + local attestors |
| **Render Plane** | web/native/widget/shell adapters | surface-specific | surface-specific |

## SCALE & CONSTRAINTS

### Non-negotiables

1. **ZeroAI must always work**
   - Exact catalog and overlay resolution must be sufficient to render safe output in regulated or offline environments.

2. **AI does not own the words**
   - Heuristic layers may coordinate candidate arrangement but may not emit strings outside the approved candidate set for canonical surfaces.

3. **Fallback is a graph, not a default string**
   - Locale, script, register, domain, and market constraints must resolve through an explicit graph.

4. **Policy and provenance are first-class**
   - Every rendered phrase should be attributable to:
     - source concept
     - selected term/message
     - locale profile
     - overlay stack
     - policy version
     - execution tier

5. **Host bindings stay peripheral**
   - TSX, SwiftUI, and future shell surfaces should bind to the language service.
   - They should not define its semantics.

### What the current landing seam gets right

- request-scoped locale resolution
- provider seam
- manifest/bundle thinking

### What it still lacks

- no first-class `LanguageObject` model
- no semantic IDs independent of display strings
- no glossary / terminology service
- no fallback graph
- no phrase-level provenance
- no runtime capability gate for translate/override/publish operations
- no signed bundle delivery
- no structured document-node mutation model

## TOUCHES US

### Why this matters to Canvas

Language will eventually cut across:

- landing content
- widgets
- native shell labels
- command bar / agent prompts
- legal/compliance surfaces
- notifications
- white-label enterprise deployments
- translated document or workflow outputs

That means the language layer is not presentation glue. It is part of the substrate.

### Recommended boundary

The landing repo should remain an **adapter**.

The future canonical backend should own:

- language bundle distribution
- overlay resolution policy
- signature / integrity verification
- provenance and audit
- tenant and brand resolution

The local runtimes should own:

- ZeroAI deterministic execution
- offline caches
- local policy enforcement in disconnected mode
- surface rendering and patch application

## BUILD-NOW

### Subagent-driven development plan

| Phase | Owner | Deliverable | Why |
|---|---|---|---|
| **P0** | Architect subagent | schema for `Concept`, `Message`, `LocaleProfile`, `FallbackGraph`, `PolicyBundle` | define the real kernel objects before more helpers appear |
| **P0** | Reviewer/Hacker subagent | adversarial review of arbitrary-string generation, overlay poisoning, and policy bypass | language kernel is a trust boundary |
| **P0** | Worker 1 | rename current landing work as `local language provider` / `catalog adapter` | demote site-local assumptions |
| **P0** | Worker 2 | add kernel-shaped manifest endpoints and overlay placeholders | stabilize the ABI before the backend exists |
| **P1** | Architect subagent | `TranslationLexiconGrid` + `TranslationCandidateSet` spec | foundation for StatisticalML / HeuristicAI tiers |
| **P1** | Worker 3 | document-node/span contract and patch-stream format | needed for docs, widgets, and later shell surfaces |
| **P1** | Worker 4 | phrase provenance/audit model wired into gate/tape thinking | aligns language with the rest of Canvas governance |
| **P2** | Worker 5 | remote provider stub in canonical backend shape | lets surfaces depend on the right contract early |
| **P2** | Worker 6 | signed bundle verification path + brand/tenant overlay loader | makes white-label structural, not ad hoc |
| **P3** | Research subagents | measured tier benchmarks on target devices | closes the “compute continuum” fantasy gap |

### Immediate directives

1. **Stop framing this as frontend translation in core architecture docs.**
2. **Define the resident service API before adding more locale utilities.**
3. **Make brand/tenant overlays explicit artifacts, not conventions.**
4. **Keep AI in bounded candidate coordination until a stricter validated-generation regime exists.**

## SKEPTICISM

### Strongest critique

The current direction is still too close to:

- “machine-first application language”, and
- “frontend-first framework with later backend integration”

That is a useful bootstrap but the wrong center of gravity for a ChromeOS-like substrate.

### What would falsify this recommendation

1. The product never needs cross-surface semantic control beyond a small marketing site.
2. White-label proves almost entirely cosmetic rather than legal/semantic/policy-bearing.
3. A language service introduces more complexity than value because the platform never accumulates shared language state across surfaces.

### Main blind spot

This recommendation is ahead of measured implementation evidence. The kernel cut is coherent, but not yet proven minimal.

## DIALECTIC

- **thesis:** the locale/catalog seam should be generalized upward into a resident language kernel with one control plane and many host adapters.
- **antithesis:** the current work is still too abstract and too codegen/app-language centered; without first-class language objects, fallback, provenance, and service ownership, calling it a kernel is inflationary.
- **synthesis:** keep the seam, but explicitly demote it to a bootstrap provider. Promote only the kernel primitives and service contracts that survive across web/native/backend surfaces.
- **residual_disagreement:** whether lexicon-grid and candidate-set protocols should be specified immediately or after one more grounded research wave on real translation/runtime workloads.

## ML-FEED

```json
{
  "entities": [
    {"id": "lk-concept", "type": "Concept"},
    {"id": "lk-message", "type": "Message"},
    {"id": "lk-locale-profile", "type": "LocaleProfile"},
    {"id": "lk-fallback-graph", "type": "FallbackGraph"},
    {"id": "lk-policy-bundle", "type": "PolicyBundle"},
    {"id": "lk-provenance-entry", "type": "ProvenanceEntry"}
  ],
  "relations": [
    ["lk-concept", "renders_via", "lk-message"],
    ["lk-message", "resolved_under", "lk-locale-profile"],
    ["lk-locale-profile", "falls_back_through", "lk-fallback-graph"],
    ["lk-message", "governed_by", "lk-policy-bundle"],
    ["lk-message", "recorded_by", "lk-provenance-entry"]
  ],
  "metrics": [
    "fallback_hit_rate",
    "unresolved_concept_count",
    "tenant_override_conflict_count",
    "policy_reject_count",
    "arbitrary_string_generation_attempt_count"
  ]
}
```
