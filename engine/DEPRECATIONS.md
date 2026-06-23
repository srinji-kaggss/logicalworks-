# DEPRECATIONS — orchestrator collapse into the Membrane Engine

> Reversible manifest. Nothing here is deleted yet. Header banners + this file mark intent; deletion is approval-gated and happens only after the Membrane Engine reaches parity. See `docs/membrane-engine-thesis.md` §6 and `docs/orchestration-gap-analysis.md` §5.

| module | LOC | status | disposition | replaced-by |
|---|---|---|---|---|
| `lgwks_agent` | 396 | DEMOTE | front door: `act()` enqueues to the one loop (no inline `compose()`) | engine front door |
| `lgwks_daemon` + `lgwks_daemon_store` | ~2400 | PROMOTE | becomes the one loop; hosts membrane + ledger + work registry | engine core |
| `lgwks_do` | 545 | DEPRECATE | composer library only (leaf phase helpers → work items) | work-item templates |
| `lgwks_workflows` | 1216 | DEPRECATE | composer library; drop `do`-wrapping + own research path | work-item templates |
| `lgwks_research` | 986 | DEPRECATE | one research plan (work-item template), not a loop | research work item |
| `lgwks_workflow_aetherius` | 156 | ✅ **DELETED (proven green)** | one synthesis plan; chambers → membrane-gated work items | synthesis work item |

## Invariants that must hold before any deletion
1. Membrane engine passes the full suite with the front door **enqueuing** (gap-analysis G4 closed).
2. One run ledger is authoritative; the 3 divergent stores (workflows JSON / research ledger / daemon sqlite) are folded in (G6 closed).
3. One capability registry drives both the smart form and dispatch (G5 closed).
4. CLI verb surface preserved via deprecation shims (no user-facing break).

## Progress (2026-06-23, branch `investigate/orchestration-gaps`)
- **Landed:** `engine/engine.py` (the one loop facade) + `engine/membrane_sanitize.py` (membrane primitive).
- **Deleted:** `lgwks_workflow_aetherius` (3 wirings removed from `lgwks_workflows`). Full suite **2210 passed**; the 2 failures are pre-existing/flaky, not this change (proven by stashing the work and re-running on clean `main` — `test_graph_viz::test_home_quick_v_launches_viz` fails there too).
- **Correction to dispositions:** `lgwks_research` is **KEEP-CANONICAL** (`run_auto` is the one research impl others route to — not deleted); `lgwks_daemon` is **KEEP/PROMOTE** (it is the loop). Only aetherius was a whole-module delete; the rest are demote-to-composer (delete duplicate paths, keep canonical helpers).

### Remaining sequence — each step gated by the full suite before the next
1. **Research triplication** → route `lgwks_do._do_research` + `lgwks_workflows._do_research_inline`/`_do_deep_research` to canonical `lgwks_research.run_auto`; delete the duplicate bodies.
2. **`do`-wrapping** → `lgwks_workflows._do_*_wrapper` stop re-wrapping `lgwks_do`; both become composer helpers feeding work items.
3. **Front-door rewire** → `lgwks_agent.act(execute=True)` calls `engine.dispatch` (enqueue) instead of inline `compose()`.

Verified test command (CI `pytest.suite` lane, `scripts/ci/run.mjs`):
```bash
uv run --python 3.12 --with pytest --with cryptography --with pyyaml --with networkx python -m pytest tests/ axiom/tests/
```

## Reversal
`git revert` of the banner commit restores prior behavior; this manifest and `engine/` are additive.
