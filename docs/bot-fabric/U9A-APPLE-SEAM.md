# U9A — Apple-Native Small Model Seam

Status: spec

## Purpose

Implement the inferred layer using Apple-native runtimes before standing up any
remote or general-purpose model stack. These are fixed-weight operators — deterministic
once trained — that implement mathematical operations on meaning.

L budget: 0. All operations are deterministic given weights.

## What these models do (math, not orchestration)

| Role | Operation | Math analogy |
|---|---|---|
| Intent classifier | project(fragment) → typed_intent | dimensionality reduction |
| Similarity encoder | distance(a, b) → float | metric space |
| Package router | route(package) → continuation_target | nearest-neighbour lookup |
| Abstain gate | confidence(classification) → pass/abstain | threshold function |

These are not mini-LLMs. They do not generate text. They project, measure, and route.

## Runtime selection order

```
1. Apple Foundation Models framework (on-device, system runtime)
   — use for: structured extraction, short constrained JSON, on-device text tasks
   — do not use for: large generation, multi-hop reasoning, arbitrary model hosting

2. CoreML / ANE exported encoder membrane
   — use for: BERT-class classifiers, similarity encoders, rerankers
   — requirement: model must be exportable to CoreML with fp16 or int8 quantization
   — coreml_hash must be recorded in model lineage before use

3. Small local coder/helper model
   — only if Apple-native path cannot cover the job
   — must be explicitly justified in the model lineage record
   — must produce short constrained JSON outputs only

4. Remote model (OpenRouter)
   — falls through to U9 synthesizer seam
   — not used for the inferred layer
```

## Model lineage contract

Every model used in this layer must have a lineage record:
```json
{
  "schema": "lgwks-model-lineage/1",
  "model_id": "...",
  "role": "intent_classifier | similarity_encoder | package_router | abstain_gate",
  "base_model": "...",
  "upstream_license": "...",
  "upstream_sha256": "...",
  "conversion": {
    "source_format": "safetensors | onnx | pytorch",
    "target_format": "coreml | mlpackage",
    "conversion_tool": "coremltools",
    "quantization": "fp16 | int8",
    "coreml_hash": "..."
  },
  "eval_ref": "...",
  "export_policy": "local_only"
}
```

No model may be used without a complete lineage record. Missing `coreml_hash` blocks use.

## Abstain contract

Every small model must implement an abstain gate. If confidence < threshold,
the model returns `abstain: true` and the pipeline falls through to the next layer.

Abstain is not failure. It is an honest signal that the model cannot reliably classify this input.
The reducer must handle abstain without crashing.

## Design constraints

1. no model may make network calls at inference time
2. all inference is local (on-device or local process)
3. coreml_hash must be verified before loading a model
4. abstain threshold is configurable per model role, not hardcoded
5. model outputs are typed JSON, never free text

## Likely file targets

- `lgwks_apple_seam.py` (extends existing `lgwks_foundation.py` / `lgwks_coreml.py`)
- `tests/test_apple_seam.py`

## Acceptance

1. Runtime selection follows the declared order (Foundation → CoreML → local → remote).
2. Model without complete lineage record cannot be loaded.
3. Abstain gate returns structured `abstain: true` response, not an exception.
4. All model outputs are typed JSON, validated against a schema before use.
5. No model makes network calls at inference time.
