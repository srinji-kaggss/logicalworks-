> **STATUS: historical draft (2026-06-02).** Data/ingestion authority is now
> `spec/second-harness/INGESTION-LAYER.md` + `INGESTION-PLAN.md` (v1.0, final);
> model-stack build truth is `spec/second-harness/BUILDLOG-model-stack.md`.
> Verify there before building from this file. (Banner added 2026-06-10.)

# SPEC — Tier-E Machine: the model (v1, FINALIZE)

Status: drafting (Director, 2026-06-02). Pins the **model** before the bottom-up build.
Reads with: `SPEC-lgwks-experience-v1.md` (§0 two actors, §1 flywheel), issue #27 (intent-class head),
issue #29 (honest-failure-direction, already landed `lgwks_machine.py:120`), issue #7 (Qwen3-Embedding/MLX track).

> Decision frame already set by Director:
> - End state = the **Tier-E Machine**; build top-down to spec, then bottom-up to implement.
> - Embeddings = **owned encoder** (train it, don't rent it). Vendor-agnostic, on-device.
> - Size is **not** a constraint — if 110M runs comfortably on the Mac, use 110M.
> - Domain-biased distillation toward two clusters + a general remainder (§2).
> - Bootstrap corpus = AI-seed + deterministic-augment + **self-learning from its own coverage-gap fuck-ups** ("deeply curious").

---

## §0 · What the model IS (one sentence)

A **discriminative encoder** (BERT-class, ~110M) that hooks raw human input *pre-LLM* and emits, in one
forward pass, four typed signals — **intent-class · entity-link · gap-detect · specificity-score** — never
prose; abstains-and-self-diagnoses when uncertain; **owned weights**, domain-biased, on-device (CoreML/ANE).

It is **not AI** (`SPEC-experience` §0): it scores and shapes, it does not speak. The AI (Tier-G) is its teacher.

## §1 · Architecture — one trunk, four heads, two steering rails

```
                      raw input string
                            │
            ┌───────────────▼────────────────┐
            │  TRUNK: domain-biased encoder   │  ~110M, 12 layers, d=768
            │  (owned weights, §3 distill)    │  tokenizer: WordPiece/BPE, English-first
            └───────────────┬────────────────┘
        pooled [CLS]  +  per-token hidden states
                            │
   ┌────────┬─────────┬──────────┬───────────┬──────────┬─────────┐
   ▼        ▼         ▼          ▼           ▼          ▼         ▼
 H1 intent H2 entity H3 gap    H4 specif.  H5 reason  (probes)
 -class    -link     -detect   regression  -mode      linear probes on
 softmax   tok-cls+  multi-lbl [0,1]+calib multi-lbl  mid-layer activations
 over N    linker    per slot  (temp)      (§2 reason)→ steering axes (§4)
 verbs
```

> //why H5 + a SHARED trunk: reasoning is baked into the trunk weights via auxiliary objectives (§2.reason);
> H5 is the one deployed reasoning head — it lets the membrane route by inference type and keeps the trunk's
> reasoning structure inspectable (§4 probes). The reasoning CAPABILITY lives in the weights, not in H5 alone.

- **H1 intent-class** = issue #27. Labels = live manifest verbs (`lgwks manifest --json` IS the label schema).
  Catch-all `unknown` class → `[PLAN_ONLY]` gate. Today: keyword stub (`lgwks_intent_classifier.py:182`). This head replaces it.
- **H2 entity-link** = token classification (NER) + link to known lgwks entities (repos, files, providers, people).
- **H3 gap-detect** = multi-label over the slot vocabulary already in `lgwks_machine.py:_questions` (timeframe, target, concern…).
- **H4 specificity** = scalar regression in [0,1], temperature-calibrated; feeds the abstain gate (`lgwks_machine.py:119`).
- All four share the trunk → one forward pass, sub-2ms target on ANE. Heads are cheap linear/shallow.

//why one trunk not four models: the four signals are correlated (a specific, well-entitied input is rarely a
// gap); a shared representation is smaller, faster, and lets the flywheel improve all heads from one corpus.

## §2 · The distillation — what "custom distill" means here

Since **size is not a constraint**, we do NOT distill for compression. "Distill" = **bias the representation**
toward the Director's domains, via two distillations stacked (the thesis of `SPEC-experience` §1):

1. **Domain-adaptive pretraining (DAPT)** — continue masked-LM on a **domain-mixed corpus** (ratio below) on
   top of a strong general base. This is the "bias it toward" step: it moves the encoder's manifold toward
   psychology/intent/linguistics/philosophy AND math/STEM, so both circuits exist and can be composed (ActAdd thesis, §4).
2. **Behavior distillation (the flywheel)** — the **AI (Tier-G) is teacher**, the Machine is student. AI
   refinement traces in the cognition-log (`lgwks_cognition.py`) become soft targets; the Machine learns to
   imitate the AI's intent-shaping. Gets cheaper + more personalized with use. Champion/challenger governed (ADR-003 §D3).

### Domain mix (Director's ratio — DAPT corpus)

FINALIZED ratio (Director's weights, normalized to reserve a general floor):

| Bucket | Share | Sources (vendor-agnostic / open) |
|---|---|---|
| Math | 21% | arXiv math, proof corpora, OpenStax math |
| Other STEM | 21% | arXiv cs/physics/bio, OpenStax STEM, STEM Wikipedia |
| Psychology | 14% | PsyArXiv abstracts, open psychology texts |
| Linguistics | 11% | ACL Anthology, linguistics corpora |
| Philosophy | 7% | Stanford Encyclopedia, PhilPapers, Gutenberg philosophy |
| **General** | **26%** | broad English (Wikipedia general, C4/OpenWebText subset) |

STEM-dominant (~42%), human-meaning ~32% (psych-led: intent-understanding is the core job), general floored at 26%.

> //why a 26% general floor (the ONE change from the Director's raw numbers, which summed to 105% → 0 general):
> a zero-general DAPT catastrophically forgets everyday English; the Machine must parse arbitrary NOISY human
> intent, not only domain text. ~74/26 domain/general is a deliberate shift from the earlier 50/50 — intentional.
> Treat the ratio as a tunable hyperparameter; re-weight once coverage-gap data shows where the Machine is weak.

### Base / trunk — FINALIZED: DeBERTa-v3-base

| Option | Trunk | Why | Cost |
|---|---|---|---|
| **✅ DeBERTa-v3-base** | ~86M+emb (~110M class) | SOTA encoder NLU, disentangled attention → strong intent/specificity | MPS fine-tune OK |
| BERT-base-uncased | 110M | low-risk fallback if DeBERTa's disentangled attention is painful to export to ANE | cheapest |
| Qwen3-Embedding (MLX) | varies | issue #7 track; MRL embeddings — kept for the embedding-substrate repoint, not the trunk | MLX path |

**Trunk = DeBERTa-v3-base.** First bottom-up unit includes a CoreML/ANE export spike; if disentangled
attention won't export cleanly under the <2ms bar, fall back to BERT-base (same domain corpus, same heads).

**Size growth path: start 110M, let it grow naturally.** Base now; promote to DeBERTa-v3-large (~350M class)
later ONLY if (a) the accuracy/coverage ceiling demands it AND (b) it still exports to ANE and stays interactive.
Growth is evidence-gated by the champion/challenger gate (§6 ACC-4), not pre-committed.

### §2.reason · Philosophy/reasoning baked INTO the weights (Director, 2026-06-02)

> Distinction (anti-binning): philosophy-as-*topic* (the 7% corpus bucket) gives the trunk philosophical
> *vocabulary*. It does NOT teach it to *reason*. Reasoning is a **capability**, baked via *objectives*, not text %.

Reasoning enters the **shared trunk weights** three ways, all training-time:

1. **Auxiliary pretraining objectives** (the actual bake-in). Multi-task heads trained on the trunk; their
   gradients shape shared weights; **dropped at deploy** (structure persists in the trunk all deploy-heads read):
   - **NLI/entailment** — premise → {entail, contradict, neutral}. Bakes logical-relation structure.
     DeBERTa-v3 is SOTA at NLI → the §2 trunk choice directly pays off here.
   - **Argument structure** — token-tag {premise · claim · assumption · conclusion}. Bakes premise→conclusion shape.
   - **Reasoning-type** — {deductive · inductive · abductive · causal · analogical · normative/ethical}. Bakes inference *kind*. (= deployed H5.)
   - **Lens-axis contrastive** — philosophy-framed ↔ science-framed contrast pairs train `lgwks_steering`'s lens
     (line 6, philosophy↔science) as a **learned direction in the weights**, not just an inference-time ActAdd vector (§4).
2. **Reasoning-dense corpus** woven through existing buckets (no new %): proofs/worked-solutions (STEM),
   SEP/PhilPapers argument articles (philosophy), Socratic/debate + argument-mining corpora, NLI sets (SNLI/MNLI/ANLI).
3. **Reasoning-trace distillation** (flywheel, reasoning-specific): cognition-log `thought`/`intent_commit`/`alignment`
   entries (`lgwks_cognition.py`) ARE the reasoning-trace corpus; the AI teacher's "why" → soft targets distilled into the student.

//why drop the aux heads at deploy: they shape the trunk during training but cost inference; H5 is the one kept
// (cheap, routable, inspectable). The trunk stays <2ms because reasoning lives in its weights, not in runtime heads.

## §3 · Training pipeline (owned, replayable, on-Mac)

```
manifest verbs ──┐
                 ├─► (R1) bootstrap corpus ──► H1 cold-start train ──► first usable Machine
AI-seed paraphrase┤        (§5 corpus gen)         (MPS fine-tune)         (ships behind PLAN_ONLY gate)
det. augment ─────┘                                                              │
                                                                                 ▼
DAPT domain corpus ──► continue-MLM + AUX reasoning objs (§2.reason) on trunk ──► mount H2/H3/H4/H5 ──► multi-task FT
                       (NLI · arg-structure · reasoning-type · lens-contrastive — drop aux at deploy)
                                                                                 │
cognition-log traces ──► behavior-distill (flywheel) ──► champion/challenger promote ──► CoreML/ANE export
        ▲                                                                        │
        └──────────────── active-learning: coverage-gap fuck-ups feed back ──────┘  (§5 self-learning)
```

- All training: **PyTorch + MPS** (Apple Silicon). Export: safetensors → **CoreML** via `coremltools`.
- Toolchain currently **absent** (numpy only) — install `torch transformers datasets coremltools` is the first bottom-up unit (L2).
- `tools/train_intent_classifier.py` is a stub (`train()` has no Trainer loop, `_export_coreml` is a placeholder) — it becomes the real pipeline.

## §4 · Steering & interpretability (ActAdd folded in — honest scope)

ActAdd (arXiv 2308.10248v5) is a **generative-decoder inference technique**; it is NOT our distillation core.
What transfers to our **encoder**:

- **Steering axes = contrast-pair directions.** `lgwks_steering`'s dials — frontierness, **lens (philosophy↔science)**,
  depth — become directions in the trunk's mid-layer activation space, computed from contrast pairs (ActAdd Alg.1).
  The Director's domain bias (human-meaning ↔ math/STEM) IS the lens axis. The thesis (paper intro): a model can
  hold both circuits even when they never co-occurred in training, and compose them in activation space — prompting can't.
- **Interpretability = linear probes on activations** (ITI-style, cited in the paper). Probes on mid-layers make
  the Machine "interpretable via attention + calibration" (`SPEC-experience` §0): we can read *why* a class fired.
- **Calibration** = temperature scaling on H1/H4 so confidence is honest → the abstain gate (#29) trusts it.

//why fold not core: ActAdd does not change weights and is decoder-oriented; for a discriminative encoder its
// value is the steering-vector + probe machinery for interpretability/dials, not for training the trunk.

## §5 · Bootstrap corpus + self-learning ("deeply curious") — the root unblock (R1)

The flywheel cannot distill from traces that don't exist (cold-start). R1 seeds H1:

1. **AI-seed** — Tier-G AI expands each manifest verb intent into N diverse paraphrases (on-thesis: teacher seeds student day 1).
2. **Deterministic augment** — synonym/verb-phrasing/slot-fill + casing/filler/typo multiplication over the seeds (owned, offline, high volume).
3. **Self-learning (active loop)** — `_log_coverage_gap` (`lgwks_machine.py:153`) already harvests real misclassifications.
   Uncertainty-sample the inputs the Machine is least confident on → label (AI or human) → fold back as **hard negatives**.
   "Deeply curious" = the Machine prioritizes its own fuck-ups for the next retrain.

Quality gate on the corpus: dedup, per-class balance, holdout split; reject paraphrases that collapse class boundaries.

## §6 · Invariants + acceptance (the production bar)

- **INV-1 owned weights**: no vendor API in the inference path; trunk weights live in-repo (`*.mlpackage`), reproducible from `tools/`.
- **INV-2 honest failure**: `unknown`/low-confidence → `[PLAN_ONLY]`, never a fabricated "please specify" (preserves #29's fix).
- **INV-3 manifest = labels**: new verb → dataset rebuild → retrain → deploy, fully automated (issue #27 acceptance).
- **INV-4 calibration**: H1/H4 confidences temperature-calibrated; ECE measured on holdout.
- **ACC-1**: H1 >90% top-1 on held-out manifest examples (#27). **ACC-2**: inference <2ms on M-series ANE.
- **ACC-3**: `refine` on #29's smoking-gun prompt proceeds/self-diagnoses, never blames the human (regression test).
- **ACC-5 (reasoning baked in — capability probe)**: trunk frozen + a linear probe (no fine-tune) scores **≥0.85**
  on held-out MNLI → proves logical-relation structure lives in the WEIGHTS, not a runtime head.
  //why 0.85 not 0.95/0.35: 3-way chance=0.33 → 0.35≈noise (would ground on garbage, the #29 disease);
  // 0.95 > SOTA for a 110M encoder on adversarial NLI (ANLI ~50-60%) → an unfalsifiable bar; 0.85 is reachable
  // (DeBERTa-v3-base MNLI ~90%) with margin. Report ANLI too as the hard-case honesty check.
- **ACC-6 (NLI as runtime grounding — minimal-reference)**: entailment is the sufficiency test for mapping the
  SMALLEST code-graph node-set that entails the answer (= token reduction). This is NOT an accuracy target — it is a
  **calibrated operating point under asymmetric cost**: bound **false-support-rate < ε (~1-2%)** (grounding on a
  non-supporting snippet = fabrication, catastrophic), maximize recall/minimality subject to that, and REPORT the
  token savings + the PR curve. Entailment runs over NL summaries of graph nodes, never raw code (NLI is NL-trained).
  //why an operating point not a constant: higher threshold → less minimal (over-fetch, loses the token win);
  // lower → insufficient context (fabrication). Sweep the PR curve, pick where false-support<ε. Ties to the
  // code-knowledge-graph token-reduction pattern (Greptile / "120x") — NLI is what makes their retrieval sound.
- **ACC-4**: champion promoted only past frozen snapshot + calibration (champion/challenger, ADR-003 §D3).

## §7 · After the model: bottom-up build order

R1 corpus gen → L2 toolchain + real train/export loop → L1 trunk (DAPT + H1, then mount H2/H3/H4 + repoint
`lgwks_embed` to the trunk's pooled output, killing the feature-hash) → L0 flywheel distillation + champion/challenger.

Each becomes a dependency-ordered GitHub issue; #27 reopens as the H1 unit.

---

*Open confirms for the Director:* (a) A:B inner ratio (even 25/25, or weight human-meaning heavier?);
(b) trunk pick (DeBERTa-v3-base recommended vs BERT-base safe vs Qwen3/MLX per issue #7);
(c) is 110M the ceiling, or is a larger trunk acceptable if it still runs comfortably + exports to ANE?
