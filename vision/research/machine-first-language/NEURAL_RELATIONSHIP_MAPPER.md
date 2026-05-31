# Neural Relationship Mapper

## Role

The relationship mapper is a separate neural system that proposes entity relationships for the
compiler. It is not the compiler and cannot make legal decisions.

```text
documents + current graph + source spans
-> frozen neural mapper
-> candidate nodes and paths
-> deterministic compiler validation
-> human accept/reject
-> offline training data
```

## Local Model Stack

Recommended local stack for the current machine:

| Function | Model |
|---|---|
| Embeddings/retrieval | `qwen3-embedding:8b` |
| Structured reasoning / graph extraction | `gpt-oss:20b` |
| Coding-agent experiments | `devstral:24b` |
| Larger coding/schema tests | `qwen3-coder:30b` |

Ollama is the serving layer, not the durable training substrate. If a future custom transformer is
trained, train from base model checkpoints and datasets, not from quantized Ollama runtime artifacts.

## Learning Boundary

The model can observe continuously, but it cannot learn continuously.

```text
observe always
learn offline
promote rarely
compile deterministically
```

Runtime uses frozen checkpoints only.

## Two-Lane Model Policy

| Lane | Behavior | Allowed Use |
|---|---|---|
| `stable` | frozen, evaluated, conservative | compiler suggestions |
| `frontier` | aggressive, experimental, high-recall | research, gap detection, adversarial probes |

The frontier lane may suggest strange relationships. That is useful. Its output is never accepted
without compiler and human validation.

## Training Examples

Accepted relation:

```json
{
  "input": {
    "source": "sales-process-doc",
    "context_nodes": ["lead", "account", "opportunity"]
  },
  "candidate": {
    "from": "opportunity",
    "rel": "belongs_to",
    "to": "account"
  },
  "decision": "accepted",
  "reason": "opportunities are account-scoped revenue objects",
  "compiler_result": "valid"
}
```

Rejected relation:

```json
{
  "input": {
    "source": "sales-process-doc",
    "context_nodes": ["lead", "forecast"]
  },
  "candidate": {
    "from": "lead",
    "rel": "owns",
    "to": "revenue_forecast"
  },
  "decision": "rejected",
  "reason": "forecast derives from opportunities, not raw leads",
  "compiler_result": "ambiguous_owner"
}
```

## Mapper Outputs

The mapper emits proposals:

```json
{
  "proposal_id": "prop-...",
  "model": "gpt-oss:20b",
  "checkpoint": "sha256-or-tag",
  "source_refs": ["doc-id#line"],
  "candidate": {
    "kind": "path",
    "from": "opportunity",
    "rel": "requires_approval_from",
    "to": "sales_manager"
  },
  "confidence": 0.78,
  "risk": "medium",
  "reason": "amount threshold language implies approval authority"
}
```

## Evaluation Set

Before a checkpoint can become `stable`, it must pass:

- relation precision on accepted/rejected historical examples;
- decomposition quality on >50-node requests;
- source-span faithfulness;
- false-positive rate for authority paths;
- hallucination rate on deliberately sparse docs;
- compile-success improvement without hiding gaps.

## What To Measure

| Metric | Why |
|---|---|
| `accepted_relation_precision` | Avoid polluting ontology. |
| `missing_required_node_rate` | Detect shallow understanding. |
| `unsafe_authority_false_positive` | Prevent dangerous grant suggestions. |
| `unanchored_path_rate` | Detect conceptual but unenforceable maps. |
| `decomposition_helpfulness` | Measure 50-node split quality. |
| `human_correction_reuse` | Ensure the model learns from feedback. |

## Governance

- Every model output is a proposal.
- Every proposal has provenance.
- Every accepted proposal becomes training data.
- Every rejected proposal becomes training data.
- No checkpoint is promoted without eval.
- No model can mutate compiler rules.
- No model can bypass compile errors.

## First Implementation

1. Use `qwen3-embedding:8b` for retrieval over docs and prior graph nodes.
2. Use `gpt-oss:20b` to generate JSON proposals from a strict schema.
3. Validate proposals with deterministic JSON Schema.
4. Store proposals in append-only JSONL.
5. Build a review UI for accept/reject.
6. Only then consider LoRA/fine-tuning.
