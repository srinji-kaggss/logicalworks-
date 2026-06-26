---
type: Reference
title: lgwks-human — daemon control surface (Rust TUI)
description: The human→daemon control surface. A Rust TUI that observes daemon-events.db and steers the daemon via the canonical ops-daemon emit/enqueue write path. Documents the confirm-gate invariant, the WORK_KIND-vs-event-KIND split, and the affordance/input key routing.
tags: [frontier, reference, tui, daemon, human, control-surface, rust]
owning_issue: "323"
timestamp: 2026-06-26T00:00:00Z
---

# lgwks-human — daemon control surface

> The human half of the daemon loop: a Rust TUI (`lgwks-human/`) that **observes**
> `daemon-events.db` read-only and **steers** the daemon via its canonical write
> path. Audience: anyone touching the crate or the daemon CLI contract. See
> [OPERATING-MODEL](../OPERATING-MODEL.md) for the request/daemon lane split this
> sits in.

## What it is

A single-binary TUI (`cargo run -p lgwks-human`) with four screens — FLIGHT
(cognition stream + affordance panel + free-text intent), RUNS, QUEUE, WIRE —
backed by a `DaemonBridge` that polls the SQLite store every 250 ms over a
read-only WAL connection and writes through the `lgwks ops daemon …` CLI.

## The two write paths (do not collapse)

The daemon has **two** ingestion verbs and they are not interchangeable. Mixing
them is the bug that made every TUI action a silent no-op (see §History).

| Intent | Verb | CLI | `--kind` domain | Lane / scope |
|---|---|---|---|---|
| Free-text human intent | **emit** an event | `lgwks ops daemon emit` | event KIND (`human_message`, …) | `--lane ingress --scope agent_local` |
| Picked affordance | **enqueue** a work item | `lgwks ops daemon enqueue` (stdin JSON) | WORK_KIND (`research_run`, `worktree_close`, `workflow`, …) | (none — work queue) |

- **Affordances are WORK_KINDS, not event KINDS.** `research_run` /
  `worktree_close` / `workflow` cannot be `emit`-ed (`--kind` rejects them);
  they must be **enqueued**. Free-text must be **emitted** as `human_message`.
- The daemon command is wired under **`ops`** (`lgwks ops daemon …`), not
  `lgwks daemon …`. The latter fails at the argparse command level (exit 2),
  which is invisible if the write path swallows the exit.

## The confirm-gate invariant

An affordance picked from FLIGHT is gated by `needs_confirm(step.approval)`,
**not** `step.risk`. The gate keys off the daemon's PULSE `approval` class:

- `approval == "none"` → fire directly.
- `approval ∈ {"once", "force"}` → require a human confirm overlay.
- **missing / unknown** → **fail-closed** (require confirm).

Why `approval`, not `risk`: an irreversible op (`worktree_close`, `workflow`)
carries `risk="medium"` but `approval="once"`. A gate on `risk=="high"` lets it
fire un-confirmed. `approval` is the effect/irreversibility-derived field, so it
is the correct authority. Fail-closed on unknown is mandatory — a daemon that
omits the field must never bypass the gate.

`approval` is part of the Rust `NextStep` (and the Python `ContextPacket`
already emits it). Both the keyboard and the mouse affordance sites route through
one `affordance_cmd` helper — do not re-duplicate them.

## Write-path error surfacing

`run_daemon_write` surfaces **two** failure shapes as `Err` (the old path
swallowed both, so every action was a silent no-op):

1. **Non-zero process exit** (argparse/usage exit 2) → `daemon write exit N: <stderr>`.
2. **Structured rejection** — the command exits 0 but prints `{"ok": false, …}`
   (queue full / invalid item) → `daemon rejected: <status> <detail>`.

Both are rendered in the status bar (`enqueue failed: …` / `emit failed: …`).

## Panic-floor invariants (DoS via crafted event data)

- **No byte-slicing daemon-supplied strings.** Every bounded preview routes
  through `util::head(s, max_chars)` / `util::head_ellipsis` — char-boundary
  safe, never panics on multibyte input. Do not reintroduce `&s[..n]` or
  `.get(a..b).unwrap_or("")` for display strings; the latter silently empties
  the field when the cut lands inside a multibyte char.
- **No `.unwrap()` on shutdown paths.** `Drop for Tui` uses `let _ = self.exit()`
  (never double-panic the terminal restore); the TUI event-loop `send`s use
  `let _ = _tx.send(...)` (the receiver drops first on quit — an `.unwrap()`
  there panics the poll task).
- **Poisoned-lock recovery** uses `unwrap_or_else(|p| p.into_inner())` for read
  guards in render paths and the standalone demo task.

## Key routing (FLIGHT)

The app-level global handler owns **only** `Ctrl-F/R/W`, `Tab`/`BackTab`, and
`Ctrl-Q`. **Bare digit shortcuts (1–4 → screen) are deliberately absent** — they
collided with FLIGHT's affordance hotkeys (`1`–`9` in normal mode pick affordance
N; `Alt+N` is the escape hatch from input mode) and with typing digits in the
free-text input. Screen switching is fully covered by the Ctrl/Tab bindings.

FLIGHT digit arm contract (must stay):
- `Alt+N` (any mode) → affordance N.
- bare `N` (normal mode) → affordance N.
- bare `N` (input mode) → **typed into the input** (must not be swallowed).

## `--standalone` demo mode

Daemon-less demo seeds a stub `ContextPacket` with `simulated: true`, which the
FLIGHT screen renders as **"DEMO DATA"**. The synthetic entropy/tps/dials are
explicitly not the real telemetry the Python side refuses to fabricate (A12).
The seeded affordance kinds (`connect_models_dev`, `init_local_llm`) are demo
stubs, not `WORK_KINDS` — they are inert without a live daemon.

## History (the bugs this design exists to prevent)

1. **Confirm gate on `risk`** — let irreversible medium-risk ops fire
   un-confirmed. Fixed: gate on `approval`, fail-closed.
2. **Write-path dead (`lgwks daemon` vs `lgwks ops daemon`)** — argparse exit 2,
   swallowed → every TUI action a no-op. Fixed: canonical `ops daemon` path +
   split emit/enqueue by KIND domain + surface exit/rejection.
3. **`&s[..n]` UTF-8 panic cluster** — crafted event payload panicked the
   render thread. Fixed: canonical `util::head`.
4. **Bare-digit screen shortcuts** — hijacked affordance hotkeys 1–4 and made
   digits un-typeable in the input. Fixed: removed the global digit shortcuts;
   forward bare digits in input mode to the input handler.
5. **`send().unwrap()` on the TUI poll task** — panicked on shutdown when the
   receiver dropped first. Fixed: `let _ = _tx.send(...)`.

## Tests

`cargo test` → 16 tests: 6 confirm-gate/affordance (incl. the irreversible-
medium-risk case + fail-closed on missing `approval`), 6 char-safe truncation
(multibyte + emoji), 3 key-dispatch integration (bare-digit-→-affordance,
Alt-digit-from-input, digit-typed-in-input), 1 low-risk-direct-enqueue. The
key-dispatch tests guard the integration bugs the unit tests on
`needs_confirm`/`affordance_cmd` could not see.