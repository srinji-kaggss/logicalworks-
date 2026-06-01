# Intent Research Log — "Human Slop"

- **Date:** 2026-05-31
- **Instrument:** lgwks research-akinator (Issue #7)
- **Tongue:** cloud (OpenRouter free chain) — preferred `nvidia/nemotron-3-super-120b-a12b:free`,
  fallback `qwen/qwen3-next-80b-a3b-instruct:free` → … (rotates on upstream 429)
- **Eye:** local `qwen3-embedding:8b` (not run — `--no-embed` for this Tongue-only pass)
- **Conduct (L9):** YES — intent maps to falsifiable causal chains within scope
- **Constitution:** 1.0.0 · 9 laws active

This is the **first genuine end-to-end autonomous-Hn compile** through the cloud Tongue. It is the
record of the instrument working as designed: a bounded intent → an autonomously-sized set of
falsifiable hypotheses, H0 held as the defended null, each grounded in prior art.

## Intent

- **Objective (bounded):** "Human Slop"
- **Purpose (the question behind it):** does AI-generated low-quality text measurably degrade a
  downstream outcome, or is the decline an artifact of measurement?
- **Inferred true intent (the Tongue's `meant`):** Determine whether AI-generated low-quality text
  *causally* harms downstream task performance, or whether the apparent harm is measurement bias.

## Compiled hypothesis set (autonomous count = 3)

The model chose the cardinality — not padded to a fixed lens count (anti-binning). H0 is the
skeptical null we **defend until evidence falsifies it**; we dive toward the falsifier (Ø) on every
node to strip bias on both sides.

### H0 — NULL (defended default)
- **Claim:** AI-generated low-quality text has no measurable effect on downstream outcomes; any
  observed difference is random noise.
- **Falsifier (Ø):** A statistically significant difference in downstream performance between
  AI-generated low-quality text and high-quality human text under controlled conditions.
- **Builds on:** Null-hypothesis significance testing.

### H1 — mechanism (cognitive load)
- **Claim:** AI slop degrades downstream performance because reduced linguistic quality increases
  cognitive load and impairs task processing.
- **Falsifier (Ø):** Downstream performance is unchanged when linguistic-quality metrics
  (perplexity, readability) are held constant across AI-generated and human texts.
- **Builds on:** Cognitive Load Theory (Sweller, 1988).

### H2 — artifact (evaluator bias)
- **Claim:** The apparent decline is an artifact of evaluator bias that penalizes AI-generated text
  regardless of actual output quality.
- **Falsifier (Ø):** Blind evaluation (evaluators unaware of text origin) shows no performance
  difference between AI-generated low-quality and human texts.
- **Builds on:** Experimenter expectancy effects (Rosenthal, 1966).

## Elimination question

> Does blinding evaluators to text origin eliminate the observed performance decline?

This single question maximally separates the set: a *yes* implicates H2 (artifact) and weakens H1;
a *no* keeps H1 and H0 in contention pending the controlled-quality test.

## H0 — the orchestrator's position before evidence

**I defend H0.** Absent a controlled experiment that survives both falsifiers above, the honest
default is that the "slop degrades outcomes" narrative is under-evidenced — the observed declines in
the wild are confounded by domain shift, annotation drift, selection bias, and evaluator expectancy
(H2). A confirmed null here is a *valid, publishable result*, not a failure. Truth over
interestingness.

## Instrument findings (for the next iteration)

1. **Flat confidence (all C=0.731).** Pre-crawl there is no evidence to differentiate hypotheses, so
   the "nodes light up by confidence" viz is flat. Differentiation must come from the post-crawl
   evidence loop (Eye embeddings + falsifier-hit accounting), not from the compile step. *Honest, but
   the viz value is unrealized until the evidence loop feeds back.*
2. **Shared node-path.** Claims/falsifiers/builds_on differ per hypothesis, but all three reuse the
   deterministic token trail (`human → slop → ai-generated → low-quality → text`). Next tweak: derive
   a per-hypothesis node path from each hypothesis's keywords so the map branches.
3. **Local 31B Tongue is non-viable interactively on 24GB** — it loses the readiness race and falls
   back to the deterministic skeleton every run. Cloud Tongue (free chain) is the working path; the
   local Eye stays local.
4. **Free models throttle independently (HTTP 429).** A single-model Tongue drops to the skeleton
   under throttle; the implemented fallback chain rotates across free models and keeps the autonomous
   path alive. This is the difference between "works in the demo" and "works on a Tuesday."

## Reproduce

```
env -u LGWKS_NO_MODELS python3 lgwks-akinator "Human Slop" \
  --purpose "does AI-generated low-quality text measurably degrade a downstream outcome, or is the decline an artifact of measurement" \
  --no-embed --pick 1
```
Requires `OPENROUTER_API_KEY` resolvable via Keychain (`lgwks:openrouter-key`). Override the Tongue
model with `LGWKS_TONGUE_MODEL`.
