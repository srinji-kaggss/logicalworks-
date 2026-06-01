# SPEC-project-deploy-e2e-v1

Status: non-ML implementation slice implemented. ML/model-training work remains gated behind the later
learning slice.

## 0. Doctrine Alignment

This spec applies the fleet doctrine:

- Semantic awareness: deploy must make sense against `SPEC-project-orchestrator-v1`,
  `SPEC-lgwks-engine-v0`, and `AI_ML_LAYER_MAP`.
- Production-grade review: every loop has pass/fail evidence, not "seems good."
- Scope guard: this is the next downstream node after `project plan`; do not absorb model training,
  dashboard polish, or cloud infra beyond the first deployable slice.
- Vendor-agnostic: local deterministic fallback first; semantic model provider is optional and
  recorded by manifest, not hardcoded into the contract.
- AI-for-AI rationale: the primary output is machine-readable cycle records.
- User-owned learning: raw prompts, transcripts, auth context, and private crawls belong to the user.
  lgwks may learn locally from them only through an explicit vault/membrane contract; it does not own,
  export, or remotely train on them by default.
- Local operator posture: when the user grants local-device consent, the CLI may behave like an
  automated research operator on that device. The privacy boundary is not "never inspect local
  context"; it is "never turn user-owned local context into operator-owned telemetry or hidden remote
  training data."

## 0.1 Hardening Layer Run

Automated lgwks feedback, 2026-06-01:

- `lgwks refine ... --agent --depth 1` accepted the task (`abstain:false`, `specificity:1.0`) but
  classified it as `comparison` with only `0.5` confidence. Hardening implication: the Machine needs
  a stronger intent taxonomy for "design/harden a private learning substrate" instead of squeezing it
  into generic comparison/build buckets.
- `lgwks project plan machine-intent-slop-model ... --embedding-rounds 400 --max-workers 6` produced
  the expected worker frame and repeated the known deploy gaps: leases, semantic provider, held-out
  critic eval, champion/challenger promotion, and token ledger enforcement.

Independent hardening feedback:

- The first spec slice is strong on deploy auditability, but thin on the learning substrate that the
  Director is asking for: model lineage, OSS license pinning, on-device/CoreML conversion, private
  transcript learning, graph learning, and AI-to-AI packet output.
- "Learning" must not mean hidden fine-tuning. It must mean typed learning records, redaction,
  held-out evaluation, adapter/checkpoint lineage, and rollback before any weight promotion.
- The Machine should not be optimized to talk to humans. Its native output should be compact packets
  for other AIs and lgwks engines; human renderers are a projection.
- The product is the next CLI, not the next crawler. Crawling is one engine behind the verb; the
  user-facing promise is "one research command replaces the many commands the user would have typed."

AI-Research-SKILLs reuse map:

- Orchestration: autoresearch two-loop, but local lgwks deploy owns the heartbeat and artifact store.
- Research artifact: ARA compiler/research-manager/rigor-reviewer shapes the claim/evidence/DAG
  artifacts; lgwks stores them as project deploy JSONL.
- Retrieval: sentence-transformers/FAISS/Qdrant class capabilities inform the vector path; deterministic
  vectors remain the fallback.
- Model spine: BERT/ModernBERT/E5/BGE/UniXcoder class encoders feed PEFT/adapters and CoreML export;
  lgwks adds lineage and local-device consent.
- Evaluation/observability: lm-evaluation-harness/Phoenix/LangSmith class patterns inform held-out eval
  and trace review; lgwks keeps the pass/fail gate local and replayable.

## 1. End-to-End User Story

One prompt:

```bash
lgwks project deploy salesforce \
  --prompt "map Salesforce as an AI-operating-system competitor" \
  --reasoning-cycles 5 \
  --embedding-rounds 400
```

Must produce:

1. project memory initialized
2. branch-worker plan
3. cycle ledger
4. token ledger
5. evidence/source records
6. root vector vault + sub-vaults
7. critic records
8. next-command proposals
9. review surface with chain head, bias flags, contradictions, rollback point
10. model lineage manifest for any ML path used
11. learning-record ledger for transcript/input-derived training signals
12. AI-to-AI machine packets (`MachinePacket`) separate from human prose
13. operator profile capturing research-only steering, one-command orchestration, and experiment lanes
14. worker map capped at four concurrent internal mapper slots
15. artifact embedding ledger for transcript, learning material, source records, packets, and metadata

Deploy may be `--dry-run` first. `--dry-run` must emit the same DAG and record schemas without
network fetches. It still embeds the deploy artifacts locally because embeddings are deterministic,
local, and part of the Machine's memory substrate. `--execute` in the non-ML slice may execute only existing lgwks verbs:
memory initialization/context, open-license public search, deterministic embedding vaults, and review
rendering. Authenticated crawling, hidden session reuse, model calls, and weight updates are deferred.

## 2. Core Hypothesis

H0: A deterministic harness can make AI-assisted research more reliable than a single prompt by
forcing every cycle through:

```text
intent -> query_form -> evidence_attention -> bias_flags -> next_command -> eval_result
       -> learning_record -> candidate_delta -> weight_update
```

Success does **not** mean the Machine becomes AGI. Success means the Machine produces replayable,
auditable, bias-aware research cycles that improve retrieval/ranking data over time.

H0b: A private Machine can become a better intent mapper without owning user data by training only
local, user-controlled adapters or candidate weights from typed learning records derived from:

```text
raw input -> redaction -> intent features -> said/meant/true divergence -> slop labels
          -> held-out eval -> challenger adapter -> CoreML/ANE export -> frozen champion
```

Success means the Machine gets measurably better at mapping human desire through text and recognizing
AI-slop failure chains while preserving user ownership and rollback.

## 3. Hypotheses and Pass Conditions

### H1 — Cycle records make workers deterministic enough

Claim: workers become reviewable when each worker reads a chain head and writes a typed cycle record.

Pass:

- `lgwks project deploy --dry-run` writes `cycles.jsonl`.
- Every cycle has `intent`, `query_form`, `evidence_attention`, `bias_flags`, `next_commands`,
  `eval_result`, `weight`, `prev`, `hash`.
- Tampering with one cycle makes `project review` report `chain_ok:false`.

Fail:

- worker output is only stdout/prose
- cycle hashes do not bind previous cycle
- next commands lack query form or budget source

### H2 — Bias stripping improves by plane separation

Claim: separating human, AI, prompt, and cognitive bias creates actionable critique rather than vague
"be unbiased" instructions.

Pass:

- each critic record may emit `human_bias`, `ai_bias`, `prompt_bias`, `cognitive_bias`
- at least one disproof query form is scheduled in the first 5 cycles
- unsupported claims are marked `unsupported`, not promoted

Fail:

- bias is a single scalar only
- disproof is absent from default cycles
- no-evidence cycles produce conclusions

### H3 — Deterministic + semantic embeddings reveal useful disagreement

Claim: dual embeddings are more useful than one vector space.

Pass:

- root vault and each sub-vault record stores deterministic vector fields
- if semantic provider is configured, the record stores `semantic_embedding`, `semantic_model`, and
  `agreement_score`
- critic can flag `lexical_collision` and `concept_bridge`

Fail:

- semantic provider replaces deterministic vectors
- records cannot be replayed without the semantic provider
- vector records lose file/path/chunk provenance

### H4 — Token ledger constrains the loop

Claim: the prompt form can bound reasoning spend.

Pass:

- each cycle records `token_budget`, `estimated_tokens`, and `token_status`
- default reasoning cycles = 5
- deploy refuses to continue when the ledger exceeds budget unless user passes a review flag

Fail:

- cycles are unbounded
- token counts are absent
- budget is only shown in prose

### H5 — Auth is used only when granted and missing auth is actionable

Claim: keychain/session auth can be helpful without becoming bypass behavior.

Pass:

- active keychain/session host gets auth headers/session only for matching host
- missing keychain secret appends sanitized `needs_auth.jsonl`
- 401/403 appends sanitized `needs_auth.jsonl`
- no token appears in logs, cache index, cycle records, or test output

Fail:

- auth is sent to unrelated host
- query/userinfo/token leaks into logs
- missing auth silently drops source without a JSON request

### H6 — Learning is gated by rollback

Claim: "micro-evolution" is safe only if every challenger can be rejected.

Pass:

- deploy creates a `model_state.json` with champion snapshot id
- challenger scores are written separately from champion
- promotion requires held-out score improvement and no contradiction-recall regression
- review reports rollback ref

Fail:

- challenger overwrites champion
- no held-out eval record exists
- promotion is based on model self-report

### H7 — User-owned transcript learning stays inside the membrane

Claim: the corpus can teach the Machine without becoming an operator-owned data asset.

Pass:

- raw transcript/private crawl text is stored only in the user's vault or local cognition log
- every learning record has `source_scope`, `redaction_status`, `consent`, and `export_policy`
- default export policy is `local_only`
- derived features are reproducible from local artifacts, but remote training receives no raw user data
- delete/export commands can remove or materialize the user's corpus without hidden replicas

Fail:

- raw user prompt text appears in model-lineage manifests, public logs, cache indexes, or test output
- learning proceeds when consent/export policy is absent
- training data is treated as lgwks-owned telemetry

### H8 — OSS/CoreML model spine is pinned before use

Claim: a custom weight set is trustworthy only when every base model and conversion step is pinned.

Pass:

- model lineage records include `base_model`, `upstream_url`, `upstream_license`, `upstream_sha256`,
  `conversion_tool`, `quantization`, `adapter_hash`, and `coreml_hash`
- accepted base paths include OSS text encoders (BERT/RoBERTa/ModernBERT class), sentence embedding
  models, graph models, and local rerankers only when their licenses are recorded and compatible
- champion weights are immutable; all learning writes challenger adapters or candidate snapshots
- CoreML/ANE export is a deploy artifact, not the source of truth

Fail:

- model is named without a license/hash
- conversion changes behavior without an eval record
- challenger weights mutate the champion in place

### H9 — Deep learning pathways are separated by job

Claim: one monolithic "AI model" is weaker and less auditable than typed pathways.

Pass:

- BERT/transformer encoder path maps text to intent, entity, gap, and said/meant divergence features
- sentence embedding/reranker path maps chunks to retrieval/ranking scores
- GNN/temporal graph path maps `intent -> cycle -> source -> claim -> contradiction -> next_command`
  edges and predicts uncertainty, missing evidence, and next useful crawl frontier
- slop-detector path classifies AI failure modes separately from truth labels
- every pathway writes calibrated scores and attribution fields that a critic can inspect

Fail:

- one generative model self-reports all labels
- graph edges are prose-only and cannot be replayed
- slop, truth, intent, and retrieval quality collapse into one scalar

### H10 — The Machine speaks packets to other AI

Claim: the Machine should communicate through compact, typed packets instead of prose.

Pass:

- each cycle emits a `MachinePacket` with intent features, evidence refs, bias planes, model state refs,
  and next command candidates
- packets are lossless enough for an AI worker to continue without reading human-facing prose
- human review is rendered from packets, not the other way around

Fail:

- AI workers must parse narrative output to continue
- packets omit evidence refs or chain head
- human copy becomes the source of truth

### H11 — AI-slop learning is measured on failure chains

Claim: the Machine can learn how AI slop happens by tracking the chain from human desire to AI output.

Pass:

- learning records track `said`, `meant`, `assumed`, `omitted`, `overclaimed`, `unsupported`,
  `corrected_by`, and `outcome`
- held-out eval includes slop-chain recall, false-positive rate, calibration, and contradiction recall
- labels distinguish user correction, critic correction, and evidence correction
- improvements are accepted only when helpfulness does not trade away evidence discipline

Fail:

- slop labels are only "good/bad"
- model rewards confident prose without source support
- user corrections are mixed with public corpora without provenance

### H12 — Steering becomes an editable operator profile

Claim: the way the Director steers and specs is high-value context that should become a compact,
machine-readable prior for future AI workers.

Pass:

- deploy writes `operator-profile.json`
- profile records `research_only`, `one_command_replaces_many`, `build_on_existing_work`,
  `experiment_slightly`, and `machine_native_first`
- profile distinguishes local-device consent from remote/export permission
- AI worker hints are derived guidance, not hidden policy

Fail:

- future workers must infer the user's operating style from long prose
- one-command CLI orchestration is treated as just another crawler command
- local-device consent silently implies remote export

### H13 — Non-ML execution composes existing verbs

Claim: the next CLI should replace the user's repeated manual research commands by orchestrating the
existing lgwks surfaces, not by recreating a new crawler.

Pass:

- `project deploy --execute` writes `execution-events.jsonl`
- memory scope/context is initialized and linked into the deploy directory
- public/open-license search writes `source-records.jsonl`
- deterministic folder embedding, when a folder is provided, writes `vector-vault.json`
- execution is bounded by `--source-limit`, `--embed-cycles`, `--max-files`, and typed leases
- authenticated crawling is explicitly skipped until the final hacker review gate

Fail:

- live execution is an unbounded crawl
- implementation bypasses existing `memory`, `public`, or `embed` modules
- auth/session crawling is silently enabled before the final review

### H14 — Worker fanout is capped and mapped internally

Claim: the CLI should fan out research work without spawning an unbounded swarm or requiring extra
API keys for mapper work.

Pass:

- `--max-workers` is hard-capped at 4
- deploy writes `worker-map.json`
- worker map has `max_concurrent_workers:4`
- all first-slice mapper slots use internal/deterministic mapper policies by default
- review reports active worker slots and max concurrent workers

Fail:

- more than four workers can be active at once
- worker mapping depends on external API keys by default
- logical research roles are invisible to future AI workers

### H15 — Everything is embedded immediately and locally

Claim: every artifact becomes searchable Machine memory as soon as it is produced.

Pass:

- deploy writes `artifact-embeddings.jsonl`
- transcript/prompt input gets an individual local embedding record
- cycle, lease, token, critic, packet, learning, lineage, graph, source, execution, model, worker,
  operator, vector, and DAG artifacts are embedded individually
- embeddings use deterministic local feature hashing in the first slice
- embedding records store hashes and vectors, not remote-provider IDs or API-keyed side effects

Fail:

- only final summaries are embedded
- learning/training material is skipped
- embedding requires a keyed external provider in the default path

## 4. Required Schemas

### 4.1 Cycle Record

```json
{
  "schema": "lgwks-cycle/1",
  "project": "salesforce",
  "seq": 1,
  "prev": "00...",
  "hash": "hmac",
  "intent": "map Salesforce...",
  "query_form": "disproof",
  "query": "Salesforce AI OS limitations failures...",
  "token_budget": 8000,
  "estimated_tokens": 2200,
  "token_status": "ok",
  "evidence_attention": [
    {"source": "openalex", "id": "W...", "why": "mechanism", "score": 0.72}
  ],
  "bias_flags": [
    {"plane": "prompt_bias", "kind": "thesis_lock", "severity": "m"}
  ],
  "next_commands": [
    {"argv": ["lgwks", "public", "..."], "reason": "fill disproof gap", "budget": 10}
  ],
  "eval_result": {"status": "planned|observed|unsupported", "score": 0.0},
  "weight": {"retrieval": 0.35, "evidence_quality": 0.25},
  "rollback_ref": "champion-sha"
}
```

### 4.2 Worker Lease

```json
{
  "schema": "lgwks-worker-lease/1",
  "worker_id": "academic-001",
  "project": "salesforce",
  "input_chain_head": "hash",
  "budget": {"tokens": 8000, "commands": 8, "fetches": 25},
  "allowed_sources": ["openalex", "crossref"],
  "query_form": "neutral_academic",
  "postcondition": "claims have source handle or unsupported label"
}
```

### 4.3 Critic Record

```json
{
  "schema": "lgwks-critic/1",
  "cycle_hash": "hash",
  "claim_id": "claim-...",
  "label": "observed|inferred|estimate|unsupported",
  "bias": {
    "human_bias": [],
    "ai_bias": [],
    "prompt_bias": [],
    "cognitive_bias": []
  },
  "contradiction": {"found": false, "source": ""},
  "next_action": "deepen|stop|disprove|embed"
}
```

### 4.4 Model State

```json
{
  "schema": "lgwks-model-state/1",
  "champion": {"id": "champion-sha", "score": {"brier": 0.18, "contradiction_recall": 0.70}},
  "challenger": {"id": "challenger-sha", "score": null},
  "promotion_policy": {
    "brier_must_improve": true,
    "contradiction_recall_must_not_regress": true
  }
}
```

### 4.5 Model Lineage

```json
{
  "schema": "lgwks-model-lineage/1",
  "model_id": "intent-encoder-champion-sha",
  "role": "intent_encoder|embedder|reranker|gnn|slop_detector",
  "base_model": "oss-model-name",
  "upstream_url": "https://...",
  "upstream_license": "Apache-2.0|MIT|BSD-3-Clause|...",
  "upstream_sha256": "sha256",
  "training_data_refs": ["learning-ledger-sha"],
  "conversion": {
    "source_format": "safetensors|torchscript|onnx",
    "target_format": "coreml",
    "conversion_tool": "coremltools",
    "quantization": "fp16|int8|none",
    "coreml_hash": "sha256"
  },
  "adapter_hash": "sha256-or-null",
  "eval_ref": "heldout-eval-sha",
  "export_policy": "local_only"
}
```

### 4.6 Learning Record

```json
{
  "schema": "lgwks-learning-record/1",
  "project": "salesforce",
  "cycle_hash": "hash",
  "source_scope": "transcript|private_crawl|public_corpus|critic",
  "consent": "local_only|export_allowed|none",
  "redaction_status": "raw_vaulted|redacted|derived_only",
  "said": "hash-ref",
  "meant": {"intent_class": "research", "entities": ["Salesforce"], "gaps": []},
  "assumed": ["AI OS means agent runtime"],
  "omitted": ["pricing evidence"],
  "overclaimed": ["dominates market"],
  "unsupported": ["claim-id"],
  "corrected_by": "user|critic|evidence|none",
  "outcome": {"accepted": false, "reason": "unsupported"}
}
```

### 4.7 Machine Packet

```json
{
  "schema": "lgwks-machine-packet/1",
  "project": "salesforce",
  "chain_head": "cycle-hash",
  "packet_id": "sha256",
  "intent_features": {
    "class": "research",
    "specificity": 0.91,
    "said_meant_distance": 0.22
  },
  "evidence_refs": ["source-hash"],
  "bias_planes": ["human_bias", "ai_bias", "prompt_bias", "cognitive_bias"],
  "model_refs": {
    "intent_encoder": "model-lineage-sha",
    "gnn": "model-lineage-sha",
    "slop_detector": "model-lineage-sha"
  },
  "next_commands": [
    {"argv": ["lgwks", "public", "..."], "reason": "contradiction gap", "budget": 10}
  ]
}
```

### 4.8 Graph Learning Edge

```json
{
  "schema": "lgwks-graph-edge/1",
  "project": "salesforce",
  "src": {"kind": "intent|cycle|source|claim|correction", "id": "hash"},
  "dst": {"kind": "cycle|source|claim|contradiction|next_command", "id": "hash"},
  "edge_type": "refines|supports|contradicts|omits|overclaims|corrects|schedules",
  "weight": 0.72,
  "evidence_ref": "source-hash-or-null",
  "created_by": "deterministic|critic|gnn_challenger",
  "attribution": {"top_features": ["missing contradictor", "source tier"]}
}
```

### 4.9 Operator Profile

```json
{
  "schema": "lgwks-operator-profile/1",
  "project": "salesforce",
  "profile_id": "operator-sha",
  "device_consent": "local-device",
  "learning_mode": "local-only",
  "stance": {
    "research_only": true,
    "one_command_replaces_many": true,
    "act_as_user_research_operator": true,
    "privacy_boundary": "local device is user-owned; remote/export remains explicit",
    "build_on_existing_work": true,
    "experiment_slightly": true,
    "architecture_fidelity_over_feature_count": true,
    "machine_native_first": true
  },
  "ai_worker_hints": [
    "prefer existing lgwks verbs and AI-Research-SKILLs patterns before inventing new machinery"
  ],
  "experiment_lanes": [
    {"lane": "steering-profile", "risk": "low"},
    {"lane": "adapter fine-tune", "risk": "high"}
  ]
}
```

### 4.10 Execution Event

```json
{
  "schema": "lgwks-execution-event/1",
  "project": "salesforce",
  "step": "public_search",
  "status": "ok|skipped|error",
  "started_at": 0.0,
  "finished_at": 0.0,
  "inputs": {"query": "salesforce ai os"},
  "outputs": {"records": 8, "artifact": "source-records.jsonl"},
  "error": ""
}
```

### 4.11 Source Record

```json
{
  "schema": "lgwks-source-record/1",
  "project": "salesforce",
  "source_id": "sha256",
  "via": "openalex",
  "title": "paper title",
  "url": "https://...",
  "open_url": "https://...",
  "license": "cc-by|metadata:CC0",
  "basis": "open reuse basis from source provider",
  "content_status": "metadata_only",
  "hash": "sha256"
}
```

### 4.12 Worker Map

```json
{
  "schema": "lgwks-worker-map/1",
  "project": "salesforce",
  "max_concurrent_workers": 4,
  "requested_workers": 4,
  "active_slots": [
    {"slot": 1, "worker_id": "context-001", "mapper": "internal-context-mapper", "api_keys": "none"},
    {"slot": 2, "worker_id": "source-001", "mapper": "internal-public-source-mapper", "api_keys": "none-by-default"},
    {"slot": 3, "worker_id": "embed-001", "mapper": "internal-deterministic-embed-mapper", "api_keys": "none"},
    {"slot": 4, "worker_id": "critic-packet-001", "mapper": "internal-critic-packet-mapper", "api_keys": "none"}
  ],
  "api_key_policy": "prefer internal deterministic mappers; keyed external providers are optional later",
  "spawn_policy": "never run more than four worker slots at any given time"
}
```

### 4.13 Artifact Embedding

```json
{
  "schema": "lgwks-artifact-embedding/1",
  "project": "salesforce",
  "kind": "transcript|artifact_doc|artifact_record",
  "artifact": "learning-records.jsonl",
  "item_id": "sha256-or-row-id",
  "text_sha256": "sha256",
  "embedding_model": "deterministic-feature-hash-v1",
  "dimensions": 128,
  "local_only": true,
  "embedding": [0.0],
  "hash": "sha256"
}
```

## 5. Command Contract

### `lgwks project deploy`

```bash
lgwks project deploy <project> \
  --prompt <text> \
  --reasoning-cycles 5 \
  --embedding-rounds 400 \
  --max-workers 4 \
  --learning-mode local-only \
  --device-consent local-device \
  --model-spine oss-coreml \
  --folder . \
  --source-limit 5 \
  --embed-cycles 3 \
  --dry-run
```

Pass:

- returns JSON by default or with `--json`
- writes deploy directory under `store/project-deploy/<project-id>/`
- `--dry-run` creates DAG, leases, and planned cycle records only
- non-dry run executes only commands in the approved typed command set
- learning modes are `off|local-only|export-allowed`; default is `local-only`
- device consent modes are `research-only|local-device`; local-device permits local user-context
  inspection for research orchestration but never implies remote export
- `oss-coreml` spine requires model lineage records before any semantic model output is trusted
- `--execute` in this slice runs non-ML typed steps only: memory, public search, deterministic embed
- auth/private crawling remains skipped until the final hacker review gate
- `--max-workers` is request input only; active workers are hard-capped at 4
- `artifact-embeddings.jsonl` is always written, including dry-run

### `lgwks project review`

```bash
lgwks project review <project>
```

Pass:

- reports chain head
- reports cycle count
- reports token spend
- reports bias counts by plane
- reports unsupported claims
- reports rollback ref
- reports source count, execution status counts, vector vault status
- reports artifact embedding count and worker-slot cap

## 6. Identify -> Spec -> Deploy Sequence

### Identify

Input:

- one prompt
- optional site/folder
- budgets

Output:

- `plan.json`
- initial memory scope
- branch worker plan

Already partially built by `lgwks project plan`.

### Spec

Input:

- plan
- this spec

Output:

- deploy DAG
- schemas
- pass-condition checklist
- test fixtures

This document is the spec gate.

### Deploy

Implementation order:

1. `lgwks_cycle.py`: append/verify/review cycle ledger.
2. `lgwks_worker.py`: lease records and dry-run worker DAG.
3. `lgwks_project deploy --dry-run`: write deploy artifacts only.
4. `lgwks_project review`: read cycle/model/token/critic summaries.
5. token ledger.
6. critic schema and dry-run critic.
7. semantic embedding sidecar.
8. model lineage manifest and learning-record ledger.
9. MachinePacket emitter.
10. graph-edge ledger and dry-run GNN pathway.
11. operator profile emitter.
12. non-ML executor: memory + public source records + deterministic vector vault + execution events.
13. worker map: max four internal mapper slots, no API-keyed mapper by default.
14. immediate artifact embeddings for transcript, learning material, and every deploy artifact.
15. CLI polish: `--render` human review projected from JSON.
16. final hacker review gate for auth/private crawling.
17. challenger promotion/rollback.

Stop after step 4 for first review. Do not jump to full model training in the same slice.

Non-ML completion slice:

1. Keep `--dry-run` default-safe.
2. `--execute` runs only existing modules: `lgwks_memory`, `lgwks_public`, `lgwks_embed`.
3. Write execution records to `execution-events.jsonl`.
4. Write public/open-license metadata to `source-records.jsonl`.
5. Write vector vault summary to `vector-vault.json` when `--folder` is present.
6. Write `worker-map.json` with max 4 active mapper slots.
7. Write `artifact-embeddings.jsonl` for every deploy artifact and record.
8. Human CLI polish is render-only; JSON remains source of truth.
9. Auth/private crawling and all ML/model evolution remain deferred.

Second learning slice:

1. Train nothing by default; emit learning records from transcript/cycle fixtures.
2. Pin one OSS text encoder lineage and one deterministic fallback lineage.
3. Convert/evaluate a no-op or fixture adapter through the CoreML path.
4. Run held-out slop-chain eval from fixtures.
5. Promote only if champion/challenger gate passes; otherwise freeze and report rollback.

## 7. First Slice Acceptance

The first implementation slice is accepted only if:

- `lgwks project deploy ai-ml-layers --prompt ... --dry-run` creates:
  - `cycles.jsonl`
  - `leases.jsonl`
  - `token-ledger.jsonl`
  - `model_state.json`
  - `machine-packets.jsonl`
  - `learning-records.jsonl` with derived-only/local-only fixture data
  - `model-lineage.jsonl` with deterministic fallback lineage
  - `operator-profile.json`
  - `execution-events.jsonl`
  - `source-records.jsonl` when executed
  - `vector-vault.json` when executed with a folder
  - `worker-map.json`
  - `artifact-embeddings.jsonl`
- `lgwks project review ai-ml-layers` reports:
  - `chain_ok:true`
  - `cycles:5` by default
  - bias planes present
  - rollback ref present
  - learning export policy
  - model lineage count
  - one-command/operator stance
  - execution status counts
  - source count
  - vector vault status
  - artifact embedding count
  - max concurrent workers = 4
- tests cover:
  - tamper breaks cycle chain
  - default cycle count is 5
  - disproof form appears within 5 cycles
  - token budget is recorded
  - no unsupported claim can be marked observed without evidence
  - raw user text does not leave the vault/log boundary in learning records
  - MachinePacket is derivable without human prose
  - operator profile records build-on-existing-work and local-device consent separately from export
  - execute composes existing public/embed/memory functions
  - review render is projected from JSON review data
  - requested workers >4 are capped at 4
  - every produced deploy artifact has deterministic local embedding coverage

## 8. Non-Goals For First Slice

- no real 400-round execution
- no actual model fine-tuning
- no unmanaged crawling expansion
- no hidden auth behavior
- no dashboard polish beyond review JSON/text
- no remote training or operator-owned telemetry
- no unpinned model downloads
- no license-unverified base weights
- no authenticated crawling before final hacker review
- no more than 4 active workers
- no default keyed embedding mapper

## 9. Open Questions

1. Should `project deploy` default to `--dry-run` until the Director passes `--execute`?
2. Should semantic embedding provider be Ollama first or CoreML/ANE first?
3. Should worker leases be per source (`openalex`) or per role (`academic`)?
4. Should token estimates be heuristic at first or measured from actual model calls?
5. Which OSS model family should be the first pinned text encoder: BERT-class, ModernBERT-class,
   E5/BGE-class sentence encoder, or UniXcoder-class code/intent encoder?
6. Should the first GNN path be a temporal graph over cycle records or a static graph over
   intent/evidence/claim nodes?
7. Should user correction labels be explicitly prompted for, inferred from edits, or both?
