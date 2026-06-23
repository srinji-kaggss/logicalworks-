# `engine/` — the Membrane Engine

The single canonical orchestrator for lgwks: one deterministic symbolic loop that meets the LLM "blackbox" at a controlled **membrane**. Replaces the five prior peer orchestrators (see [`DEPRECATIONS.md`](./DEPRECATIONS.md)).

This README is the entrypoint for the `engine/` package. Read it first.

## Why this exists
The orchestration was fragmented across five independent loops with no single owner, three divergent run-records, two capability registries, and a front door that ran phases inline instead of routing through the loop. Full diagnosis: [`../docs/orchestration-gap-analysis.md`](../docs/orchestration-gap-analysis.md). The first-principles redesign — *an LLM's "understanding" and "safety" are linear directions in a continuous residual stream, so the harness must treat the model as a steerable field and gate every read/write of it* — is in [`../docs/membrane-engine-thesis.md`](../docs/membrane-engine-thesis.md).

## The one idea
> **"When compute becomes AI" = the moment a deterministic symbolic pipeline reads/writes the model's stochastic field.** That crossing is the membrane, and it is the only place that needs the full interpretability / observability / security stack.

Every crossing, in both directions, runs: **SANITIZE → MEASURE → GATE → ATTRIBUTE → QUARANTINE.**

## Files
| file | role | status |
|---|---|---|
| `engine.py` | the one loop: `perceive → sanitize → plan → gate → dispatch(enqueue)` | **landed**, smoke + suite green |
| `membrane_sanitize.py` | redesign-#1 primitive: strips hidden-payload codepoints (Unicode Tags / PUA / zero-width / bidi / zalgo), scores `payload_ratio`, fails closed | **landed**, dogfooded |
| `DEPRECATIONS.md` | reversible retirement manifest for the 5 prior orchestrators | aetherius **done**; rest sequenced |
| `__init__.py` | package marker | landed |

## Control flow (what `engine.run()` does)
```
intent ─▶ sanitize ─▶ (payload_ratio > 0.02? ─▶ BLOCK: quarantine)
                  └─▶ perceive (lgwks_agent.worldview)        ← canonical, delegated
                  └─▶ plan     (lgwks_agent.compile_plan)     ← canonical, delegated
                  └─▶ gate     (risk verdict == block? ─▶ BLOCK)
                  └─▶ dispatch ─▶ ENQUEUE work items to the daemon's one queue
                                  (verbs → WORK_KINDs; never inline execution)
```
- **Keystone (gap-analysis G4):** `dispatch()` **enqueues** through `lgwks_daemon_store` rather than running phases in-process. A surface (CLI/TUI/API) may read the ledger and emit intent (enqueue) — it must **never become a loop**.
- **Delegation, not duplication:** perceive/plan call the canonical `lgwks_agent` primitives; research routes to the canonical `lgwks_research.run_auto`; phase helpers come from `lgwks_do`. The engine owns the *loop*, not copies of the work.
- **Honest seams:** `measure()` exposes the live `payload_ratio` signal today; the MEASURE-stage probes (intent / harm / injection directions, the refusal Δ) and the PULSE wire-grammar binding are documented roadmap, stubbed behind stable seams — **not faked**.

## The daemon moat (why this beats a provider guardrail)
Anthropic's AUP gate is stateless, per-request, content-only. The daemon membrane is a **stateful, system-resident control plane**: it has the event ledger (memory), the filesystem, the process tree, worktrees, and the authority to block / pause / **branch a worktree** / **roll back** / route to the next legal move. A stateless classifier can only say "no"; the daemon can say "no, and here is the next legal move." Detail + the AUP field note (how Anthropic "knew on its own" — a learned classifier/probe, not reasoning): [`../docs/guardrail-aup-event-note.md`](../docs/guardrail-aup-event-note.md).

## Interfaces (one loop, many surfaces)
CLI, TUI, and API are clients over the one loop (opencode's client/server split). The **TUI already exists and is already correct** — PR #323 `lgwks-human/` reads the daemon event DB read-only/WAL and emits intent; its `flight/queue/runs/wire` screens map to the daemon's control/queue/ledger/event-wire, and its `next_steps` affordances are the PULSE affordance set. Do not rebuild it; point it at the engine.

## Protocol (PULSE) and threat data
The membrane's wire protocol is **PULSE** (`~/Downloads/pulse_okf_package`): modes = speech-acts (`ask/do/say/need/ok/fail/deny`), op-schemas = `WorkCapability`, the 15-point threat model = the membrane's non-negotiables. PULSE is better-*defined* than the pliny analog (GLOSSOPETRAE) but is asserted, not falsified — so it must absorb GLOSSOPETRAE's refutation-driven validation method and its covert-channel corpus as the membrane detector's test set. Offense modules of all studied repos are **threat-model inputs, not dependencies** — quarantined, never imported. Full comparison: thesis §10.

## Build & verify
Canonical test command (the CI `pytest.suite` lane, `scripts/ci/run.mjs`):
```bash
uv run --python 3.12 --with pytest --with cryptography --with pyyaml --with networkx \
  python -m pytest tests/ axiom/tests/
```
**Last verified (2026-06-23):** `2210 passed, 40 skipped`. The 2 reported failures are **not** from this work — `tests/test_graph_viz.py::test_home_quick_v_launches_viz` fails on clean `main` too (pre-existing bug in `lgwks_home._browser_entryway`; flagged), and the other was flaky (passed on rerun). Verified by stashing the engine work and re-running on clean main.

Membrane self-check (no model needed):
```bash
python3 engine/membrane_sanitize.py <file>   # exit 3 = payload-like, quarantined
```

## Status & roadmap
- **Done, proven green:** membrane sanitizer; engine facade (perceive/plan/dispatch-enqueue); first deletion (`lgwks_workflow_aetherius`).
- **Next (each per-step suite-gated):** (1) collapse research triplication → one `research.run_auto`; (2) fold `do`-wrapping in `workflows`; (3) rewire `lgwks_agent.act` → `engine.dispatch`. Then delete the freed duplicate paths.
- **Roadmap (research arc):** MEASURE-stage linear probes (intent/harm/injection); PULSE↔daemon binding; GLOSSOPETRAE corpus as detector tests.

## Repo constraints honored
The ~100 root `lgwks_*.py` are load-bearing (the CLI imports them by module name) — `engine/` is a new directory, not a repackaging of them. The daemon-core and a "security membrane" are already named in `docs/OPERATING-MODEL.md` and `docs/DAEMON-CORE-PLAN.md`; this engine aligns with that documented direction rather than competing with it.
