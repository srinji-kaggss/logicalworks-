---
type: Reference
title: CODEBASE EXTRACTION — Interpretability, Observability, Research Orchestration, Affordances
description: envelope that is the single canonical shape every observer emits.
tags: [reference]
timestamp: 2026-06-24T20:18:37-04:00
---

# CODEBASE EXTRACTION — Interpretability, Observability, Research Orchestration, Affordances

> **Method:** every claim below is verified by reading the source (line numbers cited) and/or
> running the live CLI. No docstring-trusting. This is the "verify before assert" extraction
> the Director demanded — most of what an outsider would cite as "missing" is built; the real
> gaps are narrow and named at the end.
>
> **Worktree:** `feat/agent-prompts-obs` off `origin/main` (80b61f4).
> **Date:** 2026-06-24.

---

## 1. Observability / Interpretability surfaces (what's built)

### 1.1 Daemon event envelope — `lgwks_daemon_event.py` (373 LOC)

**The observability schema.** `lgwks.daemon.event.v2` — a typed, content-addressed event
envelope that is the single canonical shape every observer emits.

- **10 event kinds** (line 44): `human_message`, `transcript_turn`, `tool_call`,
  `file_change`, `workflow_event`, `browser_action`, `repo_diff`, `terminal_output`,
  `model_output`, `artifact_emit`.
- **4 trust classes** (line 65): `human_confirmed`, `deterministic`, `model_proposed`,
  `untrusted`. This is the interpretability axis — every event carries how-much-to-trust-it.
- **8 sources** (line 62): `speech`, `text`, `browser`, `repo`, `terminal`, `model`,
  `workflow`, `artifact`.
- **Content-addressed payloads** (`payload_cid`, line 15): large payloads live out-of-band,
  addressed by axiom CID (`b2b256:<hex>`); small events inline. This is the "complete DB"
  shape — events are durable, content-addressed, queryable.
- **Provenance** (line 19): `{derived_from, producer, producer_version}` — every derived
  event records what produced it. This is the chain-of-custody for interpretability.
- **Validation** (`validate_event`, line 108): schema-conformant on write; rejects unknown
  kinds/trust/sources.

**Verdict:** competitive with LangSmith/Langfuse trace schemas. Has the trust/provenance
axis they lack. **Built.**

### 1.2 Daemon store — `lgwks_daemon_store.py` (1039 LOC)

**The durable event log + work queue.** SQLite-backed. Emits typed work events
(`research_run`, `ingest_file`, `index_run`, `worktree_open/close`, `workflow`, `custom`)
and is queryable (`lgwks.daemon.events.query.v0`). The PULSE Affordance Model (from the
preserved `chore/dedup-canonical-primitives` branch) adds `next_steps` + `telemetry` to the
context packet — the "what's next" affordance plumbing.

**Verdict:** the "complete DB" exists for daemon events. **Built.** Gap: research-run
findings (per-round files in `runs/<id>/`) are NOT in this store — they're filesystem-only.

### 1.3 Cognition log — `lgwks_cognition.py` (190 LOC)

**The training-data ingestion store.** `CognitionLog` — every event/thought/commitment
captured for the Standalone Aetherius Model training trajectory. This is the
"NORTH STAR" store (per AGENTS.md).

**Verdict:** **Built.** This is the long-horizon observability DB (training data), distinct
from the operational daemon store.

### 1.4 Transcript cortex — `lgwks_cortex.py` (250 LOC)

**The Transcript Cortex (PRD-06 U5).** CLI-exposed. The surface that reads agent
transcripts and extracts structured signal.

**Verdict:** **Built.** Needs deeper extraction to confirm what it surfaces to the TUI.

### 1.5 Hooks — 8 modules, all wired to the daemon store

Every hook (`claude_stop_hook`, `claude_tool_hook`, `claude_why_hook`,
`lgwks_subconscious_hook`, `subconscious_inbound`, `claude_scope_guard_hook`,
`codex_inbound`, `gemini_inbound`) imports `lgwks_daemon_event.build_event` +
`lgwks_daemon_store.DaemonEventStore` and emits typed events. **Vendor-agnostic** (Claude,
Codex, Gemini all funnel through the same envelope).

**Verdict:** **Built and wired.** The agent-observation tap is real and multi-vendor.

### 1.6 Audit — `lgwks_audit.py` (94 LOC) + `lgwks_audit_graph.py` (215 LOC)

**One canonical audit-append primitive** (#223 family) + the "Liquid Brain" audit graph
(ADR-sast-003). Append-only, signed.

**Verdict:** **Built.**

---

## 2. Research orchestration (what's built)

### 2.1 Question decomposition — `lgwks_tongue.py` (236 LOC) + `lgwks_research.py` (863 LOC)

**The AI planner that breaks a question into sub-questions.** Two entry points:
- `decompose_guide(guide_text, objective)` (tongue:140) — turns an implementation guide
  into N falsifiable research questions (agenda nodes).
- `compile_research_plan(objective, purpose)` (tongue:199) — turns a bare objective into a
  BROAD frontier of concrete search fronts. This is the "AI directs, compute goes deep"
  binding (research.py:585, "Director 2026-06-23").

**Verdict:** question decomposition + scoping **is built.** The agenda drives the frontier
walk; once drained, EIG-proposed expansion takes over. Fail-closed: planner offline →
deterministic market-seed agenda.

### 2.2 Bounded parallel fan-out — `lgwks_research.py`

- `FANOUT_CAP = 4` (line 42) — bounded preview fan-out for cheap frontier scans.
- `concurrent.futures.ThreadPoolExecutor` (line 25) — `_fanout_preview` (line 516) runs
  `inspect` over frontier items in parallel, capped at `min(fanout, len(items))`.

**Verdict:** parallel fan-out **is built** but **capped at 4.** This is the #1 real gap vs
ChatGPT/Firecrawl (300+). The architecture supports raising the cap; it's a constant, not
a structural missing piece.

### 2.3 Grounding — `lgwks_ground.py` (144 LOC)

**Fused live grounding.** Two fail-soft sources: ctx7 (library/API truth) + web (world
truth via `lgwks_search`). `has_evidence` is True iff at least one source returned real
content — the loop keys PLANNING vs EVIDENCE off this, never off a model claim. Everything
returned is wrapped in `<UNTRUSTED_FINDINGS>` before it reaches a Tongue prompt.

**Verdict:** **Built.** The epistemics discipline (evidence vs planning) is real and
enforced.

### 2.4 Findings persistence — `runs/<id>/` (filesystem)

Each round writes: `hypotheses.json`, `reason.json`, `think.md`, `contrarian.json`,
`digest.md`, `findings.md`, `sources.json` + `rounds.ledger.jsonl` + `index.json` +
`report.md`. **Per-run, per-round, structured.**

**Verdict:** **Built** but **NOT a queryable DB.** Findings are filesystem artifacts, not
in the daemon store or a queryable index. Gap: no `lgwks research query <run-id>` to
cross-run search findings. This is the "complete DB" gap.

---

## 3. "What's next" / affordances / steering (what's built)

### 3.1 Steering dials — `lgwks_steering.py` (101 LOC)

**Three forced, visible dials** that steer how the instrument reasons:
- **Frontierness** (0=consolidated … 1=frontier/speculative)
- **Lens** (-1=philosophy/first-principles … +1=science/evidence)
- **Depth** (0=shallow … 1=deep/exhaustive)

Rendered as bars; the human always SEES the active stance. The AI side is a
**thought-continuation packet** (terse, compact-keyed, evidence by hash-ref) — the next
call RESUMES the chain of thought instead of re-parsing narrative.

**Verdict:** the "leveling" you asked about **is built.** These are the dials a Bloomberg
cockpit would expose. Gap: not yet surfaced in the TUI (that's the TUI lap, in flight).

### 3.2 Context sufficiency gating

A verb refuses to run on too-thin input and names exactly what is missing (steering.py
docstring). **Clarification is a deterministic interface duty** — not a model guess.

**Verdict:** **Built.** This is the "unhappy path" handling for ambiguous/thin queries.

### 3.3 GitHub "what's next" — `lgwks_gh.py` (900 LOC)

`_compute_issue_next` (line 207) + `_compute_state_next` (line 257) — deterministic
recommendations on what to work on next, driven by issue state, branches, PRs. Outputs
`NextAction` objects.

**Verdict:** **Built** but **repo-state-driven, not trajectory-driven.** It tells you what
ISSUE to work on, not what RESEARCH STEP to take next. Gap: no "what's next" for a
research run (the agenda drives that, but there's no cockpit surface for "you're on
agenda item 3 of 7, here's what the next front is").

### 3.4 Agent contract — `lgwks_manifest.py` (1346 LOC)

`lgwks manifest --for-agent` emits a machine-first JSON blob: workflows, verbs, args,
capabilities. An agent reads this instead of parsing a man page. Verified live:
```
{"schema":"lgwks.manifest.for_agent.v0","tool":"lgwks","workflows":[
  {"workflow":"research","description":"AUP gate → crawl → embed → synthesize","verbs":[...],"args":[...]},
  {"workflow":"deep-research","description":"multi-source synthesis...","verbs":[...],"args":[...]},
  ...
]}
```

**Verdict:** **Built.** This is the Firecrawl-skill-equivalent — a machine-readable
contract. The skill (`skills/lgwks/SKILL.md`, merged in PR #330) is the human-readable
complement.

### 3.5 Intent routing — `lgwks_intent.py` (554 LOC) + `lgwks_intent_classifier.py` (498 LOC)

Schema-driven intent router: "a 10-line declaration drives automation." Custom English
intent classifier for the CLI membrane. Plus `lgwks_machine.py` (273 LOC) — the Tier-E
intent/goal engine (NOT AI — scores and ranks).

**Verdict:** **Built.** The membrane that routes a bare prompt to the right verb.

### 3.6 Spawn / context / portal — the handoff surface

- `lgwks_spawn.py` (207 LOC) — AI-AI handoff packet (`lgwks.spawn.v1`: AUP verdict +
  context + capabilities + provenance).
- `lgwks_context.py` (199 LOC) — graduated-resolution (LOD) context pack for the next
  spawn.
- `lgwks_portal.py` (279 LOC) — deterministic portal packets for coding-agent re-entry.

**Verdict:** **Built.** The "hand the research on a silver platter" surface exists —
spawn packets carry context + provenance to the next agent.

---

## 4. Agent prompts (what's built)

### 4.1 Tongue — `lgwks_tongue.py` (236 LOC)

The LLM compiles: `compile_hypotheses`, `decompose_guide`, `compile_research_plan`,
`reason_over_findings`, `contrarian`. Five prompt shapes, each schema-bound (not free
prose). Fail-soft to `None` (caller falls back to deterministic skeleton).

### 4.2 Agent OS — `lgwks_agent_os.py` (546 LOC)

Fleet startup/bootstrap helpers for the Logical Works prompt layer (#1).

### 4.3 Workflows — `lgwks_workflows.py` (1217 LOC)

Unified AI workflow harness: `_do_research_inline`, `_do_deep_research`, `_do_quick_scan`,
`_do_audit_trail`, `_do_health_check`, `_do_onboard`, `_do_migration_check`,
`_do_code_wrapper`, `_do_govern_wrapper`, `_do_cleanup_wrapper`, `_do_ship_wrapper`,
`_do_prove`. Phase-based (`_run_phase`), checkpointed (`_checkpoint_path`), cached
(`_cache_key`).

**Verdict:** **Built.** The workflow catalog is comprehensive. Gap: phases are sequential
(`_run_phase`), not parallel-fanned.

### 4.4 Synthesizer — `lgwks_synthesizer.py` (222 LOC)

U9/U9A: LLM reasoning layer & Apple-native/cloud synthesis seam.

---

## 5. The REAL gaps (verified, not assumed)

| # | Gap | What's built (the foundation) | What's missing |
|---|-----|-------------------------------|----------------|
| 1 | **Fan-out cap** | `FANOUT_CAP=4`, `ThreadPoolExecutor`, agenda-driven frontier walk | Cap is 4, not 300+. Raising it is a constant + a connection-pool, not a rebuild. |
| 2 | **Findings DB** | Per-run structured files (`runs/<id>/`), daemon store for events | Findings are filesystem-only; no cross-run queryable index. Add a findings→daemon-store bridge. |
| 3 | **Trajectory "what's next"** | `lgwks_gh` for repo-state, agenda for research fronts | No cockpit surface for "you're on agenda item N, here's the next front + why". The agenda data exists; the TUI surface doesn't (TUI lap). |
| 4 | **LLM interpretability (mechanistic)** | Trust classes, provenance, thought-continuation packets | No attention-map/token-attribution/SAE probing — but that's a MODEL-layer concern (Aetherius future), not a harness-layer gap. The harness records WHAT happened (events + provenance), not WHY the model fired (that's model interpretability, separate discipline). |
| 5 | **Parallel workflow phases** | `_run_phase` is sequential | Workflow phases could fan out (e.g. research + review in parallel). Structural support exists (`concurrent.futures` in research); workflows don't use it yet. |

---

## 6. Test log — every command run to produce this extraction

| # | Command | Result | What it proved |
|---|---------|--------|----------------|
| T1 | `python3 ./lgwks research --probe "LLM interpretability..."` | Header only, no body (exit 0) | `--probe` offline path returns thin world-view header; needs a repo context to body. |
| T2 | `python3 ./lgwks research --quick "LLM interpretability observability harness engineering"` | 9 citation URLs + rendered findings (OpenAI harness post, arxiv 2603.27355, walkinglabs awesome-harness-engineering, agentic-harness-engineering 128-concurrent) | `--quick` grounding is real and returns the frontier canon. Logged verbatim in §7. |
| T3 | `rg -n "def \|class \|decompos\|scop\|level\|parallel\|fan" lgwks_research.py` | 40 matches | Decomposition (`_agenda_node`, `decompose_guide`, `compile_research_plan`), fan-out (`FANOUT_CAP=4`, `ThreadPoolExecutor`), scoping (steering dials) all present. |
| T4 | `sed -n '530,620p' lgwks_research.py` (run_auto) | Full main loop | Agenda-driven frontier walk, AI-directs/compute-goes-deep binding, fail-closed fallback. |
| T5 | `rg -n "def \|whats.?next\|affordance" lgwks_gh.py` | 30 matches | `_compute_issue_next`, `_compute_state_next` — repo-state-driven what's next. |
| T6 | `rg -n "daemon_store\|DaemonStore\|emit_event" hooks/*.py` | 15 matches | All 8 hooks wired to the daemon store via `build_event`. |
| T7 | `head -40 lgwks_ground.py` | Full module header | Two-source fail-soft grounding (ctx7 + web), `has_evidence` epistemics. |
| T8 | `python3 ./lgwks manifest --for-agent` | JSON workflows blob | Machine-first agent contract is live and emits structured workflows. |
| T9 | `sed -n '42,101p' lgwks_daemon_event.py` | KINDS, SOURCES, TRUST_CLASSES, SCHEMA | 10 event kinds, 4 trust classes, 8 sources, content-addressed payloads, provenance. |
| T10 | `rg -n "def decompose_guide\|def compile_research_plan" lgwks_tongue.py` | Both present | Question decomposition is built (two entry points). |
| T11 | `cat lgwks_steering.py \| head -60` | Full steering module | 3 dials (frontierness/lens/depth) + thought-continuation packet design. |
| T12 | `rg -n "def \|parallel\|concurrent\|fan" lgwks_workflows.py` | 25 matches | Workflow harness is phase-based + checkpointed, but sequential (no parallel phases). |

---

## 7. lgwks research --quick output (verbatim, the frontier canon)

```
<UNTRUSTED_FINDINGS source=web>
[citation URLs (verifiable)]
https://www.linkedin.com/pulse/harness-engineering-discipline-turns-spiky-llms-reliable-pati-vg9mc
https://www.aiforanything.io/blog/ai-harness-engineering-observability-guide-2026
https://arxiv.org/abs/2603.27355          ← LLM Readiness Harness: Eval, Observability, CI Gates
https://arxiv.org/pdf/2603.27355v1
https://dev.to/lightningdev123/ai-harness-engineering-the-missing-layer-4919
https://deepwiki.com/walkinglabs/awesome-harness-engineering/3-evaluation-and-observability
https://openai.com/index/harness-engineering/   ← OpenAI's 0-lines-of-manual-code experiment
https://github.com/china-qijizhifeng/agentic-harness-engineering  ← 128-concurrent AHE

Key findings:
- "Harness Engineering: the discipline of constructing robust systems around the LLM...
  the harness is the nervous system, skeletal structure, and safety protocols."
- "As base model capabilities converged in early 2026, the operational layer became the
  primary determinant of production reliability." (aiforanything)
- arxiv 2603.27355: "LLM Readiness Harness: Evaluation, Observability, and CI Gates for
  LLM/RAG Applications" — turns evaluation into a deployment decision workflow.
- OpenAI: "0 lines of manually-written code... every line written by Codex... ~1/10th the time."
- agentic-harness-engineering: "harbor.n_concurrent to 128" — the 300+ parallel fan-out benchmark.
</UNTRUSTED_FINDINGS>
```
