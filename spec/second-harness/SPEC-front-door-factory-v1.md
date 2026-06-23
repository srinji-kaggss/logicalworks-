# SPEC — Two-Door Factory (agent + human over one well) v1

Status: **draft v0.2 · 2026-06-22 · implementation spec for #255 phase 2 + #249/#250/#251**
Authority: child of `prd/PRD-01-capability-map.md`; enforces parent `PRD.md` INV-1 (two projections,
never merged), §4 (BERTs orchestrate, Opus reasons), §6 (non-generative inbound schema).
Audience: machine-first. Implement, verify, then delete the poisoning doors (§7).

## 0. First-principles ground (proven by reading the code 2026-06-22)
Across the six legacy entrypoints only THREE things ever happen:
- **MAP** intent→capability — only `lgwks_engine.run_engine` actually does it.
- **COMPOSE** ordered capability phases→verdict — implemented 3× inconsistently: `do` (import ✓),
  `wf-run` (subprocess shell-out ✗), `x` (brace-expand+approval).
- **WORK** the real capabilities (`lgwks_substrate.build_run`, `lgwks_review` bots,
  `lgwks_codebase.search`, `lgwks_refactor`, `run_auto`, `solve_git`) — these are fine.
The poison is four front doors each half-doing MAP/COMPOSE differently, with `route act` coupled INTO `do`.

## 1. The model (one well, two doors — like Claude Code: perceive → act, with oversight)
```
                 ┌────────────────── THE WELL (single source) ──────────────────┐
  AGENT door ───►│ MAP  lgwks_engine.run_engine  → WorldView (§3)               │
  (machine JSON) │ PLAN compile_plan(intent,worldview) → ActionPlan (§4)        │◄─── HUMAN door
                 │ RUN  compose(plan)  one phase-runner, direct import, guarded  │     (oversight)
                 │ WORK CAPABILITIES[name] → module.command   (§5 dispatch)      │
                 └───────────────────────────────────────────────────────────────┘
```
- ONE MAP (`run_engine`), ONE COMPOSER (the `do` phase-runner, kept; shell-out variant killed),
  ONE capability table. Two reader-tuned projections sit on top. INV-1: never merge them.

## 2. The two doors
### AGENT door — `lgwks agent <intent> [--act] [--yes] [--force] [--repo P]` (machine-first, pure JSON)
The single agentic entry. Default = **give the world view**; `--act` (or an unambiguous safe resolution)
= **trigger the workflow**. Non-generative (no model prose; insight-or-silence). Output `lgwks.agent.v1`.
- `lgwks agent "<intent>"`            → WorldView only (perceive). No side effects.
- `lgwks agent "<intent>" --act`      → WorldView + compile ActionPlan + run it through the composer.
This is "world view + trigger workflows" in one door. It is the only NL→action path.

### HUMAN door — `lgwks human` (oversight projection; cockpit v0 = #251, deferred behind this seam)
Interactive oversight over the SAME well, tuned for a human, NOT the agent's raw schema (INV-1).
Consolidates existing `human {tui,repl,login,initialize}`. Reads worldview/plan/verdict for steering +
approval. This spec wires the door + seam; the rich cockpit projection lands in #251.

## 3. WorldView (the agent's perceive payload = PRD §6 schema; non-generative)
```jsonc
{ "schema":"lgwks.agent.v1", "intent":"…",
  "worldview": { "attention":{…}, "retrieval":[…], "last_state":{…},
                 "insights":{ "scores":{"C":0,"G":0,"P":0}, "selections":[…],
                              "flags":[ "slop"|"sycophancy"|"intent-drift"|"unverified-claim" ] },
                 "pathways":[…], "risk":{"verdict":"allow"|"warn"|"block"} },
  "plan": <ActionPlan|null>, "executed":false, "result":<…|null> }
```

## 4. ActionPlan — the one type that absorbs do/x/wf-run
```jsonc
{ "kind":"single"|"workflow"|"batch",   // 1 capability · named phase pipeline · brace-expanded commands
  "intent_class":"<one cortex label>",   // #255 §C — 1:1 with the resolved canonical verb
  "effect_class":"read"|"network"|"write",
  "approval":"none"|"once"|"force",      // once = x's one-confirmation; force = destructive
  "steps":[ {"verb":"research","args":{…},"effect_class":"network"}, … ],
  "reason":"…" }
```
- `single` ← today's `_choose_action` branches.  `workflow` ← `do` composites + `wf-run` chains (run via
  `lgwks_workflows`, import-based). `batch` ← `x` brace-expansion (`_expand_braces`+`_classify`, no-shell argv).

## 5. Capability table (severs route→do; one registry)
`CAPABILITIES = { name: (callable, effect_class) }` called by **direct import**, never subprocess:
```
research→lgwks_research.research_command(network) · ingest→lgwks_substrate.build_run(network)
review/govern/cleanup/ship→lgwks_review.*(read) · codebase→lgwks_codebase.search(read)
solve→lgwks_solve.solve_git(read) · refactor→lgwks_refactor(write) · crawl→lgwks_crawl(network)
graph/repo/gate/state/verify/files→<module>.command
```

## 6. Security model (the unsloppy, fail-closed part — non-negotiable)
- **S1 No NL→write auto-exec.** `effect_class:"write"`/destructive NEVER runs from a bare intent.
  It compiles to a plan requiring `approval:"once"` (`--yes`) and destructive requires `--force`.
  Mirrors `x` today + Claude-Code tool approvals. Agent default for write = block + return the plan.
- **S2 AUP gate** runs before any `network`/`research`/`ingest` step (kept from `do`); deny → exit 3, no exec.
- **S3 Risk gate**: `worldview.risk.verdict=="block"` → no exec, return plan only.
- **S4 No shell composition.** Capabilities invoked by import; `batch` uses no-shell argv (shlex). The
  `wf-run` subprocess path is deleted, not ported.
- **S5 effect_class is worst-of-aggregated** across plan steps; the plan's class gates approval.
- **S6 Non-generative output.** No model-written prose in `lgwks.agent.v1`; scores/selections/facts only.
- **S7 Versioned + labeled.** One `intent_class` per resolved action (training-label integrity, #255 §C).

## 7. Delete (poison) — verbs, not engines
- `do` verb → phase-runner + `_run_*` helpers become the composer; composites = `workflow` plans / `review …`.
- `wf-run` verb → workflows triggered via the agent door; `lgwks_workflows` kept as import-based substrate.
- `x` verb → `batch` plan kind; `lgwks_multiply._expand_braces/_classify/_run_one` kept as substrate.
- `route {map,engine,act,refine}` → folded into the agent door internals; `route` verb retired.
Add 2-token deprecation shims (`_apply_deprecation_shim`) rewriting legacy callers → `agent`.

## 8. Tests / gates (claim=evidence; fail-closed)
- `tests/test_cli_contract.py`: lower verb budget by removed verbs (no-regrowth) + assert verb→intent_class 1:1.
- Golden per plan kind (single/workflow/batch) + each guard S1–S3 (write-blocked, AUP-deny, risk-block, dry-run).
- A capability-coverage test proving every deleted door's concept is still reachable through the agent door.

## 9. Sequence
spec(this) → implement agent door (well + WorldView + ActionPlan + composer + CAPABILITIES, security S1–S7)
→ wire human door seam → delete do/wf-run/x/route verbs + shims → lower/extend contract gate → hacker pass.
