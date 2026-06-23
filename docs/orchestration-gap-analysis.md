# Orchestration Gap Analysis — lgwks / logicalworks-

> Branch: `investigate/orchestration-gaps` (off `origin/main` @ `762a595`). Originally a read-only diagnosis (the "before").
> **The redesign (the "after") is `docs/membrane-engine-thesis.md`; the package is `engine/` (start at `engine/README.md`); retirement tracking is `engine/DEPRECATIONS.md`.** Collapse has begun: the engine facade is landed and `lgwks_workflow_aetherius` is deleted (suite green, 2210 passed) — see those docs for live status.
> Method: navmap (`docs/navmap/`) + ingestion semantic DB (`~/ingestion_results`) + **dogfooded lgwks verbs** (`doctor`, `agent`, `repo graph`) + 2 background web-research streams (durable-execution camp; multi-agent-handoff camp) + the AI-authored competitive bar at `~/Downloads/translation_harness_blueprint`.

---

## 0. TL;DR — the verdict

The orchestration is "messed" in a precise, structural way: **the repo holds at least five peer orchestrators that each independently sequence multi-phase work, plus the one loop they were supposed to collapse into.** They share no single control owner, no single run record, and no single capability registry. The surface was consolidated to 10 verbs (#218) and a "single agent front door," but **the front door does not route through the loop** — it runs phases inline and never enqueues to the daemon. So the *appearance* of one entrypoint sits on top of five divergent engines.

This is not a missing feature. lgwks already states the correct philosophy — LLM as a bounded proposal generator inside a deterministic harness (the same thesis as the competitive `translation_harness_blueprint`). **The gap is that lgwks fragmented its own philosophy across five engines instead of expressing it as one harness with one bounded orchestrator.** Best-in-class systems (Temporal, LangGraph, OpenAI/Google/Anthropic agent stacks, and the blueprint itself) all converge on *exactly one control owner per run* — the thing lgwks is missing.

---

## 1. The orchestration surface as-is

From the navmap "Harness / daemon / orchestration" section: **39 modules · 13,396 LOC.** The engines that each drive a multi-phase loop:

| module | self-described role | LOC | imported-by¹ | imports¹ | what it actually is |
|---|---|---|---|---|---|
| `lgwks_daemon` | "referee runtime" background loop | 1361 | 3 | 15 | **intended canonical loop** (work queue + worktrees) |
| `lgwks_agent` | "the single AGENT front door" | 396 | 1 | 6 | **intended canonical front door** (perceive→plan→compose) |
| `lgwks_workflows` | "unified AI workflow harness" | 1216 | 2 | 19 | peer composite; **wraps `lgwks_do`** + own research loop |
| `lgwks_do` | "unified orchestrator: code/research/govern/cleanup/ship" | 545 | 0 | 16 | peer composite (RETIRED as verb, still the composer lib) |
| `lgwks_research` | "autonomous deep-research loop" | 986 | 0 | 29 | peer loop (generate→crawl→reason→contrarian→save) |
| `lgwks_workflow_aetherius` | "the autonomous intelligence kernel" | 156 | 0 | 13 | peer loop (synthesis→dialectic→valuation→refine→ingest) |
| `lgwks_substrate_run` | "build/query/baseline orchestration" | 862 | 1 | 20 | the one engine the daemon actually calls |
| `lgwks_project` | "one-prompt project orchestrator front door" | 125 | 0 | 29 | re-export shim front door |
| `lgwks_dsl` | "workflow orchestration" DSL | 141 | 0 | 7 | a fourth way to express a workflow |

¹ Degrees computed from `lgwks repo graph --json` (513 files, 3153 edges). **Caveat / dogfood gap (G9):** these counts are *static top-level imports only* — the graph misses `import lgwks_do` done lazily *inside* functions (e.g. `lgwks_workflows._do_code_wrapper` at `lgwks_workflows.py:842`), so real coupling is worse than shown. The five 0-/low-importer engines are reachable only via the CLI dispatch table or lazy imports → they are **peer top-level entrypoints, not a hierarchy under one owner.** That is the structural signature of the mess.

The word "unified" appears on three different modules (`do`, `workflows`, plus "unified" research/crawl elsewhere) and "kernel"/"orchestrator"/"harness"/"runtime" are each claimed by multiple modules — the canonical-duplication smell from the operating contract (one canonical implementation, kill duplicates).

The **ingestion semantic DB** corroborates the historical shape (two `workflow_command` symbols — `lgwks_workflow_aetherius.py:143` and `lgwks_workflows.py:950`; `do_command` at `lgwks_do.py:480`; `FleetOrchestrator` at `lgwks_agent_os.py:123`), but it is a **stale snapshot** (indexed under an old `/scratch/logicalworks-` path, no `agent_command` symbol → it predates the #218 front door). Treated as corroboration only; the live worktree is authoritative.

---

## 2. Intended canonical vs reality

The design intent (per the #218 consolidation comments in `lgwks` and the daemon docstring): **daemon = the one loop; `agent` = the one front door; `WORK_REGISTRY` × session state = the "smart form" that guides the agent to the next capability.** The collapse of `do`/`wf-run`/`x` into `agent` is documented as done at the verb surface.

Reality, verified by reading and running the code:

- **The front door perceives but does not dispatch to the loop.** `lgwks_agent.act()` (`lgwks_agent.py:332`) calls `lgwks_daemon_store.next_steps([])` (line 341) *only to display* the smart-form menu, then runs `compose(plan, repo)` (line 370) **inline, in-process**. Work is never enqueued to the daemon work queue. The front door and the loop are two unconnected systems that happen to share a menu.
- **The loop executes far less than the registry advertises.** `WORK_REGISTRY` (`lgwks_daemon_store.py:98`) declares 6 work kinds (`research_run`, `ingest_file`, `index_run`, `worktree_open`, `worktree_close`, `workflow`, `custom`), but the daemon's `_route_work_item` (`lgwks_daemon.py:435`) only really handles `research_run` and `worktree_open/close`; `ingest_file`, `index_run`, `workflow`, `custom` fall through to a no-op `complete_item(result={"dispatched": True})` (line ~463). **The smart form offers the agent capabilities the loop cannot actually run.**

So the two halves of the intended canonical exist but are not wired together — matching the long-standing open note: "the shared form primitive is built, the two loops aren't yet routed through it."

---

## 3. Gaps (evidence-cited)

### G1 — Five peer orchestrators, no single control owner *(severity: critical)*
`lgwks_do`, `lgwks_workflows`, `lgwks_agent`, `lgwks_research`, `lgwks_workflow_aetherius` each own a multi-phase run loop and are reachable as independent top-level entrypoints. Best-in-class converges on one owner per run (Temporal: one Workflow Execution; LangGraph: one Pregel engine + one `thread_id`; OpenAI: one `Runner`; ADK: one root agent; the blueprint: one `orchestrator` agent). **Five owners racing for the same step is the explicitly named anti-pattern** ("don't nest managers" — AutoGen; "crews don't orchestrate each other" — CrewAI).

### G2 — Research orchestration duplicated ≥3× *(critical)*
`lgwks_research` (full autonomous round loop), `lgwks_do._do_research` (`lgwks_do.py:204`), and `lgwks_workflows._do_research_inline`/`_do_deep_research` (`lgwks_workflows.py:340`/`:508`) are three separate research orchestrations. `workflows`' research path does **not** delegate to `do`'s. Three slightly-different copies = three bugs waiting to diverge (operating contract: "a second, slightly-different copy IS the bug").

### G3 — `workflows` wraps `do` for 4 of 5 phases, forks on the 5th *(high)*
`lgwks_workflows._do_code/govern/cleanup/ship_wrapper` (`lgwks_workflows.py:841–858`) delegate to `lgwks_do._do_*`, but research is reimplemented (G2). This is the "wrapper-on-a-library" shape the contract forbids: a composite that re-wraps another composite, blurring the two clean delegation verbs (transfer-ownership vs borrow-a-bounded-answer) that every best-in-class stack keeps mutually exclusive.

### G4 — Front door not wired to the loop *(critical)*
`agent.act()` runs `compose()` inline and never enqueues to the daemon (`lgwks_agent.py:341,370`). Consequence: no durable run record for agent-initiated work, no crash-resume, no replay, no worktree isolation, no concurrency control — all of which the daemon already provides but only for `research_run`.

### G5 — Two capability registries *(high)*
Routing/execution reads `_cap_*` handlers + `CAPABILITIES` dict (`lgwks_agent.py:182–238`), while the smart form reads `WORK_REGISTRY` (`lgwks_daemon_store.py:98`). Two registries describing "what work exists," guaranteed to drift. Best-in-class declares capabilities **once** and both routes and dispatches from that single surface (OpenAI `@function_tool`; ADK auto-`FunctionTool`; graph edges as the dispatch table).

### G6 — Three divergent run records, no single authoritative history *(critical)*
`lgwks_workflows` → `~/.lgwks/workflow_checkpoints/*.checkpoint.json` (`lgwks_workflows.py:283`); `lgwks_research` → `runs/<id>/` hash-chained ledger (`lgwks_research.py:332`); `lgwks_daemon` → `DaemonEventStore` sqlite event log + queue (`lgwks_daemon_store.py:486`). Three persistence schemes ⇒ no single replayable source of truth. This is the one primitive every durable-execution system centralizes (Temporal Event History; LangGraph checkpointer keyed by `thread_id`) and the blueprint mandates ("append-only score ledger," one trace per output).

### G7 — No uniform human-in-the-loop / approval gate *(high)*
The risk/approval gate lives in `agent.act()` (S1/S3, `lgwks_agent.py:350–368`). `do`/`workflows`/`research`/`aetherius` compose phases without going through it. Best-in-class has one pause/resume primitive per run (Temporal signal/update; LangGraph `interrupt()`/`Command(resume=)`; ADK callbacks; OpenAI tool `needs_approval`). lgwks' gate is bypassable by entering through any of the other four engines.

### G8 — `--machine` contract not honored uniformly *(medium, dogfood)*
`lgwks --machine repo graph` printed **human text**, not JSON; the verb only emits JSON via its own `--json` flag. The global machine-output contract (declared at `lgwks:` argparse top) is silently ignored by at least this verb — a machine caller relying on `--machine` gets unparseable output.

### G9 — Repo-graph edge detection misses lazy imports *(medium, dogfood)*
`lgwks repo graph` counts static top-level imports only; function-level `import lgwks_do` (e.g. `lgwks_workflows.py:842`) is invisible, so the tool under-reports coupling and can mislabel an engine as "0 importers / orphan." The map used to reason about the mess under-counts the mess.

### G10 — Smart form over-declares vs the loop's real coverage *(high)*
See §2: `WORK_REGISTRY` advertises `ingest_file`/`index_run`/`workflow`/`custom` that `_route_work_item` no-ops. The form guides the agent toward dead capabilities.

### G11 — `agent` intent→capability routing is weak on real intents *(medium, dogfood)*
`lgwks agent "find duplicate orchestrators and show what is canonical"` returned uniform-0.6 generic selections (`repo audit/graph/handoff`), `decisiveness_d=0.0`, `confidence_P=0.0`, `grounding_status: unavailable`. The single front door's classifier is undecisive on a concrete code-understanding intent — it fell back to a generic menu rather than routing to `codebase`/`repo graph` with confidence. (It *did* compile a correct single `codebase` step in the plan, so the planner is better than the scorer; the scorer is the weak link.)

---

## 4. Competitive comparison — lgwks vs best-in-class

Primitives synthesized from the two research streams (Temporal · LangGraph · Ray; OpenAI Agents SDK · Google ADK/Vertex · Anthropic orchestrator-worker · AutoGen · CrewAI) and the blueprint.

| Primitive | Best-in-class standard | lgwks today | gap |
|---|---|---|---|
| **Control owner** | exactly one per run (Runner/root/lead/Team/Workflow/Pregel) | 5 peer engines | **G1** |
| **Run record / replay** | one authoritative log (Event History / checkpointer) | 3 divergent stores | **G6** |
| **Crash-resume** | from exact step | only `research_run` via daemon; agent path none | **G4** |
| **Dispatch surface** | declared once = routes + executes (registry/edges/queues) | 2 registries (`WORK_REGISTRY` vs `_cap_*`) | **G5** |
| **Front door → executor** | triage/root *transfers ownership* to the loop | front door runs inline, never enqueues | **G4** |
| **HITL / approval** | one pause/resume primitive | only on `agent.act`, bypassable | **G7** |
| **Concurrency/fan-out** | structured (ParallelAgent, `Send`, task queues, asyncio.gather) | daemon worktrees + ad-hoc per engine | partial |
| **Delegation verbs** | 2 mutually exclusive (handoff XOR agent-as-tool) | blurred (`workflows` wraps `do`) | **G3** |
| **Workflow=deterministic vs agent=dynamic** | per-node choice, not a fork | a *fork into separate modules* | **G1/G2** |
| **Observability** | time-travel/replay over one history | 3 partial traces | **G6** |

### The blueprint mirror (the sharpest finding)
`translation_harness_blueprint` is the same thesis as lgwks — "do not ask the model to be the whole system; treat it as a proposal generator inside a deterministic harness" — but it is expressed as **one** staged pipeline `S0_intake → S1_seg → S2_candidates → S3_evidence → S4_score → S5_select → S6_repair → S7_formal_gate → S8_release`, with:

- **One bounded orchestrator role** — `allowed: route, cache, audit, decide fallback`; **`forbidden: override formal gate`**. lgwks has five orchestrators and none has a written boundary.
- **One append-only score ledger** + one trace per output (`source→candidates→scores→selected→repair diff→verification status`). lgwks has three ledgers (**G6**).
- **Strict role separation** (translator/critic/repairer/formalizer/orchestrator, each with allowed/forbidden). lgwks' roles are smeared across overlapping modules.
- **One repair loop with margin-based early exit** (`I{margin high?} → repair failed spans only`). lgwks has multiple loops with independent stop conditions (`research` budget/dry; `aetherius` chambers; `workflows` checkpoints).

**lgwks already believes the right thing and has built every ingredient — it has simply not collapsed them into one harness.** The competitive bar is not a capability lgwks lacks; it is the *discipline of a single control owner* lgwks lost by growing five.

---

## 5. Prioritized remediation (the collapse)

The fix is consolidation, not new code — consistent with "kill duplicates, route every caller through the one canonical primitive."

1. **Wire the front door to the loop (closes G4, the keystone).** `agent.act(..., execute=True)` should **enqueue** a typed work item to `DaemonEventStore` and let the daemon worker execute, rather than calling `compose()` inline. The smart form already computes the next step from `WORK_REGISTRY`; make execution go through the *same* registry. This single change subordinates `compose()` to the loop and gives every agent-initiated run the daemon's durability/worktrees/replay for free.

2. **One capability registry (closes G5, G10).** Collapse `_cap_*`/`CAPABILITIES` and `WORK_REGISTRY` into a single declared surface that both *routes* (smart form) and *dispatches* (worker), then make `_route_work_item` cover every declared kind (or stop declaring kinds the loop can't run).

3. **One run record (closes G6).** Make `DaemonEventStore` the single authoritative history. Retire `workflows`' JSON checkpoints and fold `research`'s ledger into store events (keep the hash-chain as an event property, not a parallel file tree).

4. **Demote `do`/`workflows`/`aetherius`/`research` from loops to composer libraries (closes G1, G2, G3).** They become *plan builders* that emit work items for the one loop — exactly as the #218 comments already intend ("`lgwks_do` helpers = the composer library"). Delete the duplicate research path; keep one.

5. **One HITL gate (closes G7).** Move the S1/S3 risk/approval gate out of `agent.act` into the loop's enqueue/dispatch boundary so it applies to every run regardless of entry path. Mirror the blueprint's inviolable rule: the orchestrator is *forbidden to override the gate*.

6. **Tooling fixes (G8, G9, G11).** Honor `--machine` in `repo graph`; teach `repo graph` to detect function-level imports; strengthen the `agent` intent scorer (it under-routes concrete code intents while the planner gets them right — fix the scorer, not the planner).

**Sequence:** #1 is the keystone — once the front door enqueues, the other engines have an obvious home (composer libs feeding the one loop) and the three ledgers have an obvious target (the one store). Do #1 → #3 → #2 → #4, then #5, then the tooling cleanups.

---

### Appendix — evidence index
- Surface: `docs/navmap/README.md` "Harness / daemon / orchestration"; `lgwks` build_parser (#218 verb consolidation comments).
- Front door inline-exec: `lgwks_agent.py:332` (`act`), `:341` (`next_steps`), `:370` (`compose`).
- Registry: `lgwks_daemon_store.py:98` (`WORK_REGISTRY`), `:416` (`next_steps`); `lgwks_agent.py:182–238` (`_cap_*`, `CAPABILITIES`).
- Loop coverage: `lgwks_daemon.py:435` (`_route_work_item`), `:444` (only substrate), `:463` (no-op fall-through).
- Duplicate composites: `lgwks_do.py:181–428`; `lgwks_workflows.py:340,508,841–858`.
- Persistence: `lgwks_workflows.py:283`; `lgwks_research.py:332`; `lgwks_daemon_store.py:486,669,720`.
- Graph: `lgwks repo graph --json` (513 files / 3153 edges); adjacency table §1.
- Competitive sources: see the two research streams (Temporal/LangGraph/Ray docs; OpenAI/ADK/Anthropic/AutoGen/CrewAI docs) and `~/Downloads/translation_harness_blueprint/schemas/translation_harness_blueprint.json`.
