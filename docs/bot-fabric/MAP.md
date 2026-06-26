---
type: Reference
title: Bot Fabric Map
description: Replace repeated LLM scoping work with:
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:24:49-04:00
---

# Bot Fabric Map

## North star

Replace repeated LLM scoping work with:

```text
world db
-> deterministic bot passes
-> JEPA reduction/alignment
-> one final synthesizer
-> human + machine packages
```

## Core layers

### L1. World DB

Machine-first representation of how code, systems, protocols, services, and the internet fit together.

### L2. Bot fabric

Deterministic workers that crawl the repo, run stress tests, detect slop, and emit evidence.

### L3. JEPA layer

Aligns many views of the same object:

- bot findings
- repo graph
- prior packages
- external resources
- historical outcomes

This is where latent structure and compression happen.

### L4. Synthesizer

One optional higher-compute reasoning LLM pass:

- severity
- prioritization
- next actions
- explanation

This layer exists to reduce tokens and improve final judgment, not to rescue weak artifacts.

### L5. Projection surfaces

- machine packet
- human report
- visual radar
- drill-down index

## Compute doctrine

### Cheap compute

- graph extraction
- static analysis
- heuristics
- concurrency tests
- stress harnesses
- clustering
- ranking
- diffing

### Optional small model

- Apple-native / Foundation / CoreML-backed membrane first
- BERT/ModernBERT classifier membrane only if cheap enough and exportable
- routing / ranking / abstain

### Expensive model

- final synthesis only
- exactly one reasoning-heavy LLM layer

## OpenRouter stance

Use the remote reasoning model for the final synthesizer and occasional research assists.

Do not rely on it for:

- canonical storage
- core bot analysis
- world DB construction
- irreversible decisions

## Local model stance

Local models are acceptable for:

- Apple on-device foundation/runtime features already shipped with the platform
- CoreML / ANE-native membrane helpers
- short constrained JSON synthesis
- optional small coder/reviewer helpers only if the Apple-native path is insufficient

Local models are not required for:

- the bot fabric
- JEPA package construction

## Product outcome

The human should get:

- a Bloomberg-style dense radar
- anomaly cards
- a sitemap report
- drill-down links

The AI should get:

- a compact machine packet
- ranked evidence
- suggested next commands

The package must still be useful without the synthesizer:

- enough structure for a human to continue
- enough structure for a stronger AI to continue
- no dependency on black-box prose to understand what happened
