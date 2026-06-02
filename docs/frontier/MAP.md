# Frontier Program — End-to-End Map

> Audience: autonomous coding agents (Kimi fleet) + the orchestrating generative AI.
> Status: SPEC, Director-vetted thesis (2026-06-02). Build order is normative.
> Doctrine: every unit is issue-backed, evidence-gated, `//why`-annotated. No happy-path stubs.

## 0. One-paragraph thesis

We are not building a better code generator — that road ends at the wall every frontier
lab hits (statistical generalist, no gate, uninterpretable). We are building the **gate and
the ground**: a generator-agnostic coherence layer that makes *any* model's output conform to
this system's architecture, this repo's idiom, and the *real* installed framework surface — and
proves the parts that are provable. The generator (free model, or the orchestrating AI) proposes;
the **Coherence Engine** disposes. What ships is coherent and, where an oracle exists, 100%.

## 1. The central instrument: the verifiability axis

Everything sorts on one axis — **how checkable an output is** — and that axis *is* the line where
ML becomes AI. **AI begins where verification ends.** While an oracle can check every output, the
thing stays ML: bounded, instrumentable, turn-back-able. When output must exceed what can be
checked, it crosses into AI: generative, blackbox, gated.

```
  more checkable  ────────────────────────────────────────────►  less checkable
  │                          │                          │
  G0 compiler/types     G1 architecture            G3 framework-reality
  G4 formal proof       G2 idiom (advisory)        intent → spec (HUMAN)
  │                          │                          │
  HARD / 100%           HARD where invariant       HUMAN-IN-LOOP
                        is machine-checkable        (never 100%)
```

## 2. The three frontier models (points on the axis)

| # | Model | Oracle | Verifiability | Stance | Spec |
|---|---|---|---|---|---|
| 1 | Intent / cognitive-psych membrane | calibration (Brier/ECE), abstain | LOW | stays ML/discriminative; advisory only | ml-001 (#27), spec-02 |
| 2 | **Constrained coder** (schema → Rust, review) | compiler + tests + formal | HIGH | the flagship; sits *on* the line | spec-02 §2, spec-03 |
| 3 | Science engine (Co-Scientist analog) | hypothesis tournament; experiment verifies late | MED→gen | mostly harness over Tier-G generative | spec-02 §3 |

## 3. The platform (build once, all three fork from it)

| Layer | What | State |
|---|---|---|
| Data substrate | content-addressed cognition/fact-log = private uncontaminated corpus + snapshot ledger | **built** (`lgwks_cognition.py`) |
| Governance | snapshot / freeze / turn-back, champion-challenger | **built** (`lgwks_machine.py`) |
| Train→deploy | PyTorch+MPS → safetensors-hash in fact-log → CoreML/ANE adapter | specced (ml-001), needs wiring |
| **Verifier / oracle** | typed `Verifier(output) → Verdict`; gate registry; hard vs advisory | **new — spec-01, build first** |
| **Coherence Engine** | the gate pipeline G0–G4 (the "more than a compiler" core) | **new — spec-00** |
| Instrument | Captum + calibration = the dials that show the inflection line | needs wiring |

## 4. Document index

**Implementing agents start at `BUILD.md`** — it is the E2E entry (read order, the mandatory
Comprehension Gate loop, implement → commit). The specs, in reading order:

1. `spec-00-coherence-engine.md` — the core contribution: four gates beyond the compiler;
   how it serves a context-engineered AI *and* a human; why it is different, not a copy.
2. `spec-01-verifier-oracle.md` — the one new primitive: the typed `Verifier` protocol + gate
   registry + hard/advisory soundness discipline + the **Comprehension Gate** (Intention × Understanding).
3. `spec-02-three-models.md` — the three frontier models mapped to the axis + platform forks +
   the AI-Lang ↔ Human-CS-lang horizon. (Model *training* is a research track, not this build.)
4. `spec-03-build-units.md` — the implementation plan: units U1–U7 in dependency order, each with
   L0–L5, checkable acceptance criteria, file targets, gate classification, commit message.
5. `spec-04-claude-cli-division.md` — the end-state: Claude (judgment) + CLI (deterministic substrate);
   why honest gates (#29) are the precondition for the CLI to absorb tool calls.
6. `BUILD.md` — operational entry for the implementing agent.

## 5. The marketable claim (the boundary that must be enforced in code, not prose)

> "Every line we emit is machine-proven conformant to the supplied spec — or we emit nothing."

Sound, not complete: **never wrong; sometimes abstains.** The 100% is a property of the *gate*,
not the model. The single way this becomes a lie is scope-bleed across the intent→spec edge
(G4): the day the API accepts "just describe what you want" instead of a typed spec, soundness
is gone. The spec requirement is enforced at the API boundary (spec-01 §4), never in a disclaimer.

## 6. How this outgrows the wall

The data wall dissolves in verifiable domains (a compiler is an infinite teacher). The blackbox
wall is beaten by smallness — models small enough to instrument; poverty becomes an interpretability
moat. Generality is an emergent property of the *harness* composing specialists, not a property of
any one blackbox. We do not climb their road higher; we walk up to the inflection line on purpose
and read the dials — the one thing a scale-maxing lab structurally cannot do.

Cross-refs: `docs/ml-001-intent-classifier-sizing.md` (pending reconciliation on
`fix/manifest-derives-verbs`), issues #17 (neural Tier-E), #25 (lgwks-expression), #27 (classifier).
