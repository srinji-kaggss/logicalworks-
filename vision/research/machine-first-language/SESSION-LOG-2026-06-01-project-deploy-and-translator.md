# SESSION LOG — 2026-06-01 — Project Deploy, Worker Cap, Translator Spec

Status: declarative handoff for the next agent. This is a record of decisions, artifacts, commits,
and remaining work. It is not hidden chain-of-thought.

## Vocabulary Fixed

- **Model** = Deep ML layer.
- **AI** = LLM/Tongue layer.
- **Machine** = lgwks orchestrator/intent engine using deterministic logic plus future Deep ML.
- **CLI** = compiler/runtime surface that validates, renders, executes, and logs.

The Director corrected the architecture: AI fits intent into schema; Model translates between AI,
human preview, and executable command form.

## Commits Created This Session

1. `6abae2e Specify end-to-end project deploy hypotheses`
   - Added `SPEC-project-deploy-e2e-v1.md`.
   - Established hypotheses, pass/fail gates, cycle ledger, worker lease, critic record, model state,
     deploy/review command contracts.

2. `87e5d45 Add AI ML layer map for Machine orchestrator`
   - Added `AI_ML_LAYER_MAP.md`.
   - Separated ML, transformer ML, Assistant AI, and Machine layers.

3. `da995c1 Add one-prompt project orchestrator plan`
   - Added `lgwks_project.py`.
   - Added `SPEC-project-orchestrator-v1.md`.
   - Implemented `lgwks project plan`.

4. `81bf1a6 Harden crawler auth and add project vector vault`
   - Added auth runtime, public source layer, deterministic project memory, and vector vault.
   - Hardened URL/cache/session boundaries.

5. `91b556a Build one-command project deploy artifacts`
   - Added `lgwks_cycle.py`.
   - Added `lgwks project deploy` and `lgwks project review`.
   - Deploy writes typed artifacts: cycles, leases, token ledger, critic records, model state, model
     lineage, learning records, graph edges, MachinePackets, operator profile.

6. `f4344f6 Finish non-ML project deploy execution`
   - `project deploy --execute` composes existing non-ML modules: `lgwks_memory`, `lgwks_public`,
     `lgwks_embed`.
   - Added source records, execution events, vector vault summary, and `review --render`.
   - Auth/private crawl deliberately skipped until final hacker review.

7. `2bc030b Cap project workers and embed deploy artifacts`
   - Hard-capped workers at 4.
   - Added `worker-map.json`.
   - Added `artifact-embeddings.jsonl` for immediate deterministic local embedding of deploy artifacts.
   - Updated tests to 105 passing.

## Current Working Tree At Handoff

- Source/doc changes from prior work are committed.
- `store/` remains untracked runtime output.
- The next agent should not assume `store/` is source-of-truth code.

## Implemented CLI State

### `lgwks project plan`

Turns one prompt into a bounded plan with:

- default reasoning cycles = 5
- default embedding rounds = 400
- worker budget
- branch worker roles
- next lgwks commands

### `lgwks project deploy --dry-run`

Writes the same artifact shape without live source fetches:

- `cycles.jsonl`
- `leases.jsonl`
- `token-ledger.jsonl`
- `critic-records.jsonl`
- `machine-packets.jsonl`
- `learning-records.jsonl`
- `model-lineage.jsonl`
- `graph-edges.jsonl`
- `model_state.json`
- `operator-profile.json`
- `worker-map.json`
- `artifact-embeddings.jsonl`
- empty/placeholder execution/source/vector artifacts

### `lgwks project deploy --execute`

Runs only non-ML, non-auth existing modules:

- memory scope/context
- open-license public source search
- deterministic local vector vault when `--folder` is provided
- execution event logging
- auth/private crawl skipped with a recorded event

### `lgwks project review`

Reports:

- chain integrity
- cycle count
- token status
- bias counts
- unsupported claims
- rollback ref
- source count
- vector status
- machine packet count
- graph edge count
- model lineage count
- artifact embedding count
- worker slot cap

### `lgwks project review --render`

Human projection only. JSON remains source of truth.

## Worker Cap Decision

Observed host:

```text
RAM_total = 24 GiB
CPU_total = 15 cores
```

Director clarified that the Deep ML Model is always running. Worker cap must include that reserve.

Formula:

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

For this Mac:

```text
memory_cap = floor((24 - 6 - 8 - 2) / 2) = 4
cpu_cap = floor((15 - 5) / 1) = 10
max_workers = 4
```

The cap remains 4 because Deep ML is resident.

## New Spec Added

`SPEC-geometric-cli-translator-v1.md`

Purpose:

- Define a multiplication/geometric CLI command schema.
- Deep ML Model translates between AI schema, human preview, and command plan.
- AI/Tongue debugs and clarifies mismatches.
- CLI validates and executes argv/effects.

Core loop:

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

## Architectural Decisions

- Product is the next CLI, not another crawler.
- Crawling is one engine behind the CLI.
- AI should not permanently own translation.
- Deep ML should learn the translation layer.
- CLI should act like a bidirectional intent compiler.
- Human-visible output should be a projection of typed artifacts.
- Every correction is training material.
- Every artifact gets embedded immediately and locally.
- API-keyed providers should be optional later, not required by default.

## Verification Performed

At the last committed implementation point:

- `/opt/homebrew/bin/python3 -m unittest discover tests` passed with `105 tests`.
- `git diff --check` passed.
- Smoke with `--max-workers 99` reviewed as `workers 4/4`.
- Smoke reported `artifact embeddings 55`.

## Remaining Work

1. ~~Implement mathematical worker cap as a computed artifact rather than a constant.~~ DONE.
   - New module `lgwks_workercap.py`: `probe_host()` + `compute_worker_cap(role_count, host=, reserves=)`.
   - `MAX_CONCURRENT_WORKERS` constant removed; cap computed from host formula per deploy/plan.
   - Director decisions encoded: formula cap is a *ceiling*; active slots stay bound to the 4 defined
     mapper roles (`MAPPER_ROLES`); host is probed live (`os.sysconf` RAM + `os.cpu_count`), overridable
     and pinned via `LGWKS_HOST_RAM_GIB`/`LGWKS_HOST_CPU` so artifacts replay deterministically.
   - Model reserve (8GiB) is a named input in `reserves`, stamped into `worker-map.json` + plan/deploy
     budgets under `worker_cap`. 24GiB/15cpu → 4 (cap_basis=role_count); 64GiB+ records higher headroom
     but cap stays 4 until a 5th role is added. Tests: `TestWorkerCap` (5) + host-pinned planner suite.
     110 tests pass.

2. Implement the geometric CLI translator.
   - Add `GeoExpr`, `HumanPreview`, `CommandPlan`, `CorrectionRecord` schemas.
   - Extend or wrap `lgwks x`.
   - Do not execute shell strings as source of truth.

3. Build Deep ML translator later.
   - Model translates schema/human/command forms.
   - AI/Tongue handles low-confidence and correction flows.
   - No training until held-out eval and rollback gates exist.

4. Add correction ledger.
   - Human correction.
   - AI schema correction.
   - Model translation error.
   - Execution surprise.

5. Final hacker review.
   - Hold until auth/private crawling is ready.
   - Review local-device consent, auth scope, cache/log leakage, source boundaries.

## Explicit Deferrals

- No ML training was implemented.
- No auth/private crawl was enabled.
- No worker process pool was implemented.
- No geometric CLI translator was implemented.
- No hidden API-key dependency was introduced.

