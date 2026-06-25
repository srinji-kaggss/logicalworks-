---
type: Archive
title: JEPA Scientific Approach — 2026-06-06
description: Status: active research doctrine for the lgwks JEPA path
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# JEPA Scientific Approach — 2026-06-06

Status: active research doctrine for the `lgwks` JEPA path

## Purpose

This document logs the scientific approach for the `lgwks` JEPA architecture.

The goal is not to claim "we built JEPA."

The goal is to prove or refute a tighter thesis:

```text
multi-view latent prediction + deterministic CLI orchestration
beats token-only prompting for messy human-to-machine work
```

This is the architecture thesis under test.

## Research posture

Use the strongest parts of the local AI research skill stack:

- `autoresearch`: two-loop rhythm
  - inner loop = controlled experiment slices
  - outer loop = synthesis, claim updates, and pivots
- `agent-native research artifact`
  - claims must be falsifiable
  - experiments must be declarative
  - evidence must be separated from interpretation
- `ml-training-recipes`
  - fixed budget comparisons
  - one change at a time
  - keep/discard discipline

Our claim is systems-first, not model-hype-first.

## Core thesis

### T1 — Language is a lossy ingress, not the ontology

Human words are overloaded, underspecified, socially loaded, and unstable across contexts.

Claim:

```text
A machine that treats language as ingress and compiles it into typed multi-view artifacts
will outperform a machine that treats raw chat as the system of record.
```

Why this matters:

- words carry hidden assumptions
- the same idea can appear as prose, repo state, citations, commands, and outcomes
- token prediction alone overfits phrasing

### T2 — JEPA belongs above token prediction, not instead of it

Claim:

```text
The useful JEPA layer for lgwks is a world-model layer that aligns multiple views of the
same underlying object, while the deterministic CLI remains the executor and truth boundary.
```

Why this matters:

- we do not want another chat wrapper
- we want a latent alignment layer that survives paraphrase, slop, and partial context
- the CLI should remain the explainable compiler between latent state and machine action

### T3 — Deterministic structure is the great equalizer

Claim:

```text
Deterministic packaging, tranching, graph grounding, and replayable artifacts reduce the gap
between beginner humans, expert humans, weak agents, and strong agents.
```

Why this matters:

- it saves tokens
- it reduces dependency on prompt skill
- it preserves inspectability when the model is wrong

## Main research hypotheses

### H1 — Multi-view packages improve intent reconstruction

Statement:

```text
When the same problem is presented through multiple views, a JEPA-style package layer produces
better downstream retrieval and next-step selection than a single raw text prompt.
```

Null:

```text
Multi-view packaging does not improve retrieval or next-step selection over a strong single-prompt baseline.
```

Pass indicators:

- higher top-k relevant file recall
- better next-command accuracy
- lower contradiction omission rate
- lower token usage to reach the same useful state

Falsifier:

- no measurable improvement over control
- or gains vanish once prompt length is matched fairly

### H2 — Latent alignment beats wording sensitivity

Statement:

```text
A package-level latent predictor trained across multiple views is less sensitive to wording drift
than a token-only or lexical-only routing baseline.
```

Controls:

- deterministic lexical baseline
- deterministic + semantic embedding baseline
- BERT/ModernBERT router without JEPA loss

Pass indicators:

- stable routing under paraphrase
- stable routing under slop/noise injection
- stable routing across human vs machine phrasing

Falsifier:

- routing quality collapses under paraphrase at the same rate as baseline

### H3 — Temporal package transitions are learnable

Statement:

```text
The sequence
jepa package -> portal -> command -> outcome -> contradiction/update
contains enough signal for a temporal GNN or graph learner to improve next-action prediction.
```

Why this matters:

- this is the "AI needs to understand next outcome better" thesis
- not just next token, but next useful machine transition

Pass indicators:

- improved next-action ranking against heuristic scheduler
- improved contradiction recall
- better abstention when evidence is weak

Falsifier:

- graph learner does not beat simple heuristic or BERT-only ranking

### H4 — Humanized output can stay faithful if compiled from the same source package

Statement:

```text
Human-readable outputs can be safer and less slop-prone when they are a projection of the same
canonical machine package rather than a separate freeform synthesis path.
```

Pass indicators:

- human summary preserves same repo bindings and claims as machine packet
- no unsupported claims appear only in human projection
- lower divergence between human and machine outputs

Falsifier:

- human projection routinely introduces claims absent from the machine package

### H5 — Deterministic CLI control lowers total compute burden

Statement:

```text
Treating JEPA as a separate compute task above a deterministic CLI reduces total model work by
shifting grounding, replay, and verification into stable binaries and artifacts.
```

Pass indicators:

- fewer repeated repo scans
- lower prompt/context size
- fewer corrective agent turns before useful action

Falsifier:

- package/orchestration overhead costs more than it saves

## Architectural thesis points to prove

These are the thesis-level points the architecture is definitely trying to prove.

### P1 — Chat is the wrong storage format

Raw chat is a debugging format for humans, not a durable systems format for machines.

### P2 — The missing layer is not "more agent", it is "better latent object"

The system should operate on:

- views
- anchors
- claims
- contradictions
- bindings
- outcomes

not just prompts and completions.

### P3 — JEPA should bind views, not issue commands

JEPA predicts shared structure and likely next latent state.

The CLI decides:

- what command can run
- what repo state exists
- what evidence promotes a relation

### P4 — Repo alignment is not a retrieval trick, it is a truth anchor

Without the repo/code/command boundary, the latent model drifts into elegant nonsense.

### P5 — World-modeling must be typed before it is trained

If we cannot define the package, the event ledger, and the outcome graph, the model will learn on mush.

### P6 — Human and AI outputs should be projections, not separate pipelines

One canonical artifact, many views.

## Experimental controls

The first control ladder should be:

### C0 — Deterministic only

- `capture`
- `portal`
- no trained router
- no JEPA predictor

### C1 — Semantic router only

- BERT/ModernBERT membrane
- no JEPA loss
- no temporal graph learner

### T1 — Package-level JEPA predictor

- latent alignment across views
- predicts next useful tranche / binding / route

### T2 — JEPA predictor + temporal GNN

- learns package transitions and outcome structure

## Measurement doctrine

Measure system outcomes, not just model loss.

Primary metrics:

- top-k file recall
- next-command accuracy
- abstention calibration
- contradiction recall
- token cost to useful portal
- time to useful action
- human/AI projection divergence

Secondary metrics:

- package build cost
- number of repeated repo reads
- number of unsupported promoted claims

## Inner-loop plan

Short-loop experiments should change one thing at a time:

1. baseline deterministic package
2. add semantic router
3. add multi-view alignment objective
4. add temporal graph learner
5. compare under fixed time budget and fixed task set

## Outer-loop questions

Every synthesis pass should ask:

1. Did latent packaging improve machine action, or only summaries?
2. Did JEPA help under paraphrase/slop, or only on clean curated inputs?
3. Did the graph learner improve actual next outcomes?
4. Where did deterministic structure still outperform learned components?
5. Which parts of the system should remain permanently non-neural?

## Current honest status

As of 2026-06-06:

- canonical package runtime exists
- machine/human dual projections exist
- repo-grounded portal exists
- ML health surface exists
- trained JEPA predictor does not exist yet
- promoted BERT/CoreML router does not exist yet
- temporal GNN learner does not exist yet

Therefore:

```text
we are not proving the full thesis yet
we are building the correct substrate to test it
```

## Immediate next hypotheses to operationalize

If only three hypotheses are advanced first, they should be:

1. `H1 multi-view packages improve intent reconstruction`
2. `H2 latent alignment beats wording sensitivity`
3. `H5 deterministic CLI control lowers total compute burden`

Why these three:

- they are closest to the current code
- they are measurable with local experiments
- they determine whether full JEPA training is worth the added complexity
