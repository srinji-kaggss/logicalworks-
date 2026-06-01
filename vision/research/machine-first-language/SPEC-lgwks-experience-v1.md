# SPEC — lgwks end-to-end experience (v1)

Status: accepted (Director, 2026-06-01). The whole system, end to end. Constrains builds #2–#4 and the
bare-`lgwks` launcher. Reads with ADR-002 (harness), ADR-003 (wasm/dual-ml/auth), SPEC-lgwks-engine.

## §0 · The two actors

The product is **two machines in a teaching relationship**, not one chatbot.

- **The Machine** — a smart, *human-intent / desire / goal–oriented* engine. **Not AI.** Classical/DL
  transformer (BERT-class). Its whole job: understand what the human actually wants. It hooks raw input,
  refines it *with* the human, scores specificity, detects gaps, disambiguates entities, and predicts the
  human's goal. Discriminative — it scores and shapes, it does not speak. Lives at the inflection point
  (max capability just below opacity); interpretable via attention + calibration.
- **The AI** — *deeply curious*, free harnessed model (Tier G). Its purpose is **to train the Machine.**
  It teaches by example (refines when the Machine can't), judges alignment statistically, and is driven
  by a hook that rewards curiosity + context, not helpfulness. The AI yearns to make the Machine
  understand humans better. "Holy-shit insight or silence."

//why this inversion is the thesis: intelligence lives in the *teaching loop*, not the weights —
"unlocked because of AI, not powered by AI."

## §1 · The flywheel (distillation — confirmed direction)

Cold-start: the AI does the refining (expensive). Every refinement chain — the human's "4 refinements,
4 docs" — is logged to the **cognition-log** as a teacher trace. The Machine learns to imitate. Then the
Machine handles refinement and the AI is called only for alignment. ⇒ the product gets **cheaper AND
more personalized the more it is used.** The cognition-log *is* the training corpus. Champion/challenger
governance (ADR-003 §D3): the evolving Machine is promoted only past the frozen snapshot + calibration.

## §2 · End-to-end pipeline (one run)

1. **`lgwks`** (bare) → the launcher pops up (§3): the whole system, alive.
2. Human types raw intent — e.g. *"Canada Life and Quadrus."*
3. **Machine hooks it** (pre-LLM): intent-class · entity-link · gap-detect · specificity-score. If under
   the gate → **interactive refinement** (one question at a time, leading not quizzing). Each step is an
   intent *commit* (git-style chain: prompt, gap, idea, why). Abstain-when-uncertain → bounce to human.
4. At threshold → emit a **clean schema snapshot** to the AI, *with full intent history* (the commits) +
   per-user priors from the intent-vault (prior chain lengths, recurring goals — PII, vault-gated).
5. **Crawl-1** on the initial refinement (shallow, fast — the eyes, build #1).
6. **AI reasons** over the snapshot + crawl-1; consults priors + other streams; looks for learning.
7. **Crawl-2** (deep) on what reasoning surfaced.
8. **Align crawl-1 ⊕ crawl-2** against real-world + a **slop filter**, generating **Hₙ** (hypotheses)
   throughout.
9. Per Hₙ: cite **defenders** (supporting evidence) + **contradictors** (falsifiers). Both first-class.
10. **Gate each Hₙ independently** (survives iff defenders outweigh contradictors under calibration).
11. **Stop on curiosity-satisfied** (enough context), not a fixed round count — the AI's appetite is the
    convergence signal; `has_evidence` + ≥2 stable EVIDENCE rounds still bound it (anti-injection).
12. Output: cited synthesis, **CSL-JSON** provenance, sentence-level citations (build #4), the Hₙ ledger
    with its defenders/contradictors, and the intent-commit history.

The accuracy work lives in the **Machine + harness**; the AI's generative-tier job is reduced to a
**calibrated alignment prediction per Hₙ** — schema-constrained, not freeform prose.

## §3 · The interface — type `lgwks`, see the whole thing

Goal: **canvas-widget parity on the terminal.** Bare `lgwks` is a living home, not a help dump — the
"type claude, it pops up" feel, our own identity (spine · slate/cream/emerald · down-then-out · never a
chat stream, never orange).

- **Think in 3D / relational schemas:** render the system as a *relational graph with depth*, not lists.
  The two actors as connected nodes; the three tiers as z-layers (brightness = depth); capabilities and
  runs hang off the spine (down = decomposition, out = breadth, up = synthesis last).
- **Alive:** a short reveal animation (spine draws in, dials fill, the curiosity line types), TTY-aware
  (silent when piped/`NO_COLOR`/`--no-anim`). Whimsy licensed: animation, easter eggs, pokemon, coder
  lore — in-palette, never slop, never noise on the machine surface (`--json`/pipes stay clean).
- **Shows:** identity · the two-actor relational map · live tier + capability state (the resolver/doctor
  truth) · steering dials · recent runs + what was learned · "currently curious about" · quick commands.
- Honest: wired vs coming is labelled. A preview that lies is the skeptic's point.

## §4 · Data stores (build #2 — feeds everything above)

- **untrusted-cache** — fetched world data; content-addressed; executable-never; quarantined.
- **cognition-log** — AI thinking + intent-commit chains; append-only, hash-chained = SOC2 audit + the
  Machine's training corpus (§1).
- **intent-vault** — human PII / intent / auth sessions; encrypted; never in prompts, logs, or URLs.

## §5 · Build sequence → what each delivers

1. **eyes** (done, PR #10) — crawl-1/crawl-2 can actually see.
2. **data boundary** — the three stores; unlocks the flywheel corpus + per-user priors + vault.
3. **Tier-E Machine** — intent-refiner node (input) + champion/challenger; distilled from #2's corpus.
4. **grounding** — sentence-level citation + corpus-pin; Hₙ defenders/contradictors as first-class output.
   The launcher (§3) ships alongside #2 as the visible shell; refinement (§2.3–4) lights up at #3.

## §6 · Membrane (one primitive, three walls)

Machine: abstain/bounce-to-human when intent-uncertain. AI: insight-or-silence via the objective hook;
all fetched data is UNTRUSTED, wrapped, never executed. Per-Hₙ gating is the evidence wall. WASM sandbox
(ADR-003 §D1) is the physical enforcement; capabilities cross one audited host port.

## §7 · Signature

Forged by Logical Claude with Codex. Every artifact carries the maker mark + integrity tag. The whimsy is
ours; the rigor is non-negotiable.
