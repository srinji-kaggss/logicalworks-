# PRD-07 — Taps & Channels (hooks in, projections out)

Parent: [PRD.md](../PRD.md) §5 taps + L5 + U7/U8/U9 · Status: **U7-minimal shipped** (hooks/subconscious_inbound.py, commit d5ae253)
Replaces: nothing — this is the delivery layer; it makes everything else exist for its two readers.

## Verified harness surface (checked 2026-06-09 against code.claude.com/docs/hooks)

All parent §5 events exist: `UserPromptSubmit`, `PostToolBatch` (blocks: stops the agentic
loop before next model call), `PostToolUse`, `FileChanged`, `TaskCreated/Completed` (both
block), `ConfigChange` (blocks), `SessionStart/End`. Parent's "verified live" claim holds.

## Scope

- IN: inbound tap (shipped v0; grows by consuming PRD-04's budgeted schema instead of
  formatting its own lines — current string-formatting in the hook migrates to
  `lgwks.inbound.v1` rendering).
- IN: mid-turn steer (`PostToolBatch`): refresh every ~3 steps OR critical-fact hit; terse
  non-generative signal; block allowed ONLY for pre-registered classes (see blocking policy).
- IN: cockpit (U9, web): Director projection — C/G/P trend, flags w/ spans, budget ledger
  (04-c), subconscious health (INV-9 failure feed), **pause Opus**. Auth spec lives in
  PRD-08 and ships BEFORE the cockpit serves a single byte.
- IN: INV-1 enforcement: two projection modules (`projection_opus.py`, `projection_cockpit.py`),
  no shared formatter; conformance test asserts field-set disjointness where specced.
- OUT: analysis (PRD-06), retrieval (PRD-04), persistence (PRD-08).

## Blocking policy (hardening of parent §5 — blocks are T0-grade acts)

A tap may `block` only on: (a) destructive-op gate (ConfigChange/TaskCompleted classes
enumerated in a versioned allowlist), (b) mid-turn halt when an unverified-claim flag with
precision-gated detector fires on a statement that is about to drive a state-changing tool
call. Every block writes a cockpit record with the evidence span. No experimental detector
may block (cockpit-only until precision-proven, per 06-d).

## Latency law (tightens INV-7)

Inbound: p95 ≤ 1s, hard self-kill at 3s (30s is the harness ceiling, never approached —
current: ~180ms). Mid-turn: p95 ≤ 500ms (it sits between every model call). Measured and
logged per fire (PRD-08 ledger); regression = failed build, not a vibe.

## Failure law (INV-9, replaces bare fail-silent)

Toward Opus/Director prompt-path: fail-silent, always (INV-6). Toward the cockpit: every
swallowed exception appends `{ts, tap, error}` to a local failure log the cockpit surfaces.
`LGWKS_SUBCONSCIOUS=0` disables every tap (INV-10) — one env var, tested.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 07-a (shipped) | inbound v0: prompt → map → additionalContext, fail-silent, 180ms — DONE (commit d5ae253) |
| 07-b schema migration | inbound renders lgwks.inbound.v1 (budget enforced by 04-a); injection byte-size asserted in test |
| 07-c failure feed | induced hook crash → zero Opus impact AND a failure-log entry; kill switch proven (env set → no injection, no daemon taps) |
| 07-d mid-turn steer | PostToolBatch fires, refresh cadence honored, p95 ≤500ms over 100 fires; block path exercised on a synthetic destructive-op fixture only |
| 07-e projections | two modules, disjointness conformance test green; cockpit shows nothing from the Opus schema verbatim and vice versa (INV-1 machine-checked) |
| 07-f cockpit v0 | localhost web app behind PRD-08 auth; shows engine output + ledger + failure feed; pause Opus works (documented mechanism, reversible) |

## Open questions → SCIENCE.md

Mid-turn cadence (every-3-steps is a guess — measure steer-acted-upon rate, §7); whether
injected context measurably changes Opus behavior (the whole-system ablation, §8).
