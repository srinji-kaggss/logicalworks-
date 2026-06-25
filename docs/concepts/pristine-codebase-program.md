---
type: Plan
title: The Pristine Codebase Program — de-slop lgwks to elegance
description: A self-decomposing program that drives lgwks to a pristine state by reconstructing the original intent behind slop, collapsing it to one canonical primitive, and gating the result with Keel.
tags: [concepts, doctrine, pristine, slop, keel, robustness, sh, program]
owning_issue: "345"
timestamp: 2026-06-25T00:00:00Z
---

# Why this exists

Large parts of lgwks were produced by **a non-technical director + a happy-path LLM**.
The *ideas were sound* — the model ladder, the state fabric, the daemon, the OKF
bundle. The **execution was junior**: plausible-looking code, silent fallbacks,
duplicated-but-slightly-different primitives, laws transcribed by hand until they
drifted from their source. The defect is not the idea; it is the gap between the idea
and a senior execution of it.

This program closes that gap, deterministically, until the codebase is **pristine** —
and it is written so that **any agent can pick it up, decompose it, and keep going
without a human re-explaining it.** The bar is not "passing." The bar is *elegance
codified*: a reader should conclude they did not know an AI could build like this.

> Operating standard: work and review **as an AI Senior Human Dev (SH+)** — an SH
> trying to out-perform a human SH. The senior's value is `−ΔEntropy(requirements,
> architecture, delivery, risk) + ΔCapability`. You lower ambiguity, coupling, risk,
> and future cost; you raise the floor for the next agent. You do not chase perfect;
> you make the change that *definitely* improves health and *cannot* silently rot.

# The method (apply on every problem and every semantic duplicate)

When you find a bug, a fragile path, or two things that do almost-the-same thing, do
**not** patch the symptom. Run this loop:

1. **Reconstruct the intent.** Ask, of the whole cluster: *"what were they trying to
   do as a whole?"* Read the actual source/spec the code was meant to implement — not
   our paraphrase of it. The honest intent is almost always simpler than the slop.
2. **Find the one canonical primitive** that intent demands (hashing, cosine, the model
   port, the state fabric, a law). If it exists, route every caller through it. If it
   half-exists, complete it. A second near-copy *is* the bug.
3. **Re-execute SH-grade.** Make it small and reversible; separate refactor from
   behavior; write the durable *why*; estimate blast radius; never widen a gate to go
   green.
4. **Gate it so it cannot rot.** Generate, don't hand-maintain. Bind the invariant in
   **Keel** (or a test that mirrors a Keel lane) so the *next* regression fails the
   gate instead of shipping. Claim only what a command you ran demonstrates.

The completed [model law](../../spec/second-harness/model-law.json) fix is the
worked template: a hand-transcribed `MESH_LAW` with a hallucinated embed id and
misattributed provenance → reconstruct "one law, generated from a single source,
gated against drift" → re-execute via `scripts/gen_model_law.py` + the `model.law`
CI lane. Slop in; one canonical, gated primitive out.

# The recursive-decomposition protocol

The program is a tree. The P0 epic is the root. **Every agent that touches it must
leave it more decomposed and more done than they found it.**

- **Decompose.** Take one rot item (below). Split it into the smallest set of
  independently shippable sub-issues, each with explicit **acceptance criteria** and a
  **gate** (the Keel lane / test that proves it). File them as sub-issues of the P0
  epic. Decomposing *is* progress — record it.
- **Execute.** Pick a leaf. Reconstruct intent → collapse to canonical → re-execute →
  gate. Open a small PR. Link the sub-issue.
- **Prove.** A leaf is done only when its gate is green *and* the duplicates it
  targeted are deleted (not deprecated-in-place). No silent caps: if you bounded
  coverage, say so in the issue.
- **Never regrow.** Each collapse adds a no-regrowth gate so the dupe cannot return.
- **Report the fork.** If the intent is genuinely ambiguous (two real designs), do the
  full blast-radius analysis and surface the decision to the director — do not guess.

# The rot inventory (evidence-ranked; the root's first children)

Status reflects 2026-06-25. Each becomes one or more sub-issues.

| # | Rot | What the slop was trying to do | Canonical fix | State |
|---|-----|-------------------------------|---------------|-------|
| R0 | **Hand-transcribed model law** (`MESH_LAW`) — hallucinated embed id, misattributed source | one model law, single source of truth | generate from `model-law.json`; gate via `model.law` lane | **DONE** |
| R1 | **Escalation has no tier ceiling** — only the all-or-nothing `LGWKS_NO_MODELS` flag | "don't use the LLM until truly needed," set per-request | caller-set `ceiling` on `escalate()`; `NO_MODELS` becomes `ceiling=deterministic` | spec'd → [escalation-robustness](escalation-robustness.md) |
| R2 | **Unbounded sinks / hang-carriers** (#320) — model/network/subprocess calls that can hang; invisible to a no-model CI | bounded, fail-closed external calls | one bounded primitive (`_run_bounded`); **Keel invariant** that every hang-class sink routes through it | spec'd → [escalation-robustness](escalation-robustness.md) |
| R3 | **Forked orchestrators** (#255) — multiple agentic entrypoints, legacy verb surface | one "do something" front door (`route act`) | absorb surface, then collapse; no-regrowth gate | open |
| R4 | **Duplicated utilities** (#150/#152) — `_sha`/`_cosine`/`_tokens` drift | one primitive per concept | centralize + route all callers; #223 tracks | partial |
| R5 | **Model-port stragglers** (#222) — `lgwks_map`/`geoexpr`/`score` resolve models outside the one port | one cognition gateway | route through `lgwks_model_port` | open |
| R6 | **God-functions** — `build_run` (~471 lines), `lgwks_jarvis` (~420), research (~275) | one readable pipeline | decompose behind existing seams when touched | open |
| R7 | **Hand-maintained laws beyond `MESH_LAW`** | law = generated truth, not typed | apply the R0 pattern to remaining hand-laws | scan needed |

This table is a seed, not a ceiling. The **completeness critic** is part of the job:
when an item closes, ask "what rot did closing it reveal?" and add it.

# Definition of "pristine" (machine-checkable, not vibes)

The program is complete when all hold, each provable by a command:

1. **One canonical primitive per concept.** No second near-copy. (no-regrowth gates green)
2. **Every law is generated** from a single source and **gated against drift**
   (`model.law`-class lanes), never hand-transcribed.
3. **Every external sink is bounded + fail-closed** — proven structurally, so a no-model
   CI is *robust*, not blind (R2 Keel invariant green).
4. **One front door per capability** — no forked orchestrators (R3 closed).
5. **Docs are generated and OKF-conformant** (`gen_okf.py --verify` green) and updated
   *before* CI — the bundle cannot rot.
6. **Green means working.** Every gate proves the thing it names; no gate asserts
   coverage it never ran (the determinism boundary, A14, holds end to end).

# See also

* [Two-Plane Model Layer](model-layer.md) — the one port the ladder runs through.
* [Escalation & Robustness](escalation-robustness.md) — R1+R2, the first worked design.
* [LGWKS OKF](knowledge-format.md) — the docs bundle this lives in.

# Citations

[1] Repo `CLAUDE.md` — operating contract, authority ladder, structural invariants.
[2] `governance/adr-069-keel-verification-authority.md` — Keel as the gate.
[3] `spec/second-harness/model-law.json` + `scripts/gen_model_law.py` — the R0 template.
