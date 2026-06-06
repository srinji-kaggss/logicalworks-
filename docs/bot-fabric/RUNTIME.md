# Runtime And OpenRouter Policy

## End-to-end runtime

```text
repo + world db
-> bot plan
-> deterministic bot runs
-> evidence reduction
-> JEPA package
-> optional final reasoning synthesizer
-> human + machine projections
```

## OpenRouter policy

Current `lgwks` already treats OpenRouter as a generation seam and keeps embeddings/local substrate paths separate.

Repo grounding:

- [lgwks_openrouter.py](/Users/srinji/logicalworks-/lgwks_openrouter.py)
- [lgwks_openrouter_embed.py](/Users/srinji/logicalworks-/lgwks_openrouter_embed.py)
- [lgwks_tongue.py](/Users/srinji/logicalworks-/lgwks_tongue.py)

Current repo truth:

- generation goes cloud first through OpenRouter
- local Ollama and deterministic fallbacks remain
- remote embeddings are optional, not the default eye

## Apple-native local model policy

Use Apple’s on-device model/runtime work where possible before standing up a parallel local generation stack.

Repo grounding:

- [lgwks_foundation.py](/Users/srinji/logicalworks-/lgwks_foundation.py)
- [lgwks_coreml.py](/Users/srinji/logicalworks-/lgwks_coreml.py)
- [lgwks_model_hub.py](/Users/srinji/logicalworks-/lgwks_model_hub.py)
- [docs/ml-001-intent-classifier-sizing.md](/Users/srinji/logicalworks-/docs/ml-001-intent-classifier-sizing.md)

Current repo truth:

- Foundation-backed structured extraction already exists as a graceful seam
- CoreML classifier/runtime support already exists
- the repo already assumes Apple Silicon / ANE as a serious local inference path

Official Apple runtime reality:

- `Foundation Models` exposes Apple’s on-device model through one shared system runtime
- Apple also now exposes a Python SDK for that system model
- this is excellent for native structured generation, tool calling, and on-device text tasks
- it is not a general runtime for arbitrarily hosting your own swarm of separate tiny models

What it likely saves:

- duplicated application-side runtime work
- some integration, security, and deployment complexity
- native hardware/sandbox alignment

What it does not automatically give you:

- weight sharing across 120 arbitrary custom 1B models
- a free replacement for your custom CoreML/BERT membrane stack
- a guarantee that every model role in the fabric fits the Apple system model

Practical doctrine:

1. use Apple-native on-device capabilities first
2. export encoder-style membranes to CoreML/ANE where possible
3. add a small local coder/helper model only if the Apple path cannot cover the needed job

## What we can rely on

From current official OpenRouter docs:

- `openrouter/free` exists as a free router for zero-cost inference
- `:free` variants exist for specific models
- free availability and rate limits vary
- free models are suitable for experimentation and low-volume usage, not hard-reliability production

Sources:

- https://openrouter.ai/docs/guides/routing/routers/free-router
- https://openrouter.ai/docs/guides/routing/model-variants/free
- https://openrouter.ai/docs/api/reference/embeddings
- https://openrouter.ai/collections/free-models

## Practical recommendation

### Safe to rely on

- final synthesis for planning/review packages
- occasional remote package interpretation
- optional remote embeddings for selected substrate workflows

### Not safe to rely on

- critical-path deterministic analysis
- guaranteed availability
- stable free model identity
- all-day high-volume bot traffic

## Local model recommendation

If local generation is used at all, keep it small and native-first:

- Apple on-device model/runtime where available
- CoreML / ANE membrane and classifier paths
- short constrained JSON outputs only
- small coder/reviewer helper only as a secondary seam

Do not try to run a large remote-class synthesis model locally as the default path right now.

Do not assume a generic instruct model is the best first local choice for this repo. The better first choice is the platform-native Apple path already aligned with the hardware/security envelope.

## Preferred hierarchy

1. deterministic bot fabric
2. deterministic/package JEPA layer
3. Apple-native / CoreML membrane and helper seams
4. one optional reasoning-heavy final synthesizer

## Artifact strength rule

Before the final synthesizer runs, the package should already contain:

- ranked findings
- evidence links
- next-step candidates
- contradictions
- machine-readable structure

The synthesizer is allowed to:

- reduce token volume
- improve prioritization
- improve phrasing

The synthesizer is not allowed to be the only layer that makes the artifact understandable.
