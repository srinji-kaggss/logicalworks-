# SPEC-geometric-cli-translator-v1

Status: SPEC only. Do not implement in this slice.

## 0. Definitions

This spec uses the Director's vocabulary:

- **Model** means the Deep ML layer. It is the learned translator/scorer, not the LLM.
- **AI** means the LLM/Tongue layer. It proposes, explains, debugs, and clarifies.
- **CLI** means the deterministic compiler/runtime. It validates schemas, renders to humans, executes
  safe argv/effects, and records outcomes.

Core correction: the AI should not permanently own translation. The AI fits intent into a schema; the
Deep ML Model translates between AI schema, human preview, and executable command form.

## 1. Product Goal

Build a multiplication-based CLI converter where AI communicates in a compact geometric/mathematical
command form, the Model translates and normalizes it, the CLI renders the human-safe view, and the CLI
executes only validated commands.

This replaces acronym-heavy command grammar with a mathematical form:

```text
intent -> geometric expression -> Model translation -> human preview -> compiled argv/effect plan
```

The human should see a legible workflow. The AI should see a compact schema. The Model should learn
the bidirectional mapping between both.

## 2. Core Architecture

```text
AI/Tongue
  role: express task intent into a typed geometric schema; debug failures

Deep ML Model
  role: translate AI schema <-> human preview <-> command AST
  inputs: schema, prior corrections, execution outcomes, local embeddings
  outputs: normalized schema, confidence, mismatch flags, correction prompts

CLI Compiler
  role: deterministic validation, expansion, rendering, argv/effect execution
  outputs: execution log, correction ledger, embedding records
```

The normal path is:

```text
AI intent
  -> GeoExpr schema
  -> Model normalize/translate/score
  -> HumanPreview
  -> user approve/correct
  -> CommandPlan
  -> CLI executes argv without shell
  -> ResultTranscript
  -> CorrectionLedger + ArtifactEmbeddings
  -> Model training material
```

The fallback path is:

```text
low confidence | schema mismatch | execution surprise
  -> AI/Tongue explains gap
  -> user or AI corrects schema
  -> Model receives supervised correction record
```

## 3. Mathematical Command Form

The command expression should be an AST, not shell prose.

```json
{
  "schema": "lgwks-geoexpr/1",
  "op": "product",
  "axes": [
    {"name": "verb", "values": ["git.status", "git.log", "git.diff"]},
    {"name": "scope", "values": ["repo.current"]}
  ],
  "constraints": {
    "risk_max": "read",
    "worker_cap": "auto",
    "requires_human_preview": true
  },
  "expected": {
    "artifacts": ["status", "recent_history", "diff_stat"],
    "question": "what changed and is it safe?"
  }
}
```

The compiler expands `product(verb x scope)` into validated commands. It never executes opaque shell
strings as authority.

## 4. Translation Objects

### 4.1 Human Preview

```json
{
  "schema": "lgwks-human-preview/1",
  "summary": "Check repo status, recent history, and diff stats.",
  "steps": [
    {"label": "Status", "effect": "read repo state"},
    {"label": "Recent history", "effect": "read last commits"},
    {"label": "Diff stat", "effect": "read working diff summary"}
  ],
  "risk": "read",
  "approval": "auto_allowed|ask|deny"
}
```

### 4.2 Command Plan

```json
{
  "schema": "lgwks-command-plan/1",
  "plan_id": "sha256",
  "source_expr": "geoexpr-sha",
  "commands": [
    {"argv": ["git", "status"], "risk": "read", "why": "repo state"},
    {"argv": ["git", "log", "-5", "--oneline"], "risk": "read", "why": "recent history"},
    {"argv": ["git", "diff", "--stat"], "risk": "read", "why": "diff summary"}
  ],
  "compile_policy": {
    "shell": false,
    "unknown_requires_review": true,
    "destructive_requires_force": true
  }
}
```

### 4.3 Correction Record

```json
{
  "schema": "lgwks-correction/1",
  "source_expr": "geoexpr-sha",
  "failure_type": "human_misread|ai_schema_error|model_translation_error|execution_surprise",
  "before": {"summary": "old human preview or plan"},
  "after": {"summary": "corrected human preview or plan"},
  "corrected_by": "human|ai|model|execution",
  "training_use": "local_only",
  "embedding_ref": "artifact-embedding-sha"
}
```

## 5. Deep ML Translator Duties

The Model owns:

- schema normalization
- geometric expression similarity
- human preview generation/ranking
- command-plan ranking
- confidence scoring
- mismatch detection
- correction example clustering
- learned user/AI style mapping

The Model does not own:

- policy gates
- effect execution
- destructive approval
- source-of-truth logs
- final rollback decisions

## 6. AI/Tongue Duties

The AI owns:

- forming initial `GeoExpr`
- explaining translation gaps
- asking clarifying questions when the Model or compiler flags ambiguity
- translating correction records into useful development guidance
- debugging mismatches between AI intent, human preview, and command result

The AI should activate primarily on:

- low Model confidence
- schema validation failure
- human correction
- unexpected execution result
- request for explanation

## 7. Worker And Memory Formula

Target host observed in this session:

```text
RAM_total = 24 GiB
CPU_total = 15 cores
```

The Deep ML Model is assumed always resident.

Worker cap formula:

```text
RAM_available_for_workers =
  RAM_total
  - OS_and_apps_reserve
  - always_on_deep_ml_model_reserve
  - safety_reserve

memory_cap = floor(RAM_available_for_workers / per_worker_reserve)
cpu_cap = floor((CPU_total - cpu_reserve_for_model_and_system) / cpu_per_worker)
max_workers = clamp(min(memory_cap, cpu_cap), 1, configured_upper_bound)
```

For the 24GB / 15-core Mac:

```text
RAM_total = 24
OS_and_apps_reserve = 6
always_on_deep_ml_model_reserve = 8
safety_reserve = 2
per_worker_reserve = 2

memory_cap = floor((24 - 6 - 8 - 2) / 2) = 4

CPU_total = 15
cpu_reserve_for_model_and_system = 5
cpu_per_worker = 1
cpu_cap = 10

max_workers = min(4, 10) = 4
```

Therefore the current non-ML mapper cap remains 4 when the always-on Deep ML layer is included. A
future larger-memory host may raise this automatically, but the formula must be recorded in
`worker-map.json`.

## 8. Pass Conditions

- AI emits `GeoExpr`, not shell prose, for normal command translation.
- Deep ML Model translates `GeoExpr` to `HumanPreview` and `CommandPlan` with confidence.
- CLI validates schema and compiles to argv without shell execution.
- Human preview is rendered from the command plan, not manually authored as the source of truth.
- Every translation, correction, preview, command plan, and execution result is embedded locally.
- Deep ML always-running memory reserve is included in worker-cap math.
- AI/Tongue is invoked for debug/clarification, not as the default deterministic compiler.

## 9. Non-Goals

- No implementation in this slice.
- No real model training in this slice.
- No destructive command expansion without existing approval gates.
- No keyed external translation provider by default.
- No replacing `lgwks x`; this spec is the next-generation compiler behind it.

