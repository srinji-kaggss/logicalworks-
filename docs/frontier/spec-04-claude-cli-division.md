---
type: Spec
title: SPEC-04 — The Claude + CLI Division of Labor
description: A tool call today costs: tokens to figure out the command, tokens for raw output flooding context,
tags: [frontier, spec]
timestamp: 2026-06-02T16:48:56-04:00
---

# SPEC-04 — The Claude + CLI Division of Labor

> Context, not a build unit. Why the gates exist: they let the CLI absorb deterministic work so the
> generative AI spends tokens only on judgment. The division falls exactly on the verifiability axis.

## The principle

A tool call today costs: tokens to figure out the command, tokens for raw output flooding context,
an approval interrupt, tokens to parse noise — ×15–20 per task. The fix is not faster tool calls; it
is moving deterministic work off the model entirely.

| Above the line — **Claude owns** | Below the line — **the CLI owns** |
|---|---|
| intent, judgment, hypothesis, synthesis | grounding (real API surface, repo state, validated web) |
| deciding which intent to pursue | executing a compiled, argv-safe, batched command-chain |
| deciding a finding is real | enforcing per-command safety via the gate (not human patience) |
| conveying meaning + feeling to the human | explaining, in plain language, what it did and why |
| the non-verifiable (generative) | the deterministic + verifiable |

This is the same axis as spec-02: the CLI takes everything an oracle can check; Claude keeps everything
above where verification ends.

## Four mechanisms that make tool calls vanish

1. **Intent in → condensed cited result out** (not command in → raw bytes out). One intent compiles to a
   command-chain (`x`/`multiply`/`project plan`), runs under one approval, returns a cited artifact. The
   plumbing tokens never enter Claude's context. (Generalizes the proven `extract` ~95% read-saving to *acting*.)
2. **The CLI holds the world-state** (cognition-log + embeddings) and feeds Claude the relevant grounded
   subgraph on demand — no per-session re-grepping. Sensory cortex (CLI) ↔ prefrontal cortex (Claude).
3. **One approval per intent, not per command.** Intent → typed risk-classified plan (`geo`/`x`: argv-only,
   2-layer risk gate); human approves the *plan*; the deterministic gate enforces per-command. Consent moves
   up a level. Same membrane: reason free inside, act gated outside.
4. **Self-explanation is a first-class output** — the CLI emits a plain-language trace ("read these 3 files,
   diffed the auth handler, found the leak at :151"). The human learns; Claude doesn't pay tokens to narrate.

## The honest boundary (and the precondition)

The CLI can replace a tool call **only where the work is deterministic and verifiable.** It cannot take
judgment. So the replacement is asymmetric and maps onto the axis precisely.

**Precondition:** the CLI may absorb autonomy only if its gates are honest (spec-01 + #29). A `refine` that
blames the human, a `crawl` that eats CAPTCHAs — given autonomy, amplify failure instead of saving tokens.
**Therefore this vision and the #29 fix are the same project.** Phase 1+ cannot precede honest gates.

## Phased path (not all-or-nothing)

- **Phase 0 (proven):** CLI as reader — `extract`, ~95% token saving.
- **Phase 1:** CLI as planner+executor under one approval — `geo`/`x`, hardened gates (#29 / U3).
- **Phase 2:** CLI as grounded world-model feeding context — `embed`/cognition-log + relevance gate (U3/U6).
- **Phase 3:** CLI as self-explaining peer — the learning trace. End-state across all deterministic work.

The end-state: **Claude (thinking, feeling, judging) + CLI (the deterministic substrate)** — "you don't need
skills because the CLI is the only skill; it handles the icky work of the gaps and brings us closer."
