# Daemon Absorption Log — how each killed orchestrator head returns as daemon work

> **SoT statement:** the **daemon (`lgwks_daemon`) is the single source of truth** for orchestration. The five peer orchestrators are retired. Their *heads* (autonomous entrypoints) are killed; their *leaf logic* is frozen as boilerplate and will be re-homed as daemon work-item handlers. This log is the canonical record of that re-homing. Machine-readable mirror: `engine/deprecated_heads.py`; enforced by `tests/test_deprecated_heads.py`.

## Why heads are flagged, not deleted (yet)
The composers back **14 live `ops workflow` CLI capabilities** and the daemon's `_route_work_item` currently executes only `research_run` + `worktree_open/close` (everything else hits a no-op fall-through — gap-analysis **G10**). Physically deleting the bodies now would strand those capabilities **and** cascade into the manifest⟷parser consistency gate (`tests/test_research_stack.py`) and the verb-budget gate (`tests/test_cli_contract.py`). So: **decapitate + flag + log now; delete after the daemon can execute the work.** This keeps the tool working and the suite green at every step (no gate weakening).

## Absorption map

| killed head | capabilities (frozen boilerplate) | absorbed into (daemon SoT) | status |
|---|---|---|---|
| `lgwks_workflow_aetherius` | synthesis/dialectic/valuation/refinement/ingestion chambers | work kind `workflow` → a synthesis handler | ✅ **deleted** (PR #324/#325) |
| `lgwks_workflows` | the 14 `ops workflow` verbs (research, deep-research, quick-scan, code, govern, cleanup, ship, prove, extract, compare, audit-trail, health-check, onboard, migration-check) | `research_run` (research/deep-research/quick-scan), `workflow` (code/govern/cleanup/ship/prove/compare), `index_run`/`ingest_file` (extract); leaf helpers become handlers | head_killed_boilerplate |
| `lgwks_do` | composite phases: `_do_code` / `_do_research` / `_do_govern` / `_do_cleanup` / `_do_ship`; leaf helpers `_run_review` / `_run_aup_check` / `_run_refactor` | work kind `workflow`; the `_run_*` leaf helpers become the canonical handlers the daemon calls | head_killed_boilerplate |
| `lgwks_route` | map / engine / route / refine (already RETIRED into the `agent` front door) | front door → `engine.dispatch` → daemon (no separate route head) | head_killed_boilerplate |

**Canonical survivors (NOT heads — these stay):**
- `lgwks_daemon` (+ `lgwks_daemon_store`) — the loop / SoT.
- `lgwks_research.run_auto` — the ONE research implementation; the daemon's `research_run` handler calls it (the three research copies in do/workflows collapse onto this).
- `lgwks_agent.worldview` / `compile_plan` — perceive+plan primitives the engine front door delegates to.

## The absorption sequence (executor-first, each full-suite-gated)
1. **Build the executor:** extend `daemon._route_work_item` to handle `workflow` / `index_run` / `ingest_file` by **calling the existing frozen leaf helpers** (`lgwks_do._run_review`, `_do_code`, …, `lgwks_research.run_auto`). Closes G10. Behavior preserved (same functions, reached via the loop).
2. **Reroute the heads' shims:** the 14 `ops workflow` verbs + `agent.act(execute=True)` enqueue via `engine.dispatch` instead of running inline.
3. **Delete the boilerplate:** once every capability is reached through the daemon, delete the dispatch tables / inline loops / `do`-wrappers / `lgwks_route`. Update the manifest + the parser/verb-budget gates in the same commit (directed behavior change, invariant logged here).
4. **Sweep orphans** (unused imports, dead helpers) in one final pass; full-suite gate.

Until step 3, the flagged modules remain importable boilerplate so the suite and CLI stay green. The flag (`_DEPRECATED_HEAD`) + this log are the durable record that they are dead heads, not living orchestrators.
