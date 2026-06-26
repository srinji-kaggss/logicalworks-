---
type: Archive
title: lgwks AI-AI Harness — Session Summary
description: Build AI-AI harness: wire all CLI stubs, enable deterministic composition, reduce token burn for AI successors.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# lgwks AI-AI Harness — Session Summary

## Goal
Build AI-AI harness: wire all CLI stubs, enable deterministic composition, reduce token burn for AI successors.

## Constraints & Preferences
- Human deprioritized: no TUI/HTML/SaaS; AI-facing CLI first.
- Deterministic layer preferred over LLM orchestration.
- All core verbs must have `--json` for machine-readable composition.
- No shell-outs between lgwks modules — direct function calls only.

## Progress

### ✅ Phase 1 — `agent-os` + `aup` wired into `lgwks` shell (`b38aef2`)
- `lgwks agent-os bootstrap` fleet creation.
- `lgwks aup check` / `lgwks aup audit` AUP runtime gate.
- `slop_math` S5 O(n²) → O(n) dead abstraction detection.
- `lgwks review` bot fabric with changed-files passthrough.
- 1,095/1,095 tests pass.

### ✅ Phase 2 — Unified orchestrator `lgwks do` (`9146cfd`)
- `lgwks do code` / `research` / `govern` / `cleanup` / `ship`.
- DoRun artifact (`lgwks.do.run.v1`) with per-phase results.
- Exit-code contract: 0/1/2/3/4.
- Context packs auto-emitted from `do` orchestrator.

### ✅ Phase 3 — Wire `context`, `foundation`, `keyvault`, `model-hub`, `run` (`6c4664a`)
- Graduate all five modules from standalone scripts to `lgwks` subcommands via `add_parser()`.
- Remove `_passthrough=True` for these modules; only `auth` + `akinator` remain separate scripts.
- `_VERB_META` expanded to ~40 leaf verbs.
- `_domain_for()` prefix matching for nested verbs.
- Tests updated to expect leaf verb names.

### ✅ Phase 4 — `lgwks spawn` AI-AI handoff packet (`87979f6`)
- New `lgwks_spawn.py`: assembles `spawn.json` from run directory.
- Bundles AUP verdict + DoRun artifact + context pack metadata + live capability manifest + provenance (git sha, hostname).
- Schema: `lgwks.spawn.v1`.
- 11 tests: schema, missing artifacts, context meta, capabilities, CLI JSON/summary, bad dir.

### ✅ Phase 5 — R-meter token burn categorization (`9aea771`)
- Added to `lgwks_session._summarize_activity()`: categorizes commits + shell commands.
- Categories: **Recovery** (fix, revert, test, debug), **Invention** (feat, add, implement, design), **Noise** (wip, merge, docs, stub).
- Structured JSON: `counts`, `percentages`, `dominant`, `total_weighted`.
- Narrative integration + TTY rendering with color-coded dominant.
- 7 tests: invention, recovery, noise, counts, narrative, empty, json.

### ✅ Phase 6 — Schema registry (`lgwks schema ls/show`) (`9de1766`)
- New `lgwks_schema.py`: scans codebase for schema declarations, builds registry.
- CLI: `lgwks schema ls --json --domain`; `lgwks schema show <name> --json`.
- Auto-discovers 20+ schemas from Python files + manual annotations.
- 8 tests: ls JSON, domain filter, show known/unknown, TTY output.

### ✅ Phase 7 — Deterministic intent router (`lgwks route`) (`9de1766`)
- New `lgwks_intent_router.py`: tiny-bert + heuristic fallback classifier.
- 9 verb categories: research, code, system, data, github, devops, multiply, meta, unknown.
- Fast heuristic: keyword-based with confidence scores (zero-latency).
- tiny-bert integration: loads from model hub, validates num_labels, graceful fallback.
- `route()` maps category → concrete verb + args + note.
- CLI: `lgwks route <text> --json --model {auto,heuristic,tiny-bert}`.
- 15 tests: classify all categories, route mapping, CLI JSON/TTY/empty, hash consistency.

## Key Decisions
- AI-AI harness, not SaaS: built for AI successors, not human users. TUI deferred.
- Remove `_passthrough=True` for module-based verbs: direct function calls, no subprocess spawn.
- Leaf verbs in manifest/tests: `_collect_verbs()` returns `agent-os bootstrap`, `aup check`, etc.
- DoRun artifact: every `lgwks do` subcommand produces structured JSON with per-phase results.
- Context packs auto-emitted: `lgwks context --run-dir X --json` exposed in CLI surface.
- Spawn packet: `lgwks spawn --run-dir X --json` assembles the full handoff artifact.

## Critical Context
- **HEAD state**: `9de1766` (all 7 phases complete).
- `lgwks`: Main CLI router with all modules wired (40+ leaf verbs).
- `lgwks_do.py`: Unified orchestrator with DoRun artifact.
- `lgwks_context.py`: Graduated-resolution spawn context packs.
- `lgwks_spawn.py`: AI-AI handoff packet assembler (lgwks.spawn.v1).
- `lgwks_schema.py`: Schema registry for next-agent discovery (lgwks.schema.registry.v0).
- `lgwks_intent_router.py`: Deterministic intent router (tiny-bert + heuristic).
- `lgwks_manifest.py`: `_VERB_META` with ~50 entries.
- `lgwks_home.py`: `_DOMAINS` + `_domain_for()` with prefix matching.
- 4-model hierarchy: tiny-bert (edge/ANE intent), distilbert-base-uncased (STEM gate), neobert (research engine), codebert-base (code engine).

## Next Steps
1. Fine-tune tiny-bert on actual lgwks intent data (currently heuristic-dominant).
2. Deploy neobert for research tasks (long-context understanding).
3. Deploy codebert-base for code review (AST-aware).
4. Build `lgwks monitor` for continuous run observation.
5. Build `lgwks replay` for deterministic session replay.
6. Cross-spawn A2A protocol: agent cards + capability exchange.

## Relevant Files
- `lgwks`: Main CLI router.
- `lgwks_do.py`: Unified orchestrator.
- `lgwks_context.py`: Graduated-resolution spawn context packs.
- `lgwks_foundation.py`: On-device entity extraction.
- `lgwks_keyvault.py`: Keychain secret resolver.
- `lgwks_model_hub.py`: Model catalog/convert/train.
- `lgwks_agent_os.py`: Fleet bootstrap/doctor/cards/agents/spawn/audit.
- `lgwks_aup.py`: AUP runtime gate.
- `lgwks_spawn.py`: AI-AI handoff packet assembler.
- `lgwks_schema.py`: Schema registry.
- `lgwks_intent_router.py`: Deterministic intent router.
- `lgwks_manifest.py`: `_VERB_META` with all leaf verb metadata.
- `lgwks_home.py`: `_DOMAINS` + `_domain_for()` with prefix matching.
- `lgwks_session.py`: Session boundary analyzer with R-meter.
- `tests/test_research_stack.py`: Updated expected verb list.
- `tests/test_spawn.py`: 11 tests for spawn packet.
- `tests/test_rmeter.py`: 7 tests for R-meter.
- `tests/test_schema.py`: 8 tests for schema registry.
- `tests/test_intent_router.py`: 15 tests for intent router.
- `vision/research/research-network/GAP-ANALYSIS.md`: AI-AI harness gap analysis.

## Test Status
- **1,136 tests pass** (1,006 regression + 130 new/updated).
- No regressions.
