# HANDOFF — read this first (for the next instance of me)

You are picking up a **research system**, not a one-off task. Goal: an AI fleet maps the world as it
actually is → lightweight JSON pings → a world-map → which feeds **our OS-layer architecture** (a
"plugin to the internet") and shows where it plugs in. Director values: accuracy over speed, the map
as-it-is (not as-AI-wishes), token economy, ISO/standard rigor, human-in-the-loop verification.

## Reconciled status (last-reconciled 2026-05-27, by Opus processor)
> NOTE: the earlier "real research NOT STARTED" status was STALE. Multiple waves have run.
- **Framework: DONE.** Pipeline, schema, standard, prompts, OS-Spec scaffold all exist.
- **Tier-1 sweeps (T1–T7) + extras: mostly DONE & grounded.** `notes/` + `claims/` populated for
  distribution, moats, identity, **cloud (added 2026-05-27)**, regulation (now with §C claims),
  ecosystems, stack, governance, ecosystems-frameworks-sdks. All JSONL/JSON valid; std-declared.
- **Tier-2 synthesis (T8–T13): PARTIAL.** notes hold 14 `os_hook`, 8+ `arch_directive`, 2
  `discovery`, 6+ `lesson`; `os-spec/backlog.md` has directives; dialectic + level-2 artifacts exist.
  **Still missing: T10 `artifacts/wedge.world-map.md`** (the stitched world-map + wedge).
- **NEW honesty layer (2026-05-27): blindspots.** `notes/blindspots.jsonl` (kind `blindspot`) +
  `artifacts/blindspots.register.json` (§D in ARTIFACT_SCHEMA). 2 high-severity open: the inference
  crossover is modeled-not-measured, and the consumer-device on-device cost curve is ungrounded.
- **Git:** only the T6 ecosystems commit exists; everything else uncommitted (director chose not to
  auto-commit/auto-delete this session). `artifacts/cyberstrikeai-skill-schemas/` is unreferenced
  cross-project bleed — left in place, not part of this research.
- **C01 prototype** (in chat, not saved): "messaging causally drives super-app success" → dialectic
  converged on MYTH (thesis 0.55 vs antithesis 0.86; Alipay/Grab/Gojek succeed without messaging).

## Folder map (`~/logic-research/`)
- `HANDOFF.md` — this file.
- `PROTOCOL.md` — the dialectic engine: anti-bias rules, triage gate, convergence-not-98%, checklist.
- `LW-RS-1.md` — **the standard** (canonical). ISO codes + the subjective scales/caps. Versioned.
- `ARTIFACT_SCHEMA.md` — entry formats: §A lightweight World-Map Notes (the ingestion unit, minified
  JSONL, short keys), §B heavy Opus synthesis markdown, §C distinctive claims + human_input.
- `REFERENCES.md` — skills (thinking, AI-Research, Factory) + Firecrawl SDKs/auth/limits.
- `prompts/GLOBAL.md` — the one global prompt (paste once). Agent-agnostic.
- `prompts/TOPICS.md` — all topic prompts in one file: T1–T7 [CHEAP] sweeps, T8–T13 [OPUS] synthesis.
- `os-spec/SPEC.md` — how arch pings compile into draw.io diagrams (ping→cell mapping, determinism).
- `os-spec/os-spec.drawio` — 4 tabs (us↔world ERD, architecture, compliance, compute). Skeleton.
- `os-spec/backlog.md` — arch_directive register (empty).
- `artifacts/` — older RAC examples + a Level-2 review JSON (the review-layer precedent).

## How it runs
Paste `prompts/GLOBAL.md` into any model → paste ONE block from `prompts/TOPICS.md`. Cheap models
fire T1–T7 (emit pings to `notes/<topic>.jsonl` + ≥2 distinctive claims to `claims/<topic>.json`,
flag hard calls `op:1`). Then Opus fires T8–T13 over the flagged pings → os_hooks, disproof,
discovery + arch_directives, and T13 compiles the OS Spec diagrams.

## Key decisions (and why) — don't relitigate without reason
- **Minified JSONL, short keys, append-only, diff-not-resend** — most token-efficient *reliable*
  AI↔AI format; MD reserved for human-facing §B only. Notes are "short context pings" to a
  world-builder, not documents.
- **Convergence, not a 98% confidence gate** — a target number invites rationalization.
- **Author ≠ scorer** — confidence set by a separate adjudicator; orchestrator reports + flags.
- **Distinctive claims (§C) kept separate from facts** + a `verify` handle + seeded `human_input`
  ("how the director would frame it") — director's N+1 idea, for manual fact-check + reasoning capture.
- **LW-RS/1 outcome-priority** — ISO codes default; if a code would drop a finding, `nonstd:true`.

## What's NOT done (pick up here)
1. **Close the 2 high-severity blindspots, then run T10.** (a) Ground the consumer-device on-device
   inference $/token curve (Apple Neural Engine / M-series / NPU) — the hybrid-router cost model
   depends on it; (b) replace the modeled inference crossover with a measured figure. Then run T10
   to stitch nodes/edges/os_hooks into `artifacts/wedge.world-map.md`. Tier-1 base is now complete.
2. **The ingestion/world-builder agent** that merges pings (by `i`/`sup`) into one graph + the OS
   Spec — not written. Today a human or an Opus T13 pass does it manually.
3. **A `verify`-field linter** (proposed, not built): reject any §C claim whose `verify` lacks a
   concrete handle (URL / named dataset / runnable query). Cheap guard against vague verifiability.
4. **Directive → GitHub issue routing** — deliberately deferred; human-gated per repo governance.

## Environment notes
- Firecrawl: authenticated via `FIRECRAWL_API_KEY` now in `~/.zshenv` (so subagents/non-interactive
  shells inherit it). Verify with `firecrawl --status`. Limits: concurrency **2**, ~**1,200** credits
  — fan grounding ≤2-wide, cache in `.firecrawl/`, reserve the deep dialectic for `op:1` claims.
- Repo for the OS itself: `~/sales-landing-page` (monorepo: apps/landing, apps/crm, apps/mac,
  backend-rust, packages/canvas-protocol). Envelope schemas live in `packages/canvas-protocol/schema`.
- The six model-specific prompt files in `~/Downloads/prompts/` are SUPERSEDED by GLOBAL.md + TOPICS.md.
