---
type: Concept
title: Escalation & Robustness — the tier ceiling and the boundedness invariant
description: Codifies "don't use the LLM until truly needed" as a caller-set tier ceiling on the one escalation harness, and makes a no-model CI robust by proving every hang-class sink is bounded and fail-closed via Keel.
tags: [concepts, model, port, escalation, robustness, keel, ladder, threshold]
owning_issue: "345"
timestamp: 2026-06-25T00:00:00Z
---

# The ladder (existing, correct)

Every cognition request flows through one gateway, `lgwks_model_port`, which escalates
through trust tiers **preferring determinism**:

```text
deterministic  →  sensor  →  generative
(math)            (narrow/symbolic ML)   (LLM — last resort, even when present)
```

The law (`lgwks_model_mesh`) owns precedence; the harness only climbs to a more
probabilistic tier when the cheaper, more trustworthy one cannot answer at the caller's
**confidence threshold**. If nothing answers, it returns `mode="deferred"` and **never
fabricates** (INV-3 / fail-closed). This design is right. Starting at no-model is right.
Two things are missing to make it *robust*.

# R1 — the tier ceiling ("threshold, not chain")

## Problem

The escalation embodies "reach the LLM only when truly needed," but the only control
that *enforces* "don't reach the model" is the global `LGWKS_NO_MODELS` env flag —
**all-or-nothing**. There is no way for a caller to say *"for this work you may climb to
`sensor` but not `generative`."* So ~14 test suites slam the global flag, and the
graduated, per-request control the design wanted does not exist. The kill-switch is the
happy-path stand-in for a real ceiling.

## Design

The caller (daemon / human / agent) sets a **ceiling** = the highest trust tier the
ladder may use for this request. It is the codification of *"don't use the expensive,
less-trustworthy tier until you're really needed."*

```text
escalate(role, attempts, *, threshold=0.0, ceiling="generative", defer_why=...)
```

- `ceiling` ∈ the locked `trust_class` vocabulary (`deterministic` | `sensor` |
  `generative`). Default `generative` = today's behavior (no regression).
- A rung **above** the ceiling is skipped through the **same suppression path** that
  `LGWKS_NO_MODELS` already uses — one mechanism, not a parallel one.
- `LGWKS_NO_MODELS` collapses to the special case **`ceiling="deterministic"`** — a
  near-duplicate control removed, not grown.
- The `escalation` trace records `outcome="above_ceiling"` for skipped rungs, so the
  daemon's training ledger can read *why* the LLM was not used.

`threshold` (how good must a rung be to win) and `ceiling` (how far up the ladder we may
go) together are the full "set threshold, not chain" knob: the caller declares intent;
the law owns precedence; the harness obeys both.

## Acceptance criteria

- `escalate(..., ceiling="sensor")` never invokes a `generative` rung; trace shows
  `above_ceiling`.
- `ceiling="deterministic"` is behaviourally identical to `LGWKS_NO_MODELS=1` (proven by
  a test that runs both and asserts equal envelopes).
- Default (`ceiling="generative"`) reproduces current envelopes exactly — zero behaviour
  change for existing callers.
- The daemon's ask-vs-act surface can pass a ceiling; documented, not yet wired to policy
  (policy wiring is a separate, confirmed step).

# R2 — the boundedness invariant (robustness in the CI, via Keel)

## Problem

A no-model CI is **correct**, but it cannot see whether a model / network / subprocess
call is **bounded**. So a call that hangs in real use ships green — exactly how the
`review` hang reached production while the suite stayed green (#319/#320). The canonical
bound exists (`lgwks_model_port._run_bounded` + `_model_timeout`;
`lgwks_embed_port`'s `LGWKS_EMBED_TIMEOUT`), but it is applied by convention, not proven.

## Design

Make boundedness a **gated invariant**, not a habit:

1. **One bounded primitive.** Every hang-class external call — model load/generate,
   network request, external worker subprocess — routes through the canonical bound
   (`_run_bounded` or an equivalent timeout). Scope is the *genuinely blocking* class;
   fast, local git calls are out of scope and explicitly listed.
2. **A Keel lane (`runtime.bounded`)** that statically proves the invariant: no
   hang-class sink escapes the bound. New unbounded sink → lane fails → cannot ship. This
   is the structural fix for the #320 disease class, replacing per-hang whack-a-mole.
3. **Fail-closed on timeout.** A bounded call that times out degrades to `deferred`
   (never a crash, never a fabricated value), preserving INV-3.

## Acceptance criteria

- An inventory of hang-class sinks exists and each is either bounded or listed as
  out-of-scope with a one-line reason (no silent omissions).
- The `runtime.bounded` Keel lane fails on a newly introduced unbounded model/network
  sink (proven on a known-bad fixture, the Keel way).
- A simulated hang in a weight tier returns `mode="deferred"` within the timeout, with
  the hang recorded in the `escalation` trace — verified without loading a real model
  (the fake is injected at the port seam; A14 — the deterministic layer validates the
  nondeterministic path's *shape* without its weights).

# Why this is the robustness, not "run models in CI"

The point is never to run a 32B model in CI. It is to prove the *contract* around the
model path: it climbs no higher than allowed, it cannot hang, and it fails closed. Then a
no-model default is **robust** rather than **blind** — green means working, even for the
paths CI deliberately does not execute.

# See also

* [The Pristine Codebase Program](pristine-codebase-program.md) — R1/R2 are its first items.
* [Two-Plane Model Layer](model-layer.md) — the locality axis orthogonal to this ladder.

# Citations

[1] `lgwks_model_port.py` — `escalate`, `_run_bounded`, `models_suppressed`, INV-3.
[2] GitHub #320 — "Hang-carrier dredge: remaining unbounded sinks + NO_MODELS test-blindness."
[3] `governance/adr-069-keel-verification-authority.md` — Keel lanes as gated invariants.
