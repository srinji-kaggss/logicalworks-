---
type: Plan
title: Pristine Codebase Program — Build Order (R3→R9), an executable playbook
description: A sequential, fork-resolved playbook for an executing agent to de-slop lgwks milestone by milestone — each leaf with intent, the one canonical primitive, pre-decided forks, acceptance criteria, the Keel gate, and human-checkpoints where the agent must stop and check in with Opus before anything goes upstream.
tags: [concepts, doctrine, pristine, slop, keel, build-order, playbook, checkpoints]
owning_issue: "345"
timestamp: 2026-06-25T00:00:00Z
---

# What this is

The [Pristine Codebase Program](pristine-codebase-program.md) names the rot; the
[escalation-robustness](escalation-robustness.md) doc was the first worked design (R1+R2,
shipped). **This doc is the rest, sequenced for execution.** It is written so a *cheaper
executing agent* can take it leaf by leaf without a human re-deriving context — the hard
thinking (which primitive is canonical, which forks are real, what order is safe) is
already done here. Where a fork genuinely needs the Director, it is marked
**🔶 DIRECTOR-GATED** and deferred to a checkpoint; the agent must **not** guess it.

> Operate as **SH+** (an AI senior dev out to beat a human senior): lower
> entropy/coupling/risk, raise the floor for the next agent, never chase perfect, never
> let a fix silently rot. Claim only what a command you ran demonstrates.

# How the executing agent works (read this first, every session)

1. **Read** `CLAUDE.md` (authority ladder + the load-bearing-root invariant — do NOT move
   `lgwks_*.py` into a package) and the program doc. Then this doc.
2. **The per-leaf loop** (the program method): reconstruct the intent → find/​complete the
   ONE canonical primitive → route every caller through it and **delete** the dup (never
   deprecate-in-place) → **gate it** so the dup cannot regrow → prove green.
3. **Separate refactor from behavior.** A pure routing/extraction leaf must not change
   behavior; assert parity (byte-identical IDs/vectors) where it could.
4. **Never weaken a gate to go green.** Fix the thing under test. Retargeting a stale test
   to canonical behavior is allowed ONLY when the invariant is preserved — and you must
   say so in the commit. (See `feedback`: no-gate-weakening.)
   - **No silent self-allow-listing.** A no-regrowth gate (R4.7/R5.4/R3.4/R6.4) protects you
     only if its allow-list cannot grow in the same breath as the straggler it should catch.
     Every allow-list/inventory addition MUST carry a tracking-issue reference and a one-line
     reason in the same commit; adding a straggler AND its own allow-list entry is the
     anti-pattern the gate exists to stop. If a fix tempts you to add an allow-list row,
     that is a 🔶 — surface it, don't self-pardon.
5. **One small commit per leaf**, on the milestone branch. Conventional message; end every
   commit body with:
   `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
6. **Do NOT push to origin/gdrive and do NOT open PRs.** Commit locally only. Pushing
   upstream happens at a checkpoint, by the Director with Opus. (See "Checkpoints".) This is
   not honor-system: install the repo's pre-push block before starting work —
   `git config --local --add hook... ` is not enough, so set a `pre-push` hook that exits 1
   with "Pristine Program: push is checkpoint-gated — see pristine-build-order.md" (a sample
   is in the Checkpoints section). The human removes it to push at a checkpoint. If you
   cannot install the hook, STOP and say so — do not proceed on the honor system.
7. **If you hit a 🔶 DIRECTOR-GATED fork, STOP** that leaf, do the full blast-radius
   analysis, and surface it at the next checkpoint. Do the un-gated leaves around it.

## Branching

Until PR #346 (R0–R2) merges to `main`, branch each milestone off the program tip
`feat/model-law-generated`; after it merges, branch off `main`. One branch per milestone:
`pristine/m<N>-<rot>` (e.g. `pristine/m1-model-catalog-gate`). Stack only if a milestone
truly depends on an unmerged earlier one; otherwise branch fresh so each can merge alone.

## The single definition of "green" (commands — claim only what these show)

The local Keel CI is the authority (not GitHub). Run the whole gate:

```
node scripts/ci/run.mjs            # all commit lanes; must end GO / exit 0
```

Or the individual lanes while iterating (all must pass):

```
uv run --python 3.12 --with pytest --with cryptography --with pyyaml --with networkx \
    python -m pytest tests/ axiom/tests/ -rs      # full suite — 0 failed; skips are env-only
python3 scripts/gen_model_law.py     --verify      # model.law lane
python3 scripts/gen_okf.py           --verify      # docs.okf lane  (run --write first if you touched docs/)
python3 scripts/check_runtime_bounded.py --verify  # runtime.bounded lane (R2)
node    scripts/ci/coverage_guard.mjs              # coverage.completeness lane
```

A leaf is **done** only when: its gate is green, the full suite is 0-failed, the dup it
targeted is **deleted**, and a **no-regrowth gate** exists so it cannot return. If you
bounded coverage (skipped a sub-case), say so in the commit — no silent caps.

---

# Milestones (in order). Each = one rot item, decomposed into leaves.

Sizing legend: 🟢 mechanical/low-risk · 🟡 behavior-adjacent (assert parity) · 🔴 risky /
semantics · 🔶 needs a Director decision first.

## M1 — R7.1+R7.4 · the model-catalog parity gate (do this FIRST) 🟢

**Intent.** R0 made `MESH_LAW` a generated, drift-gated law. `lgwks_model_hub._MODEL_CATALOG`
(`:37`, 7 entries: repo/revision/license/…) is a *second* model law — its local model
**names must equal** the law's — but **nothing gates the parity**. A code comment claims
divergence "is a tracked conflict"; nothing tracks it. This is the R0 bug class recurring
one module over. Closing it is the highest-value untouched leaf and reuses the R0 template
the agent can study in this very branch (`scripts/gen_model_law.py`).

**Canonical primitive.** The `model.law` lane (`scripts/ci/run.mjs:100`). Extend it; do not
add a parallel lane.

- **R7.1** — Add a parity check (extend `scripts/gen_model_law.py --verify`, or a sibling
  `scripts/check_model_catalog.py` bound into the same lane): the set of `_MODEL_CATALOG`
  entries with `locality=="local"` must equal the set of `MESH_LAW` entries with
  `locality=="local"` and `status=="current_law"`, by model name. *Accept:* renaming/adding
  either side without the other → exit 1 listing the offending names. *Gate:* the
  `model.law` lane.
- **R7.4** — Fix stale provenance: `scripts/build_model_mesh.py` cites
  `MODEL-RUNTIME-FINALIZATION…§3.1`; the R0 source of truth is
  `spec/second-harness/model-law.json` (prose anchor `docs/AETHERIUS_SPEC_2026.md §3`).
  Repoint the docstring to the model-law.json source; drop the finalization reference.
  *Accept:* one provenance string for the law across `gen_model_law.py` and
  `build_model_mesh.py`. *Gate:* `model.law` + `docs.okf` green.

## M2 — R4 · collapse duplicated utilities 🟢🟡

**Intent.** Canonical primitives already exist (`lgwks_hashing`, `lgwks_vecmath`,
`lgwks_clock`, `lgwks_redact`, `lgwks_proc`); callers re-implement slightly-different copies
that drift. One primitive per concept; route every caller; gate against regrowth.
**Do NOT merge the legit forks below.**

- **R4.1 vecmath** 🟡 — replace manual cosine/dot/norm with
  `lgwks_vecmath.{cosine,dot,l2_norm}` in: `lgwks_jarvis:133`, `lgwks_vector:201,212`,
  `lgwks_substrate_vector:21,23`, `lgwks_score:184,348`, `lgwks_pipeline:141,173`,
  `lgwks_concept:459,594`, `lgwks_viz_project:256`, `lgwks_multimodal:135,145`,
  `lgwks_apple:140`. *Accept:* no `sum(x*y …)`/`sqrt(sum(…))` in those files; vector parity
  asserted; suite green.
- **R4.2 plain-hash** 🟡 — route plain content-hash sites to `lgwks_hashing`:
  `lgwks_score:346`, `lgwks_viz_project:254`, `lgwks_portal._sha:57` (width-12 →
  `content_id(n=12)`), `lgwks_jarvis:85`. *Accept:* IDs are byte-identical to the OLD
  output for the SAME input — assert the full digest **including encoding** (hex vs base64),
  algorithm, and truncation width, not just the width. `content_id(n=12)` must reproduce the
  exact 12-char string `hashlib.sha256(x)…[:12]` produced, or stored CIDs fork silently. If
  encodings differ, this is NOT a mechanical route — STOP (🔶) and surface it. No bare
  `hashlib.sha256(` left there.
- **R4.3 ISO-clock** 🟢 — route `lgwks_models_dev:82,98` and `scripts/build_model_mesh.py:31`
  to `lgwks_clock`. *Accept:* no `datetime.now(` in those; `test_clock_formatters` green.
- **R4.7 regrowth guard** 🟢 — add ONE source-scan test (model it on
  `tests/test_one_embedder.py`) forbidding manual cosine / bare `hashlib.sha*(` / `datetime.now(`
  outside the canonical modules, with an **allow-list** for the legit forks (below).
  *Accept:* reintroducing any straggler fails the test.
- *Optional continuation if time:* **R4.5 git-proc** (route `lgwks_repo:49`, `lgwks_gh:238`,
  `lgwks_home:761` to `lgwks_proc.run_git`); **R4.6 redact** (route `lgwks_run._scrub`,
  `lgwks_audit._redact`, `lgwks_hooks._scrub` to `lgwks_redact.scrub` *after confirming each
  is PII-scrub*).

**Legit forks — DO NOT touch in R4** (add to the R4.7 allow-list): keyed/crypto hashing
(`lgwks_vault` KDF, `lgwks_capability`/`lgwks_sign`/`lgwks_axiom`/`axiom/verify` HMAC,
`lgwks_multimodal` perceptual fp, `axiom/cid` ADR-068 CID, `lgwks_input` file fp);
`lgwks_proc`'s documented git forks (`lgwks_axiom._git`, `lgwks_daemon._git`); elapsed-duration
`time.time()` (workflows/do/axiom/daemon).
**Deferred fork F2 (epoch clock) → M-later:** ~17 `time.time()` *stamp* sites store epoch
floats and `lgwks_clock` has **no** epoch primitive. Do NOT convert stamps to ISO (wire
change). The fix is **R4.4**: add `lgwks_clock.epoch()` (pure addition) then route the 17
sites. Schedule after M2's core lands.

> ⛔ **CHECKPOINT 1** (after M1+M2). See "Checkpoints" — STOP, do not push, tell the
> Director to check in with Opus. Opus reviews + pushes M1/M2, and **rules the two
> R5 forks below** before M3 starts.

## M3 — R5 · route model stragglers through the one port 🟡🔶

**Intent.** Every model resolve/invoke flows through `lgwks_model_port` (the ladder). The
named suspects were mostly false: `lgwks_map`/`lgwks_score` are deterministic-by-design
(**keep**), `lgwks_cohere` is the Coherence-Engine Rust gate, not an LLM (**drop from R5**).
The real rot is the **embed role**: callers reach the embedder *beside* the port.

- **R5.1** 🟡 — route the 4 direct `lgwks_run.embed_dual` callers
  (`lgwks_search_engine:103`, `lgwks_fabric_reader:153`, `lgwks_substrate_run:289,327`)
  through `lgwks_model_port.embed(...)` and read the envelope `value`. *Accept:* those files
  don't import `embed_dual`; vector parity asserted; suite green.
- **R5.4** 🟢 — straggler guard: source-scan test forbidding `lgwks_run.embed_dual` /
  `model_name_for_role` / direct provider imports outside an allow-list (`lgwks_model_port`
  + the tier modules `lgwks_run`/`lgwks_apple`/`lgwks_openrouter_embed`/`lgwks_reasoning_port`/
  `lgwks_embed_port`, + `lgwks_model_hub`/`lgwks_models_dev`). *Accept:* a new bypass fails.
- **R5.2** 🔶 — the 5 deterministic *audit-vector* callers
  (`lgwks_codebase:552,656`, `lgwks_gate_idiom:54,94`, `lgwks_geoexpr:206`,
  `lgwks_project_deploy:169`) call private `lgwks_embed._embedding`. **Fork:** (A) route
  through `model_port.embed` for provenance, vs (B) expose a public
  `lgwks_embed.embedding()` audit-only API and depend on that. *Opus decides at CP1.*
- **R5.3** 🔶 — **two embed ports** exist: `lgwks_model_port.embed`/`embed_dual` (role
  envelope) vs `lgwks_pipeline.embed_text`/`lgwks_embed_port` (MLX/VL runtime). Which is
  canonical? Collapse the other to a delegator. *Largest R5 ambiguity — Opus decides at CP1;
  do not touch until ruled.*

## M4 — R7.2+R8 · completeness gates (DOMAINS + module coverage) 🟢

**Intent.** Two structural gaps where "green" doesn't yet mean "covered."

- **R7.2** 🟢 — `lgwks_cli_introspect.DOMAINS` (`:26`) hand-lists verb→domain; verbs can
  drift from real registrations. Add a gate: every `DOMAINS` verb resolves to a registered
  dispatcher verb, and every registered verb is classified exactly once (or in `Other`).
  *Gate:* fold into `coverage.completeness` (`scripts/ci/coverage_guard.mjs`) or a small lane.
- **R8** 🟢 — **module-coverage gate.** `coverage_guard.mjs` ensures test *files* run, not
  that every module *is* tested; ~20 `lgwks_*.py` with live callers have zero test
  references (`lgwks_do` 554, `lgwks_project_deploy` 469, `lgwks_substrate_crawl` 433,
  `lgwks_multimodal` 349, `lgwks_substrate_vector` 252, `lgwks_foundation` 199, +14). Add a
  lane: every tracked `lgwks_*.py` with live callers is imported by ≥1 test, with an
  EXCLUDED-with-reason list (mirror the existing coverage_guard pattern). Then start paying
  down the list (smallest first) — but the GATE landing is the M4 deliverable; backfilling
  tests can continue opportunistically. *Accept:* the lane fails if a new untested module
  with live callers appears. (Also surfaces the `lgwks_foundation:134` stub-as-runtime TODO.)

> ⛔ **CHECKPOINT 2** (after M3+M4). STOP, do not push, check in with Opus. Opus reviews +
> pushes M3/M4 and **rules the R3 + R6 forks below** before the hard milestones.

## M5 — R3+R9 · one front door; finish the orchestrator collapse 🔴🔶

**Intent.** The canonical front door **exists**: `engine/engine.py:dispatch()` enqueues
plan steps through the one registry+queue (`WORK_REGISTRY`/`WorkCapability` in
`lgwks_daemon_store.py`) and the daemon drain loop. Four heads are already killed +
registered (`engine/deprecated_heads.py`, gated by `tests/test_deprecated_heads.py`). The
collapse is ~70% done. The surviving slop: **two execute-inline paths bypass the queue.**

- **R3.1** 🟢 — doc reconcile: the program doc R3 row says the target verb is `route act`;
  the shipped front door is **`agent`** (`route` retired, `lgwks:47`). Fix
  `pristine-codebase-program.md` to say `agent`. *Accept:* doc names the verb the dispatcher
  registers; `docs.okf` green.
- **R3.2** 🟡 — make `lgwks_route.act_intent` a thin shim over `engine.dispatch` /
  `dispatch_and_await`; delete its inline `_choose_action`/`_execute_codebase_search`/
  `_execute_research`. *Accept:* `route act <intent>` yields identical artifacts via the
  daemon path; `tests/test_route_act.py` retargeted to the enqueue+await invariant (say so).
- **R3.3** 🔴🔶 — `lgwks_agent.compose` runs caps inline instead of enqueuing. **Fork:**
  enqueue write/network kinds through `engine.dispatch` (gains durability/ledger) vs keep
  the sync read-path for latency. *Opus rules at CP2.* (Recommended: enqueue write/network,
  keep read inline.)
- **R9** 🟡 — `lgwks_do` is a declared killed-head yet `lgwks_agent:221,309` still calls
  `lgwks_do._run_review`/`_run_aup_check` live. Absorb those leaves into daemon work
  handlers (per `engine/DAEMON-ABSORPTION-LOG.md`), repoint `lgwks_agent`, delete the
  boilerplate. *Accept:* nothing on the live path imports a killed head.
- **R3.4** 🟢 — no-regrowth: extend `tests/test_deprecated_heads.py` to assert no module
  outside `engine.dispatch` invokes a `WORK_KIND` capability inline. *Accept:* a new parallel
  execute-loop fails the test.
- **Keep separate (NOT R3 scope):** `lgwks_repl`'s interactive dispatch — it's a presentation
  surface, not an orchestrator.

## M6 — R6 · decompose the god-functions 🟡🔴

**Intent.** Honor the doc's "decompose behind existing seams **when touched**." Exact counts
(AST-verified): `build_run` 469 (`lgwks_substrate_run.py:147`), `crawl_command` 418
(`lgwks_jarvis.py:513`), `run_auto` 385 (`lgwks_research.py:734`). Each has clean
comment-banner phase seams and existing helpers — extract behind them, invent nothing.

- **R6.1** 🟡 — extract `build_run` phases (chunks/media/concepts/graph/vectors/relational —
  the `# ──` banners) into private helpers; `build_run` becomes a ~40–80-line sequencer.
  *Accept:* `build_run` ≤ ~80 lines; `tests/test_substrate_gate_projection.py` green.
- **R6.2** 🔴🔶 — **kills the R3∩R6 dup, but it is semantics-bearing, not mechanical:**
  `crawl_command:677` reimplements build_run's chunk-ingest loop ("Mirrors
  lgwks_substrate_run.build_run"). The two loops are historically divergent — chunk-boundary
  logic differences produce DIFFERENT CIDs, which forks stored content. Do NOT treat as a
  🟡 routing. **First** write a parity test asserting jarvis-crawl and `build_run` produce
  identical chunk CIDs for a fixed input and **land it red/green as a real gate** (not just an
  acceptance note); only then route `crawl_command` through the R6.1 helper. If the CIDs
  already differ today, that is a 🔶 — surface the divergence to Opus before changing either.
  (Coupled to M5; sequence the jarvis dup once.)
- **R6.3** 🔴 — extract `run_auto`'s per-round body into `_run_round(state)`; **thread the
  rolling digest/budget/frontier state explicitly** (the one real behavior-change risk).
  *Accept:* `run_auto` ≤ ~120 lines; research tests green; add a golden-trajectory test if
  none exists.
- **R6.4** 🟢 — no-regrowth size gate: a small AST lint (extend `scripts/gen_navmap.py` or a
  new check) failing if any `lgwks_*.py` function exceeds ~200 lines beyond an allow-list.
  *Accept:* the three shrink or are allow-listed with a tracking issue.

> ⛔ **CHECKPOINT 3** (after M5+M6). STOP, push with Opus, then run the **completeness
> critic**: "what rot did closing these reveal?" Add R10+ rows to the program doc and the
> rot table. Re-confirm the "pristine" definition's six checks each pass by command.

---

# Checkpoints — the rule the executing agent MUST obey

After each checkpoint's two milestones: **commit everything locally, run the full gate, then
STOP. Do NOT `git push`. Do NOT open a PR.** Emit exactly this, then wait for the human:

```
⛔ CHECKPOINT <N> REACHED — go check in with Opus before anything goes upstream.
Landed locally on <branch(es)>: <one line per leaf>.
Gates: node scripts/ci/run.mjs → <GO/NO-GO>; full suite → <N passed / M failed>.
🔶 Forks needing an Opus ruling before the next milestone: <list, or "none">.
Blast-radius notes for each open fork: <2–3 lines each>.
Paste this to the Director and wait. Do not start the next milestone until Opus rules.
```

## The push-block hook (install before any work — the checkpoint rule is not honor-system)

Write `.git/hooks/pre-push` (chmod +x) so a stray/auto push fails closed:

```sh
#!/bin/sh
echo "Pristine Program: push is checkpoint-gated — see docs/concepts/pristine-build-order.md" >&2
echo "The Director removes this hook to push at a checkpoint." >&2
exit 1
```

The human deletes the hook to push at a checkpoint, then restores it. If you (the executing
agent) cannot install it, STOP and say so — do not work on the honor system.

The Director takes that to Opus, who reviews the diff, resolves the 🔶 forks, pushes the
milestone branch(es) to origin+gdrive, and opens the PR(s). Only then does the agent
continue. This keeps every upstream update Opus-reviewed and every hard fork
Opus-decided — the agent executes the mechanical 80%, Opus owns the load-bearing 20%.

# Sequence at a glance

| Milestone | Rot | Risk | Director-gated leaves | Checkpoint | Status |
|---|---|---|---|---|---|
| M1 | R7.1 catalog parity + R7.4 provenance | 🟢 | — | | ✅ done (#350) |
| M2 | R4 dup-utility collapse (+ R4.4 epoch after) | 🟢🟡 | — | ⛔ **CP1** → Opus rules R5.2, R5.3 | ✅ done (#350) |
| M3 | R5 model-port stragglers | 🟡 | R5.2, R5.3 | | ✅ done (#350) |
| M4 | R7.2 DOMAINS + R8 module-coverage gate | 🟢 | — | ⛔ **CP2** → Opus rules R3.3, R6.2 | ✅ done (#350) |
| M5 | R3 front-door collapse + R9 absorb lgwks_do | 🔴 | R3.3 | | ⚠️ **blocked at root (G10)** — see below |
| M6 | R6 god-function decomposition | 🟡🔴 | (R6.2 per CP2) | ⛔ **CP3** → completeness critic | ✅ done (#352) |

# Final status & next-agent handoff (2026-06-26)

The **de-slop executable scope is delivered**: M1–M4 (PR #350) and M6 (PR #352) landed;
full suite green, local Keel CI GO modulo the pre-existing report-only `target.gate` (#304).

**M5 was ruled blocked at the root, not skipped.** The front-door collapse is gated by
**G10**: the daemon executor (`lgwks_daemon._dispatch_item`) runs only 5 kinds
`{research_run, ingest_file, index_run, workflow, worktree_*}`; everything else is a logged
no-op. The repo's own `engine/DAEMON-ABSORPTION-LOG.md` binds the order
*make-daemon-execute → reroute → delete*, so the leaf framing runs ahead of the gate:
- **R3.1** ✅ already satisfied (the doc names the live verb `agent`; `route` is retired).
- **R3.2** (shim `route`) — `lgwks_route` has **zero live callers** and its `codebase_search`
  kind is not daemon-executable; shimming it would route to a no-op. Leave frozen until G10.
- **R3.3 / R9** — `lgwks_do`'s leaves are still the shared library for `lgwks_workflows`'
  4 live verbs, so they cannot be deleted until absorbed + the daemon can execute their kinds.

**What unblocks M5: closing G10** (make the daemon execute the remaining kinds) — daemon-**core**
work, tracked under the orchestration-consolidation epic **#255**, not a de-slop leaf.

**Decomposition debt** from M6 (the cohesive functions left ≥200 lines: `_run_round`,
`crawl_command`, `_ingest_docs`, + 6 pre-existing) is allow-listed in the R6.4 size-ratchet
gate and tracked in **#351**.

**M5/M6 forks ruled by Opus** (CP2): R3.3 → enqueue write/network as a `workflow` item once
G10 closes, keep reads inline; R6.2 → chunkers already converged (one `SlidingWindowChunking`
+ one hash seam), so it downgraded to a parity gate, not a risky merge.

# See also

* [The Pristine Codebase Program](pristine-codebase-program.md) — the doctrine + rot inventory.
* [Escalation & Robustness](escalation-robustness.md) — R1+R2, the first worked design.
* [Model Layer](model-layer.md) — the one port M3 routes through.

# Citations

[1] Repo `CLAUDE.md` — operating contract, authority ladder, load-bearing-root invariant.
[2] `engine/engine.py`, `lgwks_daemon_store.py`, `engine/deprecated_heads.py` — the R3 canonical front door.
[3] `scripts/gen_model_law.py` + `spec/second-harness/model-law.json` — the R0/R7 template.
[4] `lgwks_vecmath.py`, `lgwks_hashing.py`, `lgwks_clock.py`, `lgwks_model_port.py` — the R4/R5 canonical primitives.
