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

### 🔄 Phase 5 — R-meter (token burn categorization) — IN PROGRESS
- Design: `lgwks_session` summary extended with `r_meter` field.
- Categories:
  - **Recovery**: undoing mistakes, fixing tests, reverting commits.
  - **Invention**: new features, novel abstractions, creative solutions.
  - **Noise**: redundant context, verbose summaries, repeated confirmations.
- Output in session summary JSON under `r_meter`.

### ⏳ Phase 6 — Schema registry (`lgwks schema ls`)
- List all known schemas with versions and descriptions.
- For next-agent discovery.

### ⏳ Phase 7 — Deterministic intent routing
- Replace heuristic classifier with tiny-bert model-driven routing.
- 4-model hierarchy: tiny-bert (edge/ANE), distilbert-base-uncased (STEM gate), neobert (research), codebert-base (code).

## Key Decisions
- AI-AI harness, not SaaS: built for AI successors, not human users. TUI deferred.
- Remove `_passthrough=True` for module-based verbs: direct function calls, no subprocess spawn.
- Leaf verbs in manifest/tests: `_collect_verbs()` returns `agent-os bootstrap`, `aup check`, etc.
- DoRun artifact: every `lgwks do` subcommand produces structured JSON with per-phase results.
- Context packs auto-emitted: `lgwks context --run-dir X --json` exposed in CLI surface.
- Spawn packet: `lgwks spawn --run-dir X --json` assembles the full handoff artifact.

## Critical Context
- **HEAD state**: `87979f6` (Phase 4) + uncommitted Phase 5 changes.
- `lgwks`: Main CLI router with all modules wired.
- `lgwks_do.py`: Unified orchestrator.
- `lgwks_context.py`: Graduated-resolution spawn context packs.
- `lgwks_spawn.py`: AI-AI handoff packet assembler.
- `lgwks_manifest.py`: `_VERB_META` with ~40 entries.
- `lgwks_home.py`: `_DOMAINS` + `_domain_for()` with prefix matching.
- 4-model hierarchy: tiny-bert (edge/ANE intent), distilbert-base-uncased (STEM gate), neobert (research engine), codebert-base (code engine).

## Next Steps
1. Finish Phase 5: R-meter in session summary.
2. Build Phase 6: `lgwks schema ls` schema registry.
3. Build Phase 7: tiny-bert deterministic intent router.
4. Build `lgwks spawn` packet assembler — one artifact combining verdict + AUP + context + intent trail for next AI.
5. Add R-meter to `lgwks_session` or `lgwks_repl` — categorize token burn as Recovery/Invention/Noise.
6. Build schema registry (`lgwks schema ls`) for next-agent discovery.

## Relevant Files
- `lgwks`: Main CLI router.
- `lgwks_do.py`: Unified orchestrator.
- `lgwks_context.py`: Graduated-resolution spawn context packs.
- `lgwks_foundation.py`: On-device entity extraction.
- `lgwks_keyvault.py`: Keychain secret resolver.
- `lgwks_model_hub.py`: Model catalog/convert/train.
- `lgwks_agent_os.py`: Fleet bootstrap/doctor/cards/agents/spawn/audit.
- `lgwks_aup.py`: AUP runtime gate.
- `lgwks_manifest.py`: `_VERB_META` with all leaf verb metadata.
- `lgwks_home.py`: `_DOMAINS` + `_domain_for()` with prefix matching.
- `tests/test_research_stack.py`: Updated expected verb list.
- `vision/research/research-network/GAP-ANALYSIS.md`: AI-AI harness gap analysis.
- `lgwks_spawn.py`: AI-AI handoff packet assembler.
- `tests/test_spawn.py`: 11 tests for spawn packet.

## Test Status
- 128 tests pass (117 regression + 11 new spawn).
- No regressions.
