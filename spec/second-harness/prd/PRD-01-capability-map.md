# PRD-01 — Capability Map & Routing

Parent: [PRD.md](../PRD.md) §12 U1 · Status: **v0 shipped** (lgwks_map.py, commit 65a1a59) · this doc governs its growth.
Replaces: tool-discovery token waste; LangChain-class routing.

## Problem

An agent facing 106 lgwks modules, ~175 verbs, 1284 skills, 15 MCPs cannot afford to
*discover* capabilities generatively — discovery must be a sub-second deterministic lookup,
or every intent pays a token tax before work starts.

## Scope

- IN: `map(intent) → ranked capabilities`, deterministic-first; later semantic re-rank (PRD-05/06).
- IN (growth): fold skills + MCPs into the index — the daemon (PRD-08) snapshots
  `~/.claude` skill/MCP surfaces at SessionStart; lgwks verbs stay introspected live.
- IN: routing — `map` output feeds actor selection (`lgwks_actor`) and the inbound schema.
- OUT: deciding. The map ranks; Opus decides (INV-4). OUT: execution (that is actors).

## Builds on (verified)

`lgwks_map.py` (shipped) · `lgwks manifest` contract (175 verbs w/ intent text) ·
`lgwks_actor.py` registry (shipped) · candidates for growth: `lgwks_capabilities.py`,
`lgwks_intent_router.py`, `lgwks_intent_classifier.py` — surfaces to verify at unit start.

## Contract

Emits `lgwks.map.v1` (shipped shape: query, query_tokens, verb_count, matched, matches[], note).
v2 adds: `source` per match (`verb|skill|mcp|actor`), `index_snapshot_ts`. Consumers: PRD-04
(retrieval source), PRD-06 (coverage input), PRD-07 (inbound hook — live today).

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 01-a (shipped) | lexical map over lgwks verbs, <1s — DONE, evidence in commit 65a1a59 |
| 01-b eval corpus | ≥50 frozen intent→expected-capability pairs; lexical baseline scored (recall@5, MRR); committed before any ranking change (SCIENCE §3) |
| 01-c skills+MCP fold-in | map covers skills/MCPs from daemon snapshot; same schema; <1s p95 |
| 01-d semantic re-rank | BERT re-rank (PRD-05) beats lexical baseline on 01-b corpus, shown by paired comparison; deterministic tie-break; lexical remains the fallback when models absent |
| 01-e manifest cache | mtime-keyed cache of `lgwks manifest` subprocess (daemon calls this continuously) |

## Open questions → SCIENCE.md

Ranking-quality metric and corpus construction (§3); whether name-3x weighting survives the
eval; score calibration across query lengths.
