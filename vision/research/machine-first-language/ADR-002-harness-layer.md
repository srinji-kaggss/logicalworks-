# ADR-002 — The Logical Works harness layer

- **Status:** accepted (2026-05-31), partially built. Parent: #7 / #9.
- **Context:** the instrument's value is not the model — it is the *harness* around the model that
  forces curiosity, objectivity, and token discipline, and that makes every run replayable research.
  This ADR records how the harness layer is shaped to (1) look distinctly ours, (2) be visual,
  (3) force token spend into reasoning not output, mapped to DeepMind research-AI principles.

This is a machine-first artifact: the next reader is an AI. It is auditable by humans where it must be.

## D1 — Two-band contract: spend tokens in reasoning, not in the answer

**Rule:** every model call returns two bands — `think` (unbounded, logged, never shown raw) and a
**surface** (hard-capped, shown). The reasoning is where compute is spent; the surface is a receipt.
A 1000-word answer is a bug; a 1000-word `think` with a 30-word surface is correct.

- Enforced by schema: the Tongue already splits `think` + `digest`/claims (`reason_over_findings`,
  `contrarian` in `lgwks_tongue.py`). Generalise: a `surface` field with a machine-checked word cap;
  over-cap → reject/clip, never widen.
- `//why`: this is T8 (output economy) made structural — the model cannot be verbose at the user; it
  can only be verbose at itself, on the record. Mirrors DeepMind co-scientist (heavy internal
  search, compact verified output) and AlphaProof (vast proof search → one checked line).

## D2 — Curious · objective · research-driven (DeepMind mapping)

| Principle | Mechanism (where) | Status |
|---|---|---|
| **Curious** — explore by expected information gain, not by interestingness | EIG frontier in `reason_over_findings`; novelty knob | built (estimate) |
| **Objective** — defend the null; seek disconfirmation | H0 mandatory null + `contrarian` steelman; truth-over-interestingness in prompts | built |
| **Research-driven** — falsify, ground in prior art | concrete falsifier per hypothesis; `builds_on` citations; evidence tiers | built; *citations need verification (D5)* |
| **Debate → rank** (co-scientist Elo) | contrarian is the seed; add a ranking/debate stage that scores surviving H by survived-attacks | planned |

## D3 — Distinct identity (looks like ours)

A defined **render grammar**, not ad-hoc printing: the `◆` node marker, `█` confidence bars, `→`
trails, `Ø` falsifier, `⊕ builds on`, the `RISK/GAP/STRUGGLE` close. Every artifact carries the LW
envelope: constitution version + hash, `run_id`, integrity mode, ledger-intact. Consistency *is* the
brand — a reader knows a Logical Works artifact on sight, and a peer AI can parse it deterministically.

## D4 — Visual

The live "where is the AI now" view (Unit C): current round · frontier node · surviving H · confidence
movement · budget burndown — rendered from the round events `run_auto` already emits. Plus the mermaid
path map (`research-map.mmd`) and the STATE MATRIX (D5). Visual = the human sees the *shape* of the
search without reading the reasoning.

## D5 — Math for AI / auditable for humans

The same state is carried two ways: a **dense form the model operates on** and a **rendered grid a
human audits**. Built: the STATE MATRIX in `lgwks_context.py` (round × {surviving, hit, converged,
spent}); the Confidence formula `Tier_cap ⊗ σ(λ·W + (1-λ)·B)`; the EIG scores; the HMAC hash-chain.
Planned (Unit D, "Axiom envelope"): compile intent + hypothesis ledger into a compact symbolic/numeric
form (token-efficient for the model) with a deterministic renderer to human-auditable text. Humans
needn't read the math; the model optimises on it; peer-reviewer AIs verify it.

## D6 — LOD context binning for the next spawn  *(built — `lgwks_context.py`)*

A fresh spawn reads context at **decaying resolution** — recent sharp, old one-line — so the window
isn't burned on stale detail:

    TIER 0  last  5 round JSONs   — symlinked RAW (full fidelity)
    TIER 1  last  3 think logs    — verbatim
    TIER 2  last 10 rounds        — compact (one digest line)
    TIER 3  last 20 rounds        — ultra-compact (one headline line)

Written to `runs/<id>/CONTEXT/{CONTEXT.md, raw/*.reason.json}` at the end of every run. This is the
rolling-digest idea as levels-of-detail, and the run-level analogue of the active/archive memory tiers.

## D7 — Log our work as research docs

Every run already persists per-round artifacts + a hash-chained ledger. Each run gets a synthesis
(`vision/intent-research/<date>-<topic>.md`, the H0-log pattern). Design work (this ADR) is itself a
research doc. Nothing the instrument does is ephemeral; the corpus is the asset.

## Consequences

- The harness, not the model, is the moat — it is model-agnostic (free OpenRouter chain today,
  diffusion/local tomorrow) and the discipline survives any swap.
- Open: enforce the surface word-cap mechanically (D1); build the debate/rank stage (D2); the live
  viz (D4, Unit C); the Axiom envelope (D5, Unit D, spec-first).
