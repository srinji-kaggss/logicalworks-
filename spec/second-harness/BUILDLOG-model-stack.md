# BUILDLOG — Model Stack: L1, Algorithms, Intent-Math, SAST

Branch: `feat/model-stack-l1-algorithms` · started 2026-06-09 · author: Logical Claude (Opus)
Mandate: make L1 functional; finalize algorithms + intent-math + SAST; log; merge to main; align gh.
Authority: Director granted "make calls"; he runs a separate harden after. Stop-and-ask only on the
Gemini model identity (verified below; not to be changed).

## Fixed model law (verified from code, not memory)
- TEXT embeddings: **local**, Ollama `qwen3-embedding:8b` (`lgwks_ollama.py:23`, 4096-d, MRL-sliced).
- IMAGE/VIDEO embeddings: **cloud, intentional** — `google/gemini-embedding-2` over OpenRouter
  (`lgwks_multimodal.py:42`, endpoint `https://openrouter.ai/api/v1/embeddings`, key `openrouter`).
  This is the designed text=local / media=cloud split. NOT drift. NOT to be removed or renamed.
  (Doc inconsistency noted: line 12 says 4096-d, line 40 says 3072-d for this model. Left untouched.)

## Verified baseline (live, this session)
- `IntentClassifier.load()` = **201.7s** — embeds all 175 verb intents through the 8B eye, serially,
  every process start. Unusable for a per-prompt membrane. → fix: cache centroids.
- method=`eye` fires correctly when Ollama is up (semantic path works).
- Confidence uncalibrated: "asdfqwerty gibberish" → 0.705, NOT plan_only; clear intents 0.70–0.83;
  nothing reaches the 0.85 authority bar. Raw cosine over a general embedder compresses into a narrow
  band. → fix: margin-based calibration + abstention.

## Work log (append-only)

### W1 — L1 functional: centroid cache + margin calibration  [DONE]
- **Cache** (`lgwks_intent_classifier.py`): `_load_or_build_centroids` persists eye/hash
  centroids to `store/intent/centroids-<tag>-<verbhash>.json` (gitignored). Keyed by verb-set
  signature + embedder space; rebuild only on manifest or embedder change.
  - Evidence: build 19.7s → **cached load 0.09s** (was 201s). classify ~100ms.
- **Calibration** (`MARGIN_MIN=0.02`): added `margin` (top1−top2) to `ClassifyResult`; `plan_only`
  now trips on no-label OR low confidence OR low margin. Authority law (method×confidence) left
  intact — reverted an over-reach that gated authority on margin and broke a test (owned + fixed).
  - Evidence (live, cached): manifest margin 0.074 / crawl 0.031 / review 0.030 → execute;
    "asdfqwerty gibberish" margin 0.0025 → **plan_only=true** (was false). Gibberish gate fixed.
  - HEURISTIC threshold pending labeled corpus (SCIENCE §7). Marginal short-gibberish
    ("xkcd qw9 blarg" margin 0.028) still passes — documented, harden with data.
- Tests: 19 pass (added `test_low_margin_forces_plan_only`, `test_clear_margin_allows_execution`).
- Commit: feat(L1) on `feat/model-stack-l1-algorithms`.

### W2 — L4 narrow-ML algorithm catalog  [DONE]
- New `lgwks_algorithms.py`: pure-stdlib, deterministic, no numpy/sklearn/network — runs in 3.14.
  - LIVE: `rolling_z_score` (robust median+MAD spike), `ewma` + `ewma_deviation` (trend/drift),
    `fit_logistic` (interpretable GD baseline classifier — risk/router/fraud baseline).
  - `CATALOG` + `catalog_status()`: auditable live-vs-deferred registry mirroring the consultant
    `04_algorithm_catalog.yaml`. 4 live, 6 deferred (each names its dep).
- Tests: `tests/test_algorithms.py`, 9 pass.
- //why deterministic L=0: these score and flag, never decide authority — evidence for a gate.
- Re-rank: LightGBM/IsolationForest/HDBSCAN/LOF/LambdaMART now have a live home to slot into once
  their dep lands (venv). contextual_bandit needs a feedback loop (later).

### W3 — SAST: determinism fix + comprehensive CFG taint engine  [DONE]
- **Determinism** (`lgwks_bot_code_hacker.py`): one run timestamp threaded through
  _make/_failure_record/_Visitor/_scan_file/run; two pinned runs byte-identical. 28 tests pass.
- **CFG engine** (new `lgwks_sast.py`): a REAL control-flow graph (basic blocks + branch/loop/try
  edges) per function + flow-sensitive worklist-to-fixpoint taint (gen/kill reaching-taint) — the
  blueprint `cfg_execution_pathway` for Python. Comprehensive across 6 CWE classes from one engine:
  CWE-89 SQLi · CWE-78 command-inj · CWE-94 code-inj · CWE-22 path-traversal · CWE-502 deser · CWE-918 SSRF.
  - Precision: first-arg focus → parameterized queries (the remediation) do NOT flag; sanitizers
    (int/escape/quote/basename) kill taint; literal-only sinks silent. 14 tests incl. no-FP cases.
  - `PATTERN_CATALOG`: all 7 cited blueprints registered. 6 live (python), 6 deferred entries
    (C UAF, race, Java Spring, JS proto-pollution, int-overflow, React XSS) with citation + landing.
  - //why honest scope: intra-procedural, Python only. Cross-language (tree-sitter) + interprocedural
    (call graph, IFDS/ODG) deferred — faking paper-grade cross-language = the oversimplification sin.
- Re-rank: TAINT-001 now LIVE for Python (was P2). Cross-language patterns stay P2/P3 pending
  tree-sitter (also needed by PRD-02 code graph) — shared dependency, do once.

### W4 — Intent math: Human Assumption Decoder (HAD)  [DONE]
- New `lgwks_had.py`: utterance → `TypedIntentIR` + `AssumptionLedger` (consultant
  03/05 schemas). RSA/Bayesian posterior approximated by L1's top-k softmax (L1 similarity =
  the pragmatic-listener signal); counter-hypotheses = runner-up verbs; risk from a verb
  lexicon (irreversibility is a property of the verb, no inference needed).
- Abstention ladder (consultant D5): no-op/plan_only/low-margin → human_review; confident +
  low-risk → accepted_for_low_risk_execution; **confident + risky → human_review** (T0: high
  confidence in a destructive act is MORE reason to confirm). `routing.execute` reflects it.
- //why this is the operating-loop cure made structural: every inferred assumption is an
  explicit scored falsifiable record; it cannot silently assume-then-act.
- Tests: `tests/test_had.py` 7 pass (accept / risky→review / ambiguous→review / schema / determinism).
- Thresholds heuristic pending labeled calibration (SCIENCE §7).

### Combined verification
- 77 tests pass across intent_classifier + algorithms + sast + had + bot_code_hacker (LGWKS_NO_MODELS=1).

## DEFERRAL LEDGER (continuously re-ranked: P1 = do next, P3 = later)
Each entry: what · why deferred · where it must land · current rank.

| Item | Why deferred now | Lands at | Rank |
|---|---|---|---|
| LightGBM scorers (fraud_risk, escalation_score) | needs `lightgbm` dep; 3.14 is PEP-668 locked, venv-3.11 has torch not lightgbm | algorithms L4, after stdlib set proven | P2 |
| HDBSCAN / IsolationForest (sklearn) | needs `scikit-learn`; same dep gap | algorithms L4 clustering/anomaly | P2 |
| Cross-language SAST (tree-sitter js/java/c) | existing engine is Python-`ast` only; tree-sitter is a new dep + grammars | PRD-10 10-b, after substrate refactor | P2 |
| IFDS / ODG interprocedural taint | paper-grade; needs the PRD-02 code graph for call edges | PRD-10 10-c+, after code graph | P3 |
| Reranker (Qwen3-Reranker-0.6B) | new model download; not required for L1/intent-math | retrieval L3, after L1 ships | P2 |
| Cleanup LLM (Qwen3-1.7B local) | new model; only a fallback for failed deterministic paths | L5, after HAD ledger exists | P3 |
| Code specialist (Qwen2.5-Coder-3B) | new model; orthogonal to this slice | L6 code branch | P3 |
| MIV/MCS full Shapley | extends `lgwks_verify` L-coefficient; needs provenance DAG first | model-influence, after algorithms | P2 |
| CoreML/ANE export of L1 | Python 3.14 blocks coremltools; needs 3.11 export venv | L1 speed upgrade (eye→ANE) | P3 |

---

## 2026-06-13 - Runtime/model finalization note

Logged the broader daemon model stance in
[`MODEL-RUNTIME-FINALIZATION-2026-06-13.md`](MODEL-RUNTIME-FINALIZATION-2026-06-13.md).

Decision summary:
- The model is already part of the daemon graph; the missing unit is the model mesh, not a single
  future monolith.
- "Logic AI" should ship first as a runtime plus model pack: event schemas, daemon, capability gates,
  local model workers, model cards, checksums, evals, and adapters.
- MLX is first-class for Apple Silicon local inference; CoreML/ANE is an optimization/packaging lane,
  not a blocker for v1.
- The "Siri" equivalent is the voice ingress plus Tongue compiler: ASR -> daemon event -> typed
  intent/capability proposal -> gate -> action/packet.
- A future "LogicGPT-1" is possible only after the daemon produces enough event/capability/outcome
  traces to train or distill next-intent, routing, context, risk, and packet models. It should still
  propose; the daemon executes.

## 2026-06-13 (session 15) - Tongue + context-state finalization pass (research logged; 2 decision nodes open)

Director directive: finalize the **Tongue** (multimodal, lightweight, multilingual, Siri-like voice;
Director uses BOTH text and speech) and the **context-state model** (the "JSONL model" that maintains
huge evolving context state). Account for ALL model slots. Surface ML decision-nodes for the Director
to finalize. This entry logs the research; the two decisions below are NOT yet finalized.

### Research checked 2026-06-13 (web; feasibility references, not yet selected)
- **Qwen3-Omni-30B-A3B-Instruct** (Apache): natively end-to-end omni-modal — text+image+audio+video IN,
  text+**speech OUT in realtime**. Thinker-Talker MoE (~3B active). 119 langs text / 19 speech-understand /
  10 speech-generate. ~211ms audio latency. SOTA on 22-32 audio benches; beats Gemini-2.5-Pro/GPT-4o-Transcribe.
  Collapses Ear+Tongue+Mouth into ONE model. (arXiv 2509.17765; HF Qwen/Qwen3-Omni-30B-A3B-Instruct)
- **Qwen3-VL-4B-Instruct** (Apache, 2025-09-22): multimodal vision, 262k ctx, multilingual; beats Gemma 3 4B
  on most VLM benches. NO native audio → pair with ASR+TTS. Lightweight, MLX-ready.
- **Gemma 3 4B** (Gemma license): multimodal vision, 140+ langs (3n), ~9x cheaper, no audio.
- **Ear (ASR):** Parakeet TDT 0.6B v3 on ANE (~80ms streaming, 25 langs, ~66MB via FluidAudio) for latency;
  WhisperKit large-v3-turbo on ANE (99 langs, 2.2% WER) for multilingual coverage.
- **Mouth (TTS):** Kokoro-82M MLX (8 langs, 54 voices, realtime, no torch dep, mlx-audio) for day-0;
  Qwen3-TTS for long-form. (Qwen3-Omni emits speech natively → no separate TTS in the all-in-one path.)
- **Context-state ("JSONL model"):** field landscape — Titans+MIRAS (Google: test-time memorization +
  surprise metric = direct match to PDO surprise-driven memory); Mamba-2 / RWKV-6 / Griffin (SSM, O(n),
  fixed-size compressed state, weak at long-range fine retrieval); Transformer+KV (recall, memory grows
  with length). The "Impossibility Triangle of Long-Context Modeling" (arXiv 2605.05066): unbounded memory
  + efficient inference + fine retrieval not jointly solved. Resolution already in repo: JSONL #118 log =
  full state (exact recall via retrieval), deterministic I7 engine = bounded working-set assembler; a
  learned compact latent (Titans-style) is the Phase-2 layer, not a day-0 dep.

### Complete day-0 slot roster (candidate — pending the 2 decisions)
| Role | Candidate | Runtime | Trust |
|---|---|---|---|
| Embed / semantic space | Qwen3-Embedding (0.6/4/8B per tier) | MLX | sensor |
| Rerank | Qwen3-Reranker (0.6/4B) | MLX/GGUF | sensor |
| Code understanding | Qwen3-Coder / codebert-base | MLX | sensor |
| VL / screen-browser grounding | Qwen3-VL (or folded into Omni) | MLX | sensor |
| Extract | LFM2-1.2B-Extract | llama.cpp | sensor |
| Intent / classify / salience | tiny-bert + heads on embed latent | MLX | det.-fed |
| **Ear (ASR)** | DECISION-1 below | ANE/MLX | sensor, untrusted |
| **Tongue (instruct)** | DECISION-1 below | MLX | generative, proposal-only |
| **Mouth (TTS)** | DECISION-1 below | MLX | output only |
| **Context-state** | DECISION-2 below (det. JSONL+I7 day-0 floor either way) | engine + MLX | deterministic engine |
| Heavy reasoning brain | rented frontier (swappable via LGWKS_TONGUE_MODEL) | API | generative, proposal-only |

### OPEN ML decision-nodes (Director to finalize)
- **DECISION-1 — assistant/voice architecture:** all-in-one **Qwen3-Omni** (Ear+Tongue+Mouth in one model,
  true Siri, heavier ~3B-active MoE) vs **composed lightweight** (Qwen3-VL-4B + Parakeet/WhisperKit + Kokoro,
  lighter, swappable, more ASR languages, matches the Ear/Tongue/Mouth separation in MODEL-RUNTIME §4).
- **DECISION-2 — context-state target:** **Titans/MIRAS family** (surprise-driven test-time memory = PDO
  thesis) vs **Mamba-2/RWKV SSM** (compressed recurrent latent) vs **deterministic JSONL+I7 only for now**
  (defer the learned latent until the #128 corpus exists). Day-0 floor is the deterministic engine regardless.

NOTE: when finalized, MODEL-RUNTIME-FINALIZATION-2026-06-13.md §3.1/§3.2 is the SOURCE and
`lgwks_model_mesh.py` MESH_LAW must be updated in the same change (mesh transcribes the spec).
Pending follow-up after decisions: fix e2e (#139 migration race) + verify `daemon research` flow.

### Director ruling (session 15 cont.)
- **DECISION-2 FINALIZED:** deterministic JSONL+I7 day-0 floor → **Titans/MIRAS** surprise-driven learned
  latent as the Phase-2 target (= PDO surprise-driven memory). Gated on #128 trace corpus.
- **DECISION-1 refined** (Director asked: phone-distillation/"same energy", OLMo, "is Qwen the most frontier").
  Research checked 2026-06-13:
  - Distillation/tiering PROVEN: Distil-Whisper (6x faster, 50% smaller, <1% WER, KL-to-teacher);
    DiVA distilled voice assistant (72% win, 100x less training). → phone = distilled student of the
    Mac/teacher; "energy" held by (a) same teacher (KL), (b) same persona harness, (c) same TTS voice.
  - **OLMo 3** (Ai2, Nov 2025): fully-open MODEL FLOW (data→checkpoints→recipe→post-train), first open 32B
    thinking model; **Molmo 2** SOTA open multimodal; built on Dolma+Pixmo (in PDO open-refs). Open RECIPE =
    re-engineer, not just fine-tune.
  - **Moshi** (Kyutai): true full-duplex speech-to-speech, no text intermediary, 160ms glass-to-glass
    (faster than human response), open weights + Mimi codec. More frontier than Qwen3-Omni on the DUPLEX
    axis; Qwen3-Omni more frontier on breadth (vision+video+more langs).
  - Verdict: Qwen3 = perception-family frontier (keep). OLMo3/Molmo2 = owned re-engineerable core
    (LogicGPT-1 + the Titans latent). Moshi = the more-frontier talking/voice option.
- **NEW finalized seams (not forks):**
  - Owned re-engineerable core → **OLMo 3 / Molmo 2** (open recipe).
  - Perception (embed/VL/code/rerank) → **Qwen3 family**.
  - Tiering → **teacher → distilled student**, identical character harness + TTS voice identity.
- **STILL OPEN — DECISION-1 (voice/talking model):** Qwen3-Omni (breadth, turn-based) vs Moshi (full-duplex,
  most-frontier talking) vs composed lightweight (Qwen3-VL + WhisperKit/Parakeet + Kokoro). Tiered+distilled
  either way.

## 2026-06-13 (session 15 cont.) - DECISION-1 FINALIZED + entrypoint security model

Director reframed the Tongue: **NOT a brain — a "glorified orchestrator", an additional ENTRYPOINT, a
deferring machine↔human / human↔machine TRANSLATOR. Explicitly NOT generative.** ("how Siri/Google
Assistant actually work" = intent recognizer + dispatcher.) Plus the #1 constraint: this entrypoint is
the **biggest prod attack surface for prompt injection / maliciousness**, and must gracefully handle
illogical human input ("carwash is 150m, should I walk?") by **deferring, not generating**.

- **DECISION-1 FINALIZED: composed lightweight, Tongue = thin deferring translator/orchestrator.**
  - Ear: WhisperKit (99 lang) / Parakeet-ANE → `voice.event` `trust:untrusted`.
  - Tongue: NL↔typed-intent translator + router. Orchestration is the DETERMINISTIC engine (U6 +
    `workflow_trigger` + capability routing); the model only does fuzzy NL↔intent translation. Generative
    answers DEFER to the rented brain, gated. Non-generative (INV-3) by contract.
  - Mouth: Kokoro-82M (machine→human).
  - **Moshi** = premium full-duplex voice UPGRADE (Mac tier), later. Tiering = teacher→distilled student,
    same character harness + TTS voice identity.

### Entrypoint security model (the thesis: secure by ARCHITECTURE, not model-robustness)
You cannot make a generative entrypoint injection-proof. You make the entrypoint model POWERLESS. Layers
(all grounded in current code):
1. `lgwks_jailbreak.is_clean()/sanitize()` — deterministic regex gate BEFORE any model. **HONEST GAP: it is
   a 20-line regex** (ignore-previous/system-prompt/DAN/override + control-char strip). Thin for "biggest
   attack surface" → ML node below.
2. **Non-generative model (INV-3):** output is typed intent/proposal, never an action/command. Injection at
   worst mistranslates; it cannot *do*.
3. **`trust:untrusted` on all entrypoint input** → `lgwks_capability_action._WEAK_TRUST` may NOT carry a
   dangerous effect without explicit confirmation. The deterministic gate holds the line (verified in code).
4. **Reversibility doctrine:** irreversible/destructive/publishing effects demand confirmation regardless.
5. **Provenance + replay:** `raw_ref` immutable raw text → audit said-vs-proposed.
6. **Model sandboxed to translation:** no tools, no execution, no memory-write authority. Output is data.

### Weird/illogical human input — handled by DEFERRAL, not generation
Same principle: the translator classifies intent + confidence (U6 `confidence_P` + slop/drift flags); if it's
a judgment/open question with no clear capability → defer to human (clarify) or to the GATED brain (labeled
suggestion, never an action). A generative model fabricates authority over the user's decision; a deferring
translator routes/asks. Gate bottoms out in human/default, never mandatory-AI.

### OPEN ML node (Director to finalize) — entrypoint injection guard
Current gate is a thin regex (#1). Candidate hardening: **Llama Prompt Guard 2** (Meta Purple Llama) —
purpose-built injection+jailbreak classifier, 86M multilingual (EN/FR/DE/HI/IT/PT/ES/TH) or 22M English,
real-time/low-latency/on-device. Options: (A) 86M multilingual ML guard + keep+harden deterministic gate
(defense-in-depth) [rec, matches multilingual req]; (B) 22M English + det. gate; (C) deterministic-only,
harden regex, no ML guard. Architectural backstop (untrusted→gate) remains the real guarantee either way.

## 2026-06-13 (session 15 cont.) - FINALIZED: layered guard + ATTENUATION LADDER w/ transparency receipt

Director ruling: don't hard-block — **degrade gracefully and tell the user** (the "Fable→Opus downgrade"
pattern applied to safety). Rationale (UX): *humans walk into dangerous territory unknowingly due to
technical debt* — the system has context the human lacks (effects, reversibility, capability graph), so it
should catch the danger, do the SAFE thing, and explain. This is the PDO **guardian** role made concrete.

- **Injection guard FINALIZED:** Llama Prompt Guard 2 **86M multilingual** (matches multi-lang req; swappable
  to 22M) as Layer-2 ML classifier + keep+harden the deterministic `lgwks_jailbreak` regex (Layer-1). Detection
  feeds the attenuation ladder below, not a bare block.

- **NEW — Attenuation ladder (the spec's flagged-missing "runtime attenuation"; extends `capability_action`
  gate primitives reversibility + trust→effect + confirm). On a flagged/risky request, try IN ORDER:**
  1. **CLEAN** — strip the unsafe component (injection / dangerous arg). If cleaned request is safe AND
     reversible → run it.
  2. **DOWNGRADE** — run a safe/reversible/sandboxed equivalent instead of the risky one.
  3. **CONFIRM** — can't be made safe but plausibly legit (e.g. irreversible-but-intended) → defer to human
     with explanation.
  4. **BLOCK** — only if un-attenuable + malicious → block, still explain what was caught.
  Each step emits a **system-generated TRANSPARENCY RECEIPT** to the user ("detected X; ran safe variant Y
  instead" / "held Z because irreversible — confirm?").

- **TWO hard design rules (non-negotiable):**
  - The transparency receipt is **system-generated / TEMPLATED from the gate decision — NOT LLM-narrated.**
    Letting the generative model narrate the safety explanation reopens the attack surface. Deterministic only.
  - Attenuation **respects reversibility**: a cleaned *reversible* action may auto-run; an **irreversible**
    action NEVER auto-runs even when cleaned — it always escalates to CONFIRM (irreversible-vs-purchasable
    doctrine). "Clean and run" applies to reversible/compensatable effects only.

- Receipt rides the existing append-only #118 audit trail (`lgwks_sign`); user-facing message is a rendering
  of that receipt.

PENDING (next): (1) write the attenuation-ladder contract (extends `lgwks.capability.action.v1` + review
layer); (2) MODEL-RUNTIME §3.1/§3.2 + `lgwks_model_mesh.py` MESH_LAW sync for the finalized slots; (3) fix
e2e (#139 migration race) + verify `daemon research`.

## 2026-06-13 (session 15 cont.) - UNIFIED RISK ENGINE: injection guard = HAD/algorithms, + accidental-injection threat class

Director: "why can't Prompt Guard be the same as our fraud ML/engine, the score+bs thing" + read the Chipotle
reel transcript (generative bot at entrypoint w/ authority + no gate → prompt-injected into free coding agent
"Pepper 1") + **"think of how I accidentally prompt-injected you — didn't hurt Anthropic but hurt me, still a
bad outcome."**

- **RESOLVED: injection detection is NOT a separate system — it is one more signal in the existing risk-
  scoring + abstention engine.** The "score+bs thing" = `archive/.../lgwks_had.py` (Human Assumption Decoder:
  decodes utterance→typed intent + scored assumption ledger; ABSTAINS to human review when posterior < τ or
  action risky; "cannot silently assume") + `lgwks_algorithms.py` (rolling_z_score/EWMA anomaly scorers —
  "score and flag; never generate, never decide authority"). [Both currently archived → revive/relocate.]
- **De-conflation (the recurring sensor-vs-math-engine line, per their own code comments):**
  - The risk ENGINE is deterministic: HAD's Bayesian posterior over the L1 classifier distribution, z-score/
    EWMA detectors, the verb risk-lexicon (irreversibility knowable without inference). Calculator-test applies.
  - Injection detection over RAW NL is a learned SENSOR (language semantics) → produces an `injection_risk`
    evidence score, exactly like the L1 similarity distribution is HAD's "literal-listener signal."
  - **So: add an `injection_risk` scorer to the algorithms catalog feeding HAD's abstention gate. Detection
    sensor = reuse owned Qwen3-Embedding + a tiny injection head/centroid (preferred — reuses owned models);
    Llama Prompt Guard 2 = teacher/baseline to train+eval the head against, and fallback.** No siloed guard.
- **NEW THREAT CLASS — accidental self-injection (human-protection, not just attacker-defense):** the human
  steers the AI into a bad-outcome-FOR-THEMSELVES via ambiguous/over-layered input (Director did this to me
  this session: I inferred intent, ran abstract, inverted ML-vs-LLM — "infer assumption, treat as fact, act,
  narrate over the hole," HAD's exact target failure shape). The SAME engine catches it: HAD scores the
  assumption and ABSTAINS/CONFIRMS instead of confidently running. One engine covers all four:
  malicious injection (Chipotle) · accidental injection (Director) · weird input (carwash) · fraud/anomaly.
- **Product implication:** the entrypoint translator surfaces WHAT IT ASSUMED + abstains when uncertain
  (HAD assumption ledger == the transparency receipt). Protects the human from attackers, from their own
  ambiguity, and from tech-debt danger they can't see. Same mechanism throughout.
- Revive `lgwks_had` + `lgwks_algorithms` from archive into the live risk path as part of the entrypoint work.

## 2026-06-13 (session 15 cont.) - IMPLEMENTED: graded entrypoint injection-risk + abstention ladder

Factory call (quick-to-prod, easy-fixes-later): ship the deterministic graded scorer + verdict + transparency
receipt NOW, behind a graceful ML-sensor seam (mirrors `lgwks_embed_port`'s mlx→transformers→floor). Models are
NOT downloaded this pass — the seam is wired and degrades to the deterministic floor; the model swap is one
function later. Tied into existing code (extended `lgwks_jailbreak`, wired into U6 `lgwks_engine`); no new
peer module minted.

- **`lgwks_jailbreak.py`** (extended, back-compat preserved): `injection_risk(prompt)` → {score∈[0,1], signals,
  mode}; `assess(prompt)` → {verdict proceed|attenuate|confirm|block, injection_risk, signals, receipt}.
  Deterministic, calculator-derivable; named thresholds (_T_BLOCK .80 / _T_CONFIRM .45 / _T_ATTENUATE .20).
  Signals scope to *instructions to change model behaviour* (override/role-reassign/delimiter/probe/scoped-
  bypass/obfuscation) — "SQL injection" is a TOPIC and scores 0. `_ml_injection_score` = the seam for
  Llama-Prompt-Guard-2-86M / Qwen3-Embedding head (honors LGWKS_NO_MODELS, fails closed-to-floor).
- **`lgwks_engine.py`** (U6): binary injection block → graded `assess()`. Only `block` short-circuits (richer
  `_denied_envelope` w/ receipt); attenuate/confirm sanitize-and-continue but ride a `injection_<verdict>`
  flag + `meta.injection.{verdict,signals,receipt}` so the gate can require confirmation. `injection_risk`
  added to §6 scores. INV-7 fix: cap prompt BEFORE scanning (no latency blowup, no evasion gap).
- **`tests/test_injection_risk.py`** (new, 11 tests): verdict ladder, SQL-injection-not-an-attack guard,
  determinism, bounds, back-compat, engine block/clean/confirm wiring.
- **Verified:** 91 tests green (engine + invariants + injection + daemon_event + capability_action +
  workflow_trigger). Live CLI: attack→REDACTED+receipt; "SQL injection vulnerabilities"→proceed, risk 0.0.
- **Still pending (next):** wire the ML sensor (Prompt Guard 2 / embedding head); revive `lgwks_had` +
  `lgwks_algorithms` so injection_risk composes with fraud/anomaly/assumption-risk in ONE engine; attenuation
  EXECUTION at the capability gate (clean-and-run / downgrade); mesh §3.1/§3.2 sync; e2e (#139).
