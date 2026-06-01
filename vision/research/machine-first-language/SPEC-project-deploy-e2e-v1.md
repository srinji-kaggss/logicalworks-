# SPEC-project-deploy-e2e-v1

Status: SPEC first. No implementation should start until these hypotheses and pass conditions are
accepted or edited.

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

Deploy may be `--dry-run` first. `--dry-run` must emit the same DAG and record schemas without
network fetches or embeddings.

## 2. Core Hypothesis

H0: A deterministic harness can make AI-assisted research more reliable than a single prompt by
forcing every cycle through:

```text
intent -> query_form -> evidence_attention -> bias_flags -> next_command -> eval_result -> weight_update
```

Success does **not** mean the Machine becomes AGI. Success means the Machine produces replayable,
auditable, bias-aware research cycles that improve retrieval/ranking data over time.

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

## 5. Command Contract

### `lgwks project deploy`

```bash
lgwks project deploy <project> \
  --prompt <text> \
  --reasoning-cycles 5 \
  --embedding-rounds 400 \
  --max-workers 4 \
  --dry-run
```

Pass:

- returns JSON by default or with `--json`
- writes deploy directory under `store/project-deploy/<project-id>/`
- `--dry-run` creates DAG, leases, and planned cycle records only
- non-dry run executes only commands in the approved typed command set

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
8. non-dry executor with approval gate.
9. challenger promotion/rollback.

Stop after step 4 for first review. Do not jump to full model training in the same slice.

## 7. First Slice Acceptance

The first implementation slice is accepted only if:

- `lgwks project deploy ai-ml-layers --prompt ... --dry-run` creates:
  - `cycles.jsonl`
  - `leases.jsonl`
  - `token-ledger.jsonl`
  - `model_state.json`
- `lgwks project review ai-ml-layers` reports:
  - `chain_ok:true`
  - `cycles:5` by default
  - bias planes present
  - rollback ref present
- tests cover:
  - tamper breaks cycle chain
  - default cycle count is 5
  - disproof form appears within 5 cycles
  - token budget is recorded
  - no unsupported claim can be marked observed without evidence

## 8. Non-Goals For First Slice

- no real 400-round execution
- no actual model fine-tuning
- no unmanaged crawling expansion
- no hidden auth behavior
- no dashboard polish beyond review JSON/text

## 9. Open Questions

1. Should `project deploy` default to `--dry-run` until the Director passes `--execute`?
2. Should semantic embedding provider be Ollama first or CoreML/ANE first?
3. Should worker leases be per source (`openalex`) or per role (`academic`)?
4. Should token estimates be heuristic at first or measured from actual model calls?

