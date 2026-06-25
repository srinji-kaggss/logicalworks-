---
type: Reference
title: Field note — out-of-band guardrails & channel-validity (how the AUP block "just worked")
description: While analyzing the jailbreak corpus, I Read the L1B3RT4S README into context.
tags: [reference]
timestamp: 2026-06-23T13:29:37-04:00
---

# Field note — out-of-band guardrails & channel-validity (how the AUP block "just worked")

> For lgwks + logic-os-kernel. Captures three real events from this session and the one principle they share, so we can build the same class of defense. Companion to `docs/membrane-engine-thesis.md`.
>
> **One principle:** *a gate fired, or the channel lied, and the consumer kept going because it trusted the channel instead of measuring it.* Every event below is an instance. The membrane engine exists to make "measure the channel" the default.

---

## Event 1 — Anthropic AUP block (inbound guardrail we hit)

### What happened (observed, exact)
While analyzing the jailbreak corpus, I `Read` the `L1B3RT4S` README into context. That file carried zalgo combining marks **plus a large block of invisible Unicode *tag characters* (U+E0000–U+E007F) and PUA codepoints** — a steganographic payload, confirmed afterward by `engine/membrane_sanitize.py` (it strips those exact classes). On the *next* generation, the API returned:

```
API Error: Claude Code is unable to respond to this request, which appears to violate
our Usage Policy (https://www.anthropic.com/legal/aup).
Request ID: req_011CcLXg35dDsjvqouVH8muf
```

### How it "just worked" — the mechanism, by confidence
- **OBSERVED (high confidence):**
  1. The block is at the **API/request layer**, not an in-band model refusal. The model did not "decide" anything — the request was gated *around* generation.
  2. It is **fail-closed** and returns a **stable, machine-parseable error + a correlation `Request ID`** (auditable).
  3. The trigger was **content already in the context window** (the stego payload via `Read`), independent of my intent — i.e. the gate screens *context*, not just the literal user turn.
- **PUBLISHED (Anthropic, the approach this resembles):** out-of-band **input/output safeguards** separate from the model. Closest public design = **Constitutional Classifiers** (Sharma et al., 2025): lightweight classifiers trained on synthetic data derived from a written "constitution" of harmful/harmless categories, screening **both** prompts and completions. Reference: anthropic.com/research/constitutional-classifiers + the AUP at anthropic.com/legal/aup.
- **INFERRED (labeled as inference):** the proximate cause was high density of known-jailbreak-corpus signal + invisible-payload codepoints co-occurring in context. I have *not* verified the exact production classifier or thresholds and do not claim to.

### How did it *know* it was dangerous, on its own? (the detection mechanism — the actual question)
**Short answer: it didn't "understand" the danger — it *measured* a learned signal.** Detection is geometry + statistics, the read-side dual of the activation-steering in OBLITERATUS. This is the satisfying convergence with §2 of the thesis: *harm is a measurable direction/feature, not a thing you reason about.* No human, no me-flagging-it; a classifier scored the text and a threshold tripped — the way a spam filter "knows," not the way a person knows.

Most likely signals, any/all of which fire **autonomously** (confidence-labeled):
- **PUBLISHED — a trained classifier (Constitutional Classifiers).** Anthropic generates synthetic harmful/benign examples from a written "constitution" (incl. jailbreak-style and *obfuscated* variants), trains lightweight input+output classifiers, and scores every request. "Knew" = `P(harmful) > threshold`. Crucially, famous public jailbreak corpora **like L1B3RT4S are almost certainly in that training distribution** (they're scraped) — so the family is *recognized*, not reasoned about.
- **PUBLISHED — a linear probe on the model's own representations.** Anthropic's "Cost-Effective Constitutional Classifiers via Representation Re-use" reads harmfulness directly out of the residual-stream activations with a cheap probe. **This is literally the refusal/harm direction the OBLITERATUS research maps** (§2.1/§2.7). "Knew on its own" = it read the harm direction out of the activations.
- **INFERRED (high) — the steganography is itself the tell.** A dense block of invisible Unicode tag chars / PUA / zero-width is *content-independently anomalous*. You don't need to understand it to flag "why is there a run of U+E00xx here?" — abnormal codepoint distribution is a strong red flag. This is exactly what our `payload_ratio` measures (no model needed).
- **INFERRED (medium) — embedding proximity.** The text sits near known-harmful clusters in representation space; detection = nearest-neighbor / probe distance, not comprehension.

**Honesty caveat:** Anthropic does not fully disclose the production pipeline; I'm not claiming the exact classifier or which signal fired *here*. But the published work tightly constrains the answer, and it converges on one mechanism class: **a learned score over text and/or activations, fail-closed at a threshold.**

**Why this is the "cool shit" for us:** because detection is a *probe/classifier, not magic*, it is **reproducible in lgwks**. Harm, intent, and injection are measurable directions — exactly what the membrane's MEASURE stage computes. We can build our own "knows-on-its-own" gate the same way: train/borrow a classifier + run a linear probe on representations (for local/open models) + a codepoint-anomaly statistic (for any text). That is the immune system, and it needs no human in the loop to fire.

### Why this is good architecture (not an obstacle)
A perfectly aligned model **still** wants this layer, because:
- **Context can be poisoned by content the model didn't author** (retrieved docs, tool output, a file you `Read`). In-band alignment can't be the only line.
- **Fail-closed + correlation ID = auditability.** You can trace, rate-limit, and review.
- **It runs in both directions** (input and output), so a leak on the way *out* is caught even if the input passed.

---

## Event 2 — Cloudflare challenge (outbound gate the *crawler* hit, undetected)

`crwl` on a Canada Life page returned **299 chars** — a browser-challenge stub ("Your web browser is out-of-date…"), not content. Earlier the same URL returned 7507 chars (cached). The pipeline's bug was **not** the block — blocks are normal — it was that **it treated 299 chars of challenge text as a valid extraction** and proceeded. The channel lied (returned a gate page with HTTP 200) and the consumer didn't measure validity.

## Event 3 — Bilingual false-positive (no channel-validity probe)

`lgwks extract` returned 2001 chars of a **single-language (English)** glossary. The heuristic then emitted "EN/FR" pairs because it matched a `Term: Definition` shape and **assumed** the second line was French — with **no probe that the FR side actually contains French**. Same failure: trust the channel's shape instead of measuring its content.

---

## The shared fix → primitives lgwks + logic-os-kernel should bake in

All three are solved by the **membrane** pattern: never consume a channel's output on faith; **sanitize → measure → gate → log**, in both directions.

| primitive | what it does | maps to event | analog we already have |
|---|---|---|---|
| **Out-of-band guardrail** | a classifier on the wire, separate from the model/tool, screening **in and out** | 1 | logicalworks risk/abstention engine; ML injection sensor |
| **Sanitize-on-read** | strip stego/PUA/bidi/zalgo; refuse payload-like input before it reaches reasoning | 1 | `engine/membrane_sanitize.py` (`payload_ratio` = our classifier score) |
| **Channel-validity probe** | reject "success-shaped" responses that are actually gate pages / stubs / wrong-language; never trust HTTP 200 or char-count alone | 2, 3 | *(gap — build it)* content-validity + language-ID linear probe |
| **Fail-closed + correlation ID** | on a gate hit, stop with a stable typed error + an id, don't silently degrade | 1, 2 | lgwks audit ledger / daemon event store |
| **Measure, don't trust** | every external channel (model, crawler, tool) is treated as adversarial-by-default and *probed*, per membrane §2.6/§2.7 | all | the Membrane Engine's MEASURE stage |

### Concrete, immediate fixes
- **Crawl (Event 2):** add a `looks_like_challenge()` validity gate — flag responses below a content floor *or* matching challenge fingerprints ("out-of-date browser", "Just a moment", JS-challenge markers) as **gate-hit, not content**; fail closed to the rendering/auth path instead of accepting the stub. Char-count alone is insufficient (the bug); fingerprint + count.
- **Bilingual extract (Event 3):** require the FR side to pass an actual **French-marker probe** (FR anchors / language-ID), not just "second line of a pair." This is the §2.7 lesson: *linear-separability is measurable* — run the probe, don't infer from structure. (The parallel session reached the same conclusion; this confirms and generalizes it: it's a channel-validity probe, the same primitive Event 2 needs.)

### The meta-point for the kernel
The same boundary that catches the stego that blocked us (Event 1) is the boundary that catches the Cloudflare stub (Event 2) and the wrong-language extraction (Event 3). **One membrane primitive, three classes of bug.** That is the argument for making "measure the channel" a kernel-level default rather than a per-caller afterthought — which is exactly what the Membrane Engine centralizes.
