# Compiler Functions And Entities

## Core Entities

| Entity | Meaning | Required Fields |
|---|---|---|
| `Project` | Top-level compiled system boundary. | `id`, `name`, `source_refs`, `policy_profile` |
| `Swimlane` | Independent layer of meaning under the project. | `id`, `kind`, `owner`, `node_budget` |
| `Block` | Max-50-node compile unit. | `id`, `swimlane_id`, `status`, `nodes`, `paths` |
| `Node` | Atomic domain or system concept. | `id`, `kind`, `label`, `source`, `state` |
| `Path` | Typed relationship between nodes. | `from`, `rel`, `to`, `anchor`, `confidence` |
| `Capability` | Nameable action the system can grant or compile. | `id`, `verb`, `object_kind`, `params_schema` |
| `Transition` | State movement triggered by event/capability. | `from_state`, `event`, `to_state`, `guards` |
| `Constraint` | Rule that must hold before compile or runtime effect. | `scope`, `expr`, `severity`, `falsifier` |
| `Effect` | Bounded side effect. | `kind`, `target`, `reversible`, `max_surface` |
| `Evidence` | Proof emitted by compile or runtime. | `kind`, `source_node`, `storage`, `retention` |
| `Projection` | Generated output surface. | `kind`, `target`, `artifact_path`, `node_refs` |
| `Proposal` | AI-suggested node/path/change. | `candidate`, `model`, `basis`, `decision` |

## Node Kinds

Start with the smallest useful set:

- `entity`
- `role`
- `state`
- `transition`
- `capability`
- `constraint`
- `effect`
- `evidence`
- `surface`
- `integration`
- `metric`
- `risk`

Reject vague node kinds like `feature`, `thing`, `logic`, or `system` unless they are immediately
refined into one of the canonical kinds.

## Path Kinds

| Path | Meaning | Executable Anchor |
|---|---|---|
| `owns` | authority or data ownership | grant, policy, owner record |
| `contains` | hierarchy or composition | block membership, package, schema nesting |
| `depends_on` | compile/runtime dependency | import graph, build graph, SDK call |
| `transitions_to` | state transition | state machine edge |
| `grants` | authority assignment | capability grant |
| `guards` | constraint protects action/effect | policy check |
| `emits` | node produces effect/evidence | journal/audit event |
| `projects_to` | graph creates artifact | generated output map |
| `measured_by` | metric observes node/effect | monitor/SLO/test |
| `supersedes` | versioned replacement | migration or append-only correction |

Every accepted path needs an executable anchor. If no anchor exists, the path remains a hypothesis.

## Compiler Function List

### `ingest_source`

Input: prompt, file, folder, URL crawl, framework schema, or human UI edit.

Output: normalized `SourceDoc[]` with provenance.

Rules:

- record retrieval date and source type;
- preserve source spans;
- separate human text from AI text;
- never promote imported framework defaults as accepted project truth.

### `discover_nodes`

Input: `SourceDoc[]`.

Output: `Proposal[]` for nodes and paths.

Rules:

- proposals are not accepted nodes;
- include source span and confidence;
- tag likely swimlane;
- tag missing evidence.

### `bin_swimlanes`

Input: node/path proposals.

Output: candidate swimlanes and blocks.

Rules:

- block hard limit is 50 active nodes;
- split by independence first, visual convenience second;
- cross-block paths must be typed interfaces;
- return decomposition diagnostics instead of truncating.

### `validate_block`

Input: `Block`.

Output: `ValidBlock | CompileError`.

Checks:

- node count <= 50;
- no unknown node/path kinds;
- no dangling paths;
- no ambiguous ownership;
- every effect has authority and evidence;
- every transition has source, event, target, and guard status.

### `resolve_anchors`

Input: valid block.

Output: anchored block.

Purpose: map graph claims to enforceable mechanisms.

Examples:

- `depends_on` -> import/build/IDL dependency;
- `owns` -> policy grant/owner record;
- `measured_by` -> test/monitor/SLO;
- `emits` -> journal/audit schema.

### `plan_projection`

Input: anchored block.

Output: projection plan.

Targets:

- UI route/component;
- SDK method;
- MCP tool contract;
- database migration;
- policy check;
- runtime event;
- test oracle;
- documentation page.

### `emit_projection`

Input: projection plan.

Output: generated artifacts.

Rules:

- generated files include node/path trace ids;
- no handwritten business rules appear outside compiler output;
- no artifact is emitted without a verification obligation.

### `verify_projection`

Input: generated artifacts.

Output: verification report.

Checks:

- schema validation;
- typecheck;
- transition tests;
- authority denial tests;
- snapshot of graph-to-artifact trace;
- supply-chain/provenance record.

### `record_feedback`

Input: human decisions, compile failures, runtime traces.

Output: training examples and graph deltas.

Rules:

- accepted and rejected AI proposals are both recorded;
- production observation does not mutate model weights;
- training is offline and checkpointed;
- compiler uses frozen model versions only.

## Compile Errors

Errors must be instructional, not generic.

| Error | Meaning |
|---|---|
| `TooManyNodes` | Scope exceeds 50-node block budget. |
| `UnanchoredPath` | Relationship has no executable anchor. |
| `AmbiguousOwner` | Entity/effect has unresolved authority. |
| `UnsafeEffect` | Effect lacks bounds or evidence. |
| `DanglingReference` | Path points to missing node. |
| `FrameworkAssumption` | Imported template treated as accepted truth. |
| `ProjectionDrift` | Generated artifact no longer matches source graph. |

## Minimum MVP

The first implementation only needs:

- JSON Schema for entities, blocks, proposals, and compile errors;
- deterministic validator;
- simple swimlane splitter;
- markdown/JSON diagnostics;
- React/Vite workbench later.
