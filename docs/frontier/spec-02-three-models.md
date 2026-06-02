# SPEC-02 — The Three Frontier Models + the AI-Lang Horizon

> The research-track context for the build units. Read MAP.md first.
> Note: model *training* is a research track (PyTorch+MPS, see ml-001/#27). The deterministic
> Kimi build (spec-03) delivers the **platform + gates** these models plug into, NOT the training.

## The axis: AI begins where verification ends

Sort by how checkable an output is — that property *is* the line where ML becomes AI. While an
oracle checks every output, the thing stays ML (bounded, instrumentable, turn-back-able). When output
must exceed what can be checked, it crosses into AI (generative, blackbox, gated). The three models
are three points on that axis, on purpose — this is the instrument for "mapping the exact point."

| # | Model | Oracle | Verifiability | Stance | Base to fork |
|---|---|---|---|---|---|
| 1 | Intent / cognitive-psych membrane | calibration (Brier/ECE), abstain | LOW | stays ML/discriminative; **advisory only** | ModernBERT-base (Apache; distill to fit ANE) |
| 2 | **Constrained coder** (schema → Rust, review) | **compiler + tests + formal proof** | HIGH | flagship; sits *on* the line | small code base model (unixcoder #17 / StarCoder2 / Qwen-coder, Apache) |
| 3 | Science engine (Co-Scientist analog) | hypothesis tournament; experiments verify late | MED→generative | mostly **harness over free Tier-G** generative | no from-scratch model |

Model 2 is itself a small inflection point — your own phrase: *"AI like code review, ML like math."*
The math/structure half is checkable (ML); the judgment half of review leans generative (AI).

## Why not from-scratch, why not distillation (the bias question, settled)

Two things are called "bias": (a) the **substrate** — knowing English/symbols/numbers; the prerequisite
to read a problem at all; cannot be stripped. (b) the **slop** — sycophancy, hedging, refusals,
confident hallucination; bolted on in the *instruct/RLHF* layer, almost absent in a **base** model.
You want to strip (b), not (a). So: fork a **base** (non-instruct) model → keep substrate, drop slop.
- From-scratch needs billions of tokens of clean corpus (not the ~tens-of-thousands of eval rows collected).
- Distillation datasets (TraceInversion = Claude's reasoning; AgentTrove = teacher traces) **import the very
  bias to escape** — at most a disposable cold-start you RL *away* from, never a foundation.
- Benchmarks (GSM8K-test, AIME, HLE) are **held-out rulers, never training data** (HLE ships a canary).

## The anti-slop lever: verifiable reward (RLVR)

Math/physics/code have *checkable answers*. Reward the model **only when its output is provably correct**
— never for sounding nice, never for human approval — and sycophancy becomes structurally unrewardable.
The truth is the reward. This is your "anti-AI," made mechanical, and it is the Tier-G character
("truth over helpfulness") expressed as a loss function. The gate stack (spec-00) IS the reward signal:
compiler + architecture + framework-reality pass = reward. (Prior art, training-grounded: Monitor-Guided
Decoding = compiler-in-the-loop generation; AlphaProof/AlphaGeometry = formal-verifier reward; RLVR
code lineage. VERIFY LIVE before hardening — grounding was blocked at spec time.)

## The platform (build once — this is what spec-03 delivers)

| Layer | State |
|---|---|
| Data substrate — content-addressed cognition/fact-log = private uncontaminated corpus + snapshot ledger | **built** (`lgwks_cognition.py`) |
| Governance — snapshot/freeze/turn-back, champion-challenger | **built** (`lgwks_machine.py`) |
| **Verifier/oracle + comprehension gate** | **build first** (spec-01 → U0, U1) |
| **Coherence Engine gates** G1/G2/G3 | **build** (spec-00 → U2–U5) |
| Train→deploy: PyTorch+MPS → safetensors-hash → CoreML/ANE adapter | research track (ml-001) |
| Instrument — Captum + calibration = the dials on the inflection line | research track |

CoreML/ANE is **inference-only** (cannot train; never cuts training compute). Training cost is cut by
smallness + LoRA deltas + verifiable-reward-as-free-infinite-data. CoreML = the last mile, the swappable
adapter — never the foundation.

## The marketable claim + the AI-Lang horizon

> "Every line we emit is machine-proven conformant to the supplied spec — or we emit nothing."

The 100% is a property of the **gate**, not the model — a fallible model searches; only proven-conformant
output escapes. **Sound, not complete:** never wrong, sometimes abstains (exactly what audit frameworks
are). Two scoping limits keep it honest: (1) "proven" = **oracle-backed gates only** (G0 compiler/formal);
the heuristic HARD gates (G1/G3) carry a stated false-PASS surface and are not "proofs" — see spec-01's
soundness obligation. (2) The 100% holds **only** on the spec→code edge; **never** on intent→spec (intent is
not formalizable — the human stays on that edge, G4). Precedent: CompCert (proven C compiler), seL4, RustBelt.

**AI-Lang ↔ Human-CS-lang:** a provable intermediate language where AI operates, with **verified lowering**
to Rust (the human projection). 100% propagates down the stack as long as each arrow is a proven compiler.
The only un-formalizable arrow is intent → AI-Lang (human-in-loop). Multi-year program; clear shape.

## How this outgrows the wall

Data wall → dissolves in verifiable domains (a compiler is an infinite teacher). Blackbox wall → beaten by
smallness (models small enough to instrument; poverty becomes an interpretability moat). Generality →
emergent in the *harness* composing specialists, not in any one blackbox. We don't climb their road higher;
we walk up to the inflection line and read the dials — the one move a scale-maxing lab structurally cannot make.
