---
id: wedge.private-intent-fabric-hardening
track: wedge
title: Private Intent Fabric - hardening Logic OS against telemetry becoming surveillance
model: codex
confidence: 0.82
provenance: elicited
grounding:
  - "https://security.apple.com/blog/private-cloud-compute/"
  - "https://www.chromium.org/chromium-os/chromiumos-design-docs/security-overview/"
  - "https://fuchsia.dev/fuchsia-src/concepts/kernel/concepts"
  - "https://docs.sel4.systems/Tutorials/capabilities"
  - "https://www.nist.gov/privacy-framework"
  - "https://www.nist.gov/blogs/cybersecurity-insights/differential-privacy-privacy-preserving-data-analysis"
  - "https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/agents-overview"
  - "https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/agents-are-apps"
  - "https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.2"
  - "https://developer.android.com/guide/app-actions/action-schema"
  - "/Users/srinji/logicalworks-/vision/os-spec/SPEC.md"
  - "/Users/srinji/logicalworks-/vision/artifacts/canvas-architecture-recommendation.md"
  - "/Users/srinji/logicalworks-/vision/artifacts/ecosystems.super-app-os-layer.md"
  - "/Users/srinji/sales-landing-page/CODEBOOK.md"
  - "/Users/srinji/sales-landing-page/REPO_MAP.md"
  - "/Users/srinji/sales-landing-page/governance/adr-068-data-substrate-content-addressed-fact-log.md"
  - "/Users/srinji/Downloads/Claude Research/ai_os_agent_handoff_pack/deep-research-report-2.md"
  - "/Users/srinji/Downloads/Claude Research/Research1.yaml"
  - "/Users/srinji/Downloads/Claude Research/Independent AI Insight3.yaml"
maps_to_vision: [protocol, gate, tape, ml, sovereignty, distribution]
feeds: [decision, build, ml]
expand_axes:
  - "privacy-budget-ledger"
  - "purpose-firewall-schema"
  - "brief-catalogue-compartmentalization"
  - "attested-cloud-inference-envelope"
  - "agent-quarantine-capability-model"
grounding_tool: "crwl crawl (Firecrawl alternative); W3C VC crawl blocked by Cloudflare and not relied on"
source_tiers: {primary: 10, secondary: 0, tertiary: 0}
adjudicated_by: codex-self-review
convergence: synthesis
---

## TL;DR

- The current A4/ADR-068 direction is right to reject a custom storage engine and center an E2EE fact-log, but it still over-claims "provider-blindness" before the derived-data layer is designed.
- The OS should evolve from "content-addressed fact-log + intent engine" into a **Private Intent Fabric**: local observation, local inference, proposal-only AI, deterministic authorization, replayable execution.
- Telemetry must be treated as a hazardous material. It is allowed only when typed, scoped, TTL-bound, purpose-bound, and prevented from becoming provider-observable.
- The highest-risk objects are not raw rows. They are embeddings, brief catalogues, slug resolvers, cross-device absence signals, speculative UI branches, and DP egress.
- Change the plan by making privacy enforcement a schema-level kernel primitive before intent intelligence scales.

## MAP

### Current plan, read plainly

ADR-068 and the A4 plan currently propose:

1. Append-only, content-addressed, hash-chained, E2EE fact-log as substrate of record.
2. SQLite/SQLCipher and Postgres as borrowed engines behind a portability boundary.
3. Views by replay, with relational/vector/graph projections treated as disposable read models.
4. Three-syscall API: Capability, Projection, Sync.
5. Content-hash exchange plus CRDT sync with a zero-knowledge relay.
6. Provider-blind, on-device intent extraction, with epsilon-DP weight-delta egress as the single outward learning channel.
7. Moral immutability via physics-not-policy, closed vocabulary, hash-chained governance, client-held keys, and forkability.

This is directionally strong. It fixes the CAVM draft's biggest error: confusing a novel data model with a novel storage engine. The grounded move is to own the protocol, not the database.

The plan still needs a harder privacy schema because intent-driven OS telemetry changes the threat model. The dangerous asset is not only plaintext content. It is **behavioral structure**.

### Research anchors

Apple Private Cloud Compute is useful because it does not ask users to trust a policy promise. Its public design emphasizes stateless request processing, no privileged runtime access, non-targetability, and verifiable transparency. The key lesson is not "copy PCC"; it is that private cloud AI needs enforceable architecture, not logging promises.

Chromium OS security is useful because it states the pragmatic operating-system posture: defense in depth, secure by default, process isolation, sandboxing, secure autoupdate, verified boot, encryption, and recovery. The relevant lesson for Logic OS is that seamlessness must sit on routine containment and recovery, not on a trusted monolith.

Fuchsia and seL4 are useful because they model authority as handles/capabilities with rights. Fuchsia userspace interacts with kernel objects through handles; the kernel checks handle type and rights. seL4 defines a capability as an unforgeable token with access rights. The relevant lesson is that Logic OS capabilities should not be just permission labels. They should be authority-bearing runtime objects.

NIST Privacy Framework is useful because it frames privacy as risk management for systems, not a compliance afterthought. NIST differential privacy material is useful because DP is a quantifiable privacy-loss technique, not a magic anonymization sticker.

Microsoft AOC/App Actions-style work and Google App Actions sharpen the intent layer. Microsoft 365 agents are packaged as app-like units with manifests, instructions, knowledge, and actions. Google's App Actions require declared capabilities in `shortcuts.xml` mapped to built-in intents and fulfillment. The downloaded research pack reaches the same conclusion across Apple, Google, Microsoft, Amazon, OpenAI, and Anthropic: free-form conversation is not the substrate; typed capability surfaces are.

Microsoft Recall is the warning case for this exact product temptation. Seamless context transfer is attractive, but the public reset moved toward opt-in, local storage, Windows Hello gating, just-in-time decryption, hardware-backed keys/isolation, app/site filtering, and sensitive-information filtering. The lesson is not "never capture context." The lesson is that capture-everything cannot be the primitive. Context must be source-addressable, scoped, filterable, deletable, and explainable before it becomes seamless.

### AI-first generated schema

This is the schema I would ask future AI agents to use when evaluating or extending the plan. It is intentionally strict because loose architecture prose lets AI-generated plans push back with abstractions instead of controls.

```json
{
  "schema_id": "logic-os.private_intent_fabric.v0",
  "purpose": "Constrain an intent-driven OS so telemetry remains user-owned self-instrumentation instead of provider surveillance.",
  "core_thesis": {
    "claim": "Logic OS is a privacy microkernel for intent, not an omniscient AI assistant.",
    "must_hold": [
      "raw telemetry is local-only by default",
      "AI proposes but deterministic executors mutate",
      "every data crossing carries a capability, purpose, sensitivity ring, TTL, and replay record",
      "provider-readable derived structure is forbidden unless explicitly downgraded and audited"
    ],
    "falsifier": "A provider operator, cloud process, support workflow, or aggregate model pipeline can reconstruct a user timeline without a user-held key and a logged capability grant."
  },
  "data_rings": [
    {
      "ring": 0,
      "name": "raw_private_signal",
      "examples": ["screen_text", "keystroke", "microphone", "camera", "exact_location", "raw_presence", "raw_cross_device_gap"],
      "default_location": "local_device_only",
      "default_ttl": "short",
      "egress": "forbidden",
      "projection_rule": "may produce minimized ring_1 facts only under capability"
    },
    {
      "ring": 1,
      "name": "slugged_fact",
      "examples": ["edited_doc_slug", "active_work_object", "email_thread_slug", "case_context_ref"],
      "default_location": "local_or_e2ee_sync",
      "egress": "encrypted relay only",
      "projection_rule": "can feed scoped projections"
    },
    {
      "ring": 2,
      "name": "intent_fact",
      "examples": ["likely_waiting_on_signer", "drafting_response", "context_switch_detected"],
      "default_location": "local_or_e2ee_sync",
      "egress": "forbidden unless user-directed brief or DP delta",
      "projection_rule": "must preserve source purpose and sensitivity ceiling"
    },
    {
      "ring": 3,
      "name": "projection",
      "examples": ["timeline", "work_graph", "embedding_index", "brief_catalogue", "next_action_queue"],
      "default_location": "local_partitioned_cache",
      "egress": "forbidden unless explicitly exported",
      "projection_rule": "disposable; never source of truth without re-ingest as named fact"
    },
    {
      "ring": 4,
      "name": "egress_artifact",
      "examples": ["sent_email", "exported_pdf", "cloud_inference_brief", "epsilon_dp_weight_delta"],
      "default_location": "declared_destination",
      "egress": "allowed only through audited egress gate",
      "projection_rule": "must consume privacy budget or human-directed export grant"
    }
  ],
  "kernel_planes": [
    {
      "plane": "observe",
      "rule": "capture typed minimal events; default to references, not content",
      "hardening": ["purpose_tag", "ttl", "sensitivity_ring", "source_attestation", "capability_required"]
    },
    {
      "plane": "infer",
      "rule": "run intent extraction locally first; cloud receives minimized briefs only",
      "hardening": ["work_object_partition", "model_tier_policy", "no_training_by_default", "prompt_fact_manifest"]
    },
    {
      "plane": "propose",
      "rule": "AI and agents output proposals compiled to typed action graphs, never direct effects",
      "hardening": ["agent_manifest", "proposal_schema", "typed_action_ref", "confidence", "counterfactual", "reversibility_class", "human_explanation"]
    },
    {
      "plane": "authorize",
      "rule": "governance kernel resolves capability, policy, law, purpose, location, cost, reversibility",
      "hardening": ["deny_by_default", "revocation_epoch", "privacy_budget_check", "residency_gate", "confirmation_gate"]
    },
    {
      "plane": "execute_replay",
      "rule": "deterministic executor mutates; journal before effect; replay validates",
      "hardening": ["durable_journal", "audit_anchor", "rollback_policy", "chain_verification", "projection_rebuild"]
    }
  ],
  "must_add_to_current_plan": [
    "intent_compiler",
    "agent_manifest_contract",
    "purpose_firewall",
    "privacy_budget_ledger",
    "projection_firewall",
    "brief_catalogue_compartments",
    "attested_cloud_envelope",
    "agent_quarantine_model",
    "speculative_branch_quarantine"
  ],
  "must_weaken_in_current_plan": [
    {
      "phrase": "surveillance is structurally impossible",
      "replace_with": "provider plaintext surveillance is structurally constrained if keys, projections, embeddings, brief catalogues, slug resolvers, and DP egress obey enforceable gates"
    },
    {
      "phrase": "CRDT merge guarantees deterministic convergence with no merge dialogs",
      "replace_with": "CRDTs converge only for datatypes with explicit conflict semantics; legal/business conflicts become named conflict facts"
    },
    {
      "phrase": "content-addressed facts imply dedup and semantic identity",
      "replace_with": "content hashes over encrypted envelopes provide integrity/addressing; semantic dedup requires local plaintext or deterministic encrypted structure, which is privacy-sensitive"
    }
  ],
  "ship_gate": [
    "provider_db_dump_cannot_reconstruct_timeline",
    "provider_logs_cannot_join_user_identity_to_ring_0_or_ring_1_events",
    "embedding_indices_are_local_or_e2ee_and_partitioned",
    "brief_catalogue_has_no_global_unscoped_join",
    "cloud_inference_requires_attested_stateless_envelope_or_explicit_user_export",
    "dp_egress_fails_when_budget_exhausted",
    "intent_engine_down_means_apps_degrade_not_break",
    "revoked_capability_blocks_observe_infer_project_execute_sync_export"
  ]
}
```

## SCALE & CONSTRAINTS

### Where the current plan works

The fact-log is a good substrate because it gives replay, portability, auditability, and local-first sync a common base. SQLite/Postgres behind a portability boundary is exactly the right level of ambition for a small team.

The three-syscall API is the most valuable anti-slop primitive. It prevents AI-generated code from inventing raw storage paths. If Capability, Projection, and Sync become the only ways in and out, the OS can remain understandable.

Provider-blindness is the right moral invariant. It forces architecture to remove the asymmetric watcher rather than merely promising that the watcher will behave.

### Where the current plan fails if unchanged

The plan currently treats E2EE fact storage as if it largely solves privacy. It does not. An intent OS's highest-value private asset is the inferred structure: embeddings, intent facts, brief catalogues, slug maps, cross-device absence intervals, ranking weights, and speculative UI branches.

The plan risks building a global "brief catalogue" that re-aggregates what vaults compartmentalize. If the catalogue can answer "what is the user doing across everything," it is a local surveillance database. If it is later synced or used for model improvement, the provider-blind wall fails.

The plan leans on epsilon-DP egress without yet defining a privacy-loss budget, accountant, per-user/model ledger, reset policy, or adversarial memorization tests. DP without budget governance is a claim, not a control.

The plan leans on CRDT language too broadly. CRDTs are useful for low-risk convergence. They do not resolve domain-level conflicts like legal state, billing status, user consent, or destructive actions.

The plan needs an explicit cloud inference envelope. Apple PCC shows the bar: stateless processing, no privileged runtime access, verifiable transparency, non-targetability, and narrow operational telemetry. Without that, cloud AI is just a provider-visible computation path.

### Real-world constraints

ChromeOS-level concurrency comes from modularity, sandboxing, process isolation, verified boot, recovery, and "secure by default" posture. Logic OS should not chase one giant resident intelligence process. It should run work-object actors, projection actors, agent actors, and device actors over an append-only fact substrate.

Apple-level seamlessness comes from owning identity, local execution, handoff, and hardware/software integration. Logic OS cannot own the hardware stack initially, so it must simulate the same trust properties with signed components, local vaults, passkey/device keys, strict capabilities, and encrypted handoff.

Capability kernels show the right shape for authority. A "permission string" is not enough. A Logic OS grant should behave like a handle: scoped, typed, rights-bearing, TTL-bound, revocable, and auditable.

## TOUCHES US

### Changes I would make to A4 / ADR-068

1. Promote **purpose firewall** to A4.2 or A4.3. A fact collected for handoff must not silently feed model training, ranking, analytics, or product telemetry.

2. Split "views by replay" into two classes:
   - ordinary disposable projections;
   - sensitive derived projections requiring separate capability and TTL, including embeddings, intent graphs, brief catalogues, and slug resolvers.

3. Make **privacy budget ledger** a first-class kernel object before epsilon-DP egress ships.

4. Replace broad "provider-blindness" claims with testable invariants:
   - cloud dump cannot reconstruct timeline;
   - logs cannot join identity to request;
   - projections are partitioned;
   - cloud inference is stateless or forbidden;
   - egress consumes budget or explicit human export grant.

5. Add **attested cloud envelope** as the only acceptable path for non-local model inference over sensitive briefs.

6. Add **speculative branch quarantine** for predicted UI. Speculative facts must not train the model, sync as truth, or affect downstream automation until chosen.

7. Add **intent compiler** as a real layer. Natural language must terminate in a typed action graph over known entities, ambiguity markers, and capability references. It must not compile directly to side effects.

8. Treat agents and WASM modules as apps. They receive manifests and capabilities, not trust. The manifest should declare instructions, knowledge sources, actions, connected agents, data rings, egress class, and review gates.

### Evolution path from current plan

| Current plan object | Keep | Change | Resulting stronger object |
|---|---|---|---|
| E2EE fact-log | yes | add data rings and purpose tags | privacy-aware substrate |
| Capability API | yes | convert grants into handle-like authority objects | object-capability gate |
| Projection API | yes | add sensitive projection firewall | projection cannot become shadow surveillance |
| Sync API | yes | sync hashes/facts/revocations, not global behavioral catalogues | blind handoff fabric |
| Intent engine | yes | local-first, typed-compiler, proposal-only, fail-open-to-dumb | private intent service |
| Agent runtime | yes | app-like manifests + separate principal identity | auditable agent workspace |
| DP egress | yes, later | require accountant, budget ledger, adversarial tests | controlled learning outlet |
| Moral immutability | yes | weaken impossible claims; make tests executable | trustable Ulysses pact |

## BUILD-NOW

1. Define `PrivateIntentGrant` as the next capability schema.
   - subject, object, rights, sensitivity ceiling, purpose, processing location, TTL, revocation epoch, audit class, training class.

2. Define data rings in protocol.
   - Every event and projection must declare `ring`, `purpose`, `ttl`, `work_object_id`, `policy_bundle_id`, `source_device_id`.

3. Add `PurposeFirewall` to the gate.
   - Same fact cannot move from handoff to training or analytics without a new named grant.

4. Add `ProjectionFirewall`.
   - Embeddings, brief catalogue, slug resolver, and cross-device gap index are not ordinary caches. They are sensitive derived stores.

5. Add `PrivacyBudgetLedger`.
   - No epsilon-DP egress path without budget accounting and failure mode tests.

6. Add `AttestedCloudEnvelope`.
   - Cloud model path must declare software measurement, statelessness, retention, operator-access class, request unlinkability, and transparency log reference. If this cannot be proven, classify it as explicit user export, not private compute.

7. Add `SpeculativeBranch`.
   - Predicted UI/actions are effect-free until accepted. Killed branches get a short TTL and cannot train models unless user explicitly opts in.

8. Add `IntentCompiler`.
   - Natural language compiles into typed action graphs over known entities. Unsupported or ambiguous requests become clarification prompts or contained fallback tasks, not invisible execution.

9. Add `AgentManifest`.
   - Every agent is an app-like principal with instructions, knowledge sources, actions, allowed connected agents, data rings, egress class, and review gates. Microsoft's manifest/app-package direction and Google's `shortcuts.xml` capability declarations both point to this shape.

## SKEPTICISM

### Sharp pushback the plan should accept

The plan is still too comfortable with AI-native vocabulary. "Intent," "brief," "semantic projection," and "self-learning" are precisely the concepts that become surveillance when joined. The OS should assume these are toxic until proven otherwise.

Provider-blindness is not a single property. It is a bundle:

- no plaintext provider storage;
- no provider-readable derived structure;
- no linkable request logs;
- no privileged cloud access;
- no global brief catalogue;
- no unbudgeted egress;
- no model training without purpose-specific grant.

If any one of those fails, the system may still be encrypted, but it is not provider-blind in the sense the vision needs.

### What someone else does better

Apple has the hardware and vertical integration to make privacy feel invisible. Logic OS does not. It must compensate by making authority and data movement more explicit.

Microsoft is ahead on enterprise agent packaging and separate agent identity/workspace direction, but Recall shows the cost of getting context capture wrong. Logic OS should start with the post-backlash design, not repeat the pre-backlash design.

Google is ahead historically on OS-level intent routing through Android Intents and App Actions, but Google's Conversational Actions retirement reinforces the same warning: untyped conversation is a weak platform substrate.

ChromeOS has a mature verified boot, sandbox, update, and recovery posture. Logic OS does not. It must avoid pretending an E2EE fact-log is an OS security model.

Fuchsia/seL4 have cleaner authority primitives. Logic OS should borrow the capability discipline rather than inventing permission labels with poetic names.

### What would falsify this recommendation

If measured product usage shows that the OS can deliver seamless handoff and intent assistance with only external refs plus coarse local signals, then many high-risk telemetry pathways should never be built.

If attested cloud inference remains commercially or technically unavailable outside Apple-like vertical stacks, then the plan should stay local-first and downgrade cloud reasoning to explicit export.

If users reject scoped consent because it is too noisy, the answer is not broad consent. The answer is better defaults and fewer prompts, with stronger static policy.

## DIALECTIC

thesis: The current A4/ADR-068 plan is the right foundation: E2EE fact-log, borrowed engines, replay projections, capability API, zero-knowledge sync, and provider-blind intent learning can produce Apple-like seamlessness without provider surveillance.

antithesis: The plan is under-specified at the derived-data layer. An intent OS can become surveillance without plaintext if it centralizes embeddings, brief catalogues, slug maps, absence signals, ranking state, or DP deltas. The current plan's strongest privacy claims outrun its enforceable controls.

synthesis: Keep the substrate and three-syscall direction, but insert a Private Intent Fabric schema before intelligence scales. The fabric makes data rings, purpose, capabilities, projection sensitivity, privacy budget, and cloud attestation first-class. AI remains proposal-only. Deterministic governance executes.

residual_disagreement: How much telemetry is necessary for a useful first OS wedge remains unmeasured. The matched comparison is a local prototype that measures task-completion lift across three modes: external refs only, slugged facts plus local intent, and richer local telemetry with strict TTL.

## FALSIFICATION

- If provider dumps, logs, or model pipelines can reconstruct user timelines, provider-blindness is false.
- If embeddings or brief catalogues are readable outside the user's key domain, the derived-data firewall is false.
- If cloud inference cannot prove statelessness and no privileged access, it must be classified as explicit export.
- If CRDT sync produces hidden domain conflict resolution for legal, billing, consent, or destructive state, the convergence claim is false.
- If apps break when the intent engine is disabled, fail-open-to-dumb is false.

## DELTA_LOG

Before: The E2EE fact-log plus local intent engine looked like the main privacy answer.

After: The fact-log is necessary but insufficient. The real privacy boundary is the movement from raw signals to derived projections and egress. This must be governed before intent features grow.

Evidence that changed the weighting: Apple PCC's requirements show how much architecture is needed before cloud AI privacy claims are credible. Chromium OS's design emphasizes defense in depth and secure defaults over single-control confidence. Fuchsia and seL4 show that authority should be embodied as typed handles/capabilities, not labels. NIST frames privacy as managed risk, which fits the need for purpose and budget ledgers.

Additional evidence from the downloaded research pack and follow-up crwl pulls sharpened the action model: Microsoft 365 agents and Google App Actions both use manifest/capability surfaces; Microsoft's Recall reset is the clearest live warning that local semantic context without explicit consent, isolation, filtering, and deletion becomes a privacy backlash. This confirms that the fabric needs an `IntentCompiler` and `AgentManifest` layer, not only telemetry privacy controls.

## HALLUCINATION_RISK

- Apple Foundation Models details: medium. The crwl pull for Apple's developer docs produced navigation-heavy content, so this artifact does not rely on specific Foundation Models claims beyond the local/on-device direction already supported by PCC and local docs.
- W3C Verifiable Credentials: medium. The crwl pull was blocked by Cloudflare, so this artifact does not rely on VC-specific claims.
- "Apple-like seamlessness" mapping: low-to-medium. The analogy is elicited from OS behavior and PCC design, not a direct Apple architecture disclosure.
- Privacy-budget implementation shape: medium. NIST grounds DP as privacy-risk tooling, but the exact ledger schema is a design recommendation that needs prototype validation.

## ML-FEED

```json
{
  "entities": [
    {"id": "pif-private-intent-fabric", "type": "architecture", "label": "Private Intent Fabric"},
    {"id": "pif-data-ring", "type": "schema", "label": "Telemetry Data Rings"},
    {"id": "pif-purpose-firewall", "type": "gate", "label": "Purpose Firewall"},
    {"id": "pif-projection-firewall", "type": "gate", "label": "Projection Firewall"},
    {"id": "pif-privacy-budget-ledger", "type": "ledger", "label": "Privacy Budget Ledger"},
    {"id": "pif-attested-cloud-envelope", "type": "boundary", "label": "Attested Cloud Envelope"},
    {"id": "pif-speculative-branch", "type": "runtime", "label": "Speculative Branch Quarantine"},
    {"id": "pif-intent-compiler", "type": "compiler", "label": "Intent Compiler"},
    {"id": "pif-agent-manifest", "type": "manifest", "label": "Agent Manifest"}
  ],
  "relations": [
    ["pif-private-intent-fabric", "hardens", "ADR-068"],
    ["pif-intent-compiler", "compiles_language_to", "typed_action_graph"],
    ["pif-agent-manifest", "declares", "instructions_knowledge_actions_boundaries"],
    ["pif-purpose-firewall", "guards", "observe_to_infer"],
    ["pif-projection-firewall", "guards", "derived_data"],
    ["pif-privacy-budget-ledger", "guards", "dp_egress"],
    ["pif-attested-cloud-envelope", "guards", "cloud_inference"],
    ["pif-speculative-branch", "guards", "predictive_ui"]
  ],
  "metrics": [
    "provider_timeline_reconstruction_success_rate",
    "raw_signal_egress_count",
    "projection_scope_violation_count",
    "privacy_budget_exhaustion_count",
    "cloud_inference_without_attestation_count",
    "untyped_intent_execution_attempt_count",
    "agent_without_manifest_count",
    "intent_engine_disabled_task_success_rate",
    "speculative_branch_training_leak_count"
  ]
}
```
