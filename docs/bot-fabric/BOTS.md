---
type: Reference
title: Non-AI Bots
description: Bots are very well-coded deterministic workers.
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:24:49-04:00
---

# Non-AI Bots

## Thesis

Bots are very well-coded deterministic workers. They should produce evidence, not opinions.

## Bot lanes

### 1. Code Hacker

Grounded partly by the useful role/orchestrator split seen in the local `CyberStrikeAI` repo, but translated into `lgwks` machine language.

Responsibilities:

- exploitability heuristics
- auth boundary analysis
- dangerous shell/file/network usage
- secret exposure paths
- permission surface anomalies

## 2. AI slop math bots

Multiple narrow bots are preferred over one giant “quality” pass.

Sub-bots:

- graph anomaly bot
- naming/binning bot
- spec drift bot
- proof gap bot
- dead-abstraction bot
- contradiction bot

## 3. Codebase optimizer

Responsibilities:

- detect hot hubs
- identify god modules
- suggest split points
- highlight token/compute waste
- rank reusable static tool seams

## 4. Concurrent stress bot

Responsibilities:

- simulate concurrent workflows
- race/failure injection
- degraded dependency behavior
- recovery/replay realism

## Output contract

Every bot writes records shaped like:

```json
{
  "bot": "graph_anomaly",
  "target": "lgwks_substrate.py",
  "kind": "hub_risk",
  "severity": "medium",
  "confidence": 0.88,
  "evidence": [
    {"type": "pagerank", "value": 0.016829},
    {"type": "betweenness", "value": 0.074765}
  ],
  "links": {
    "file": "lgwks_substrate.py",
    "tests": ["tests/test_substrate.py"]
  }
}
```

## Bot runtime rules

1. No prose narratives
2. No hidden side effects
3. No freeform capability expansion
4. Outputs must be replayable
5. Outputs must link to drill-down artifacts
