# Architecture — Logic OS Kernel

Status: active doctrine

## Core formula

```
f(x) = (math + NLP + math + framework)^LLM_coefficient
```

`LLM_coefficient` (L) is the primary audit metric.

```
L = invented_claims / total_claims_in_output
```

Low L  → system did the work; LLM executed a pre-solved problem. Auditable.
High L → LLM invented the answer. No trail. Auditor red flag.

**Implementation:** `lgwks_verify.LCalculator` computes L from a pipeline of `Verdict`
objects. `Verdict.evidence` is a list of structured `Evidence` dataclass instances,
each carrying `origin_type ∈ {grounded, inferred, invented}`. Legacy string evidence
is auto-coerced to `origin_type=invented` (conservative) so old gates cannot
accidentally claim zero-L without provenance. L is computable from the transform log.
Any output with no log is untrusted.

## Provenance contract (bytecode level)

Every claim in the system carries three tags:

```
provenance:   human_input | repo_state | crawl | bot_finding | small_model | llm
transform:    hash chain of every operation applied
origin_type:  grounded | inferred | invented
```

`grounded`  = deterministic source (bot, repo, crawl, human input)
`inferred`  = fixed-weight small model (reproducible, auditable once trained)
`invented`  = LLM generation (only this contributes to L)

L is computable from the transform log. Any output with no log is untrusted.

## Pipeline

```
human yap (throughout day)
  → ingress normalization
      origin_type: grounded (human_input)

→ bots fire automatically (git hook / file watch / seed ingest)
    math-only, deterministic, reckless — emit everything
    origin_type: grounded (bot_finding)
    L contribution: 0

→ small model operators (fixed-weight, deterministic once trained)
    BERT classifier  : project(fragment) → typed_object
    JEPA encoder     : distance(intent_A, intent_B) → float
    alignment layer  : align(view_1..n) → canonical_object
    origin_type: inferred
    L contribution: 0 (deterministic post-training)

→ reducer / arbiter
    dedup, cluster, rank, package
    math-only
    L contribution: 0

→ LLM reasoning layer
    input:  fully typed, fully grounded package
    job:    reason over pre-compiled context — judgment, implications, next actions
    NOT:    intent reconstruction, context recovery, or invention
    origin_type: invented (measured and logged)
    L contribution: measured

→ output
    machine packet  (bytecode context for next AI)
    human report    (anomaly cards, sitemap, drill-down)
    L score         (auditable coefficient)
```

## Where small models enhance math, not orchestrate

Small models implement mathematical operations on meaning:

| Model | Operation | Math analogy |
|---|---|---|
| BERT classifier | project(fragment) → typed_object | dimensionality reduction |
| JEPA encoder | distance(intent_A, intent_B) | metric space / similarity function |
| alignment layer | align(views) → canonical_object | centroid in latent space |
| small router | route(package) → continuation_target | nearest-neighbour lookup |

These are fixed-weight operators after training. Reproducible. Auditable.
They compress the dimensionality of what the LLM must handle — directly shrinking L.

## The research gap

No existing framework measures L system-wide across a multi-layer pipeline.

Closest existing work:
- RAGAS faithfulness score — measures LLM output faithfulness to context only (single layer)
- LIME/SHAP attribution — which input tokens caused which output tokens
- Program synthesis abstraction level — how much did human specify vs system infer
- AI teaming reliance literature — human vs AI contribution to joint decisions

The gap: a provenance-chain-aware L score across the full pipeline, not just the LLM step.
This is a research contribution, not just an engineering choice.

## USP

Math does the orchestration. Small models implement mathematical operations on meaning.
The LLM sees a fully typed, pre-solved problem and reasons over the residual.
The machine-first language being built is a type system for human intent
where every construct has a proof of provenance and L is a first-class observable.

## Unit L budgets

| Layer | Allowed L | Notes |
|---|---|---|
| Bots (U5/U6/U7/U8) | 0 | pure math, no model calls |
| Reducer (U3/U4) | 0 | pure math |
| BERT membrane | 0 post-training | deterministic given weights |
| JEPA alignment | 0 post-training | deterministic given weights |
| LLM synthesizer (U9) | measured, logged | only non-zero L layer |
| Seed ingress | 0 | normalization only |

## Trigger doctrine

Bots fire automatically. CLI is the manual override.
Triggers: git post-commit hook, file-watch, seed ingest event.
The human should never have to invoke the bot fabric manually during normal work.
