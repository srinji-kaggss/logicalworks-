---
type: Index
title: Market Research Index
description: Navigable index for market-research artifacts and linked GitHub tracking issues.
tags: [market-research, index, github-issues]
timestamp: 2026-06-25T00:00:00-04:00
status: active
---

# Market Research Index

This folder stores durable market-research artifacts for Logical Works. Entries should be self-contained enough for future coding agents to consume without chat context.

## Active entries

| date | artifact | linked issue | purpose |
|---|---|---|---|
| 2026-06-25 | [OpenAI Jalapeño Inference Chip](./2026-06-25-openai-jalapeno-inference-chip.md) | [#341](https://github.com/srinji-kaggss/logicalworks-/issues/341) | Market and code-impact note for inference hardware, agent runtime selection, and existing Logical Works model/daemon seams. |

## Entry contract

Every market-research entry should include:

1. external event summary,
2. source-grounded facts,
3. unknowns / do-not-overclaim section,
4. impact on Logical Works architecture,
5. impact on agents,
6. existing-code impact map,
7. follow-up issue candidates.

## Agent instruction

Do not treat this folder as generic notes. Treat it as a compact market-signal ledger feeding repo architecture decisions.

When adding a new entry:

- create or link a GitHub issue,
- include source URLs inside the entry,
- identify exact code seams likely to change,
- define what future agents must not accidentally fork or hardcode.
