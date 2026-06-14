# PRD-06 — Transcript Cortex & Subconscious Engine (C/G/P)

Parent: [PRD.md](../PRD.md) U5+U6, §7 equations, §8 flags · Status: draft v0.1 · **gated on SCIENCE.md pre-registration**
Replaces: nothing external — this is the novel core, and the highest-risk child.

> ⚠️ **DRIFT NOTICE (2026-06-14) — spec ≠ shipped. Do not read the equations below as what runs.**
> The shipped engine (`lgwks_engine.py`, schema **`lgwks.engine.schema.v1`** — *not* the `lgwks.engine.v1`
> named in this PRD's Contract section) computes **different math under the same names**: `C` = capability
> coverage (IDF/Qwen-cosine), `G` = `1 − grounding_rate`, `P` = geometric mean over available axes (+ a 4th
> axis `decisiveness_d` not in this spec). The `required_nodes`/`grounded_nodes` model and the Bayesian/
> calibrated `P` **below are UNBUILT** (target, not current). Canonical reconciliation decision is pending the
> PI — see `Desktop/LogicOS-Conflict-Ledger-2026-06-14.md` C-01 and the tracking issue. The definitions
> below are the *design target*, retained verbatim for that decision.

## Problem (and the hard truth)

§7 is the product: C (coverage), G (gap/risk), P (outcome confidence). It is also the least
specified thing in the parent — `required_nodes` is the grounding problem wearing a variable
name. This PRD's job is to make the equations *operational and falsifiable* before they are
allowed to steer anyone. Until calibrated, C/G/P are vibes-with-decimals; injecting them
would be the exact confident-narration defect the system exists to kill.

## Definitions (v0.1 — operational, falsifiable, revisable by evidence)

- **required_nodes(intent)**: derived deterministically as the union of (a) graph
  neighborhood (depth 1) of every entity the intent mentions that resolves in the
  world-graph, (b) the declared `input_schema` fields of the top-k mapped actors/verbs
  (PRD-01), (c) files touched by the current task's diff (when in a task). No model decides
  membership (INV-4). //why: imperfect but checkable; a wrong required-set is visible and
  arguable, an implicit one is not.
- **grounded_nodes**: required nodes with at least one evidence edge — read-in-session,
  retrieved-with-citation, or verified-by-command (transcript shows the tool call).
- **C = |grounded| / |required|** over those sets.
- **G = Σ unverified_claim_i × w(tier_i)**: claims extracted from Opus's transcript turns by
  deterministic patterns first (assertions about env/git/files/tests with no preceding tool
  call — the operating-loop defect, mechanized), classifier-assisted later (05-e). Trust
  tiers w: verified-by-command=0 · cited-file=0.1 · cited-docs=0.3 · uncited-assertion=1.0.
- **P = calibrated f(C, evidence_tier_mix, prior_similarity)**: starts as logistic over
  those features, fit on labeled session outcomes; *reported only with its calibration
  error*. Until ≥N labeled outcomes exist, P is cockpit-only (never injected to Opus).

## Scope

- IN: transcript cortex (U5): tail `*.jsonl` → per-turn `{intent_class, phase, entities,
  attention}`; deterministic extraction first, BERT salience when 05 lands.
- IN: engine (U6): emits `{C,G,P}` + flags + selections per §6 schema, reproducibly.
- IN: flags (§8): slop/sycophancy/dredge/intent-drift/unverified-claim — every flag carries
  a verbatim transcript-span citation (non-generative evidence); precision-gated per flag
  class (SCIENCE §6) before entering the Opus projection; unproven flags are cockpit-only.
- OUT: blocking (PRD-07 owns tap behavior). OUT: any generated prose (INV-3).

## Builds on (candidates — verify at unit start)

`lgwks_intent_classifier.py` + `lgwks_machine.py` (tested: tests/test_machine.py,
test_intent_classifier.py) · `lgwks_cognition.py`, `lgwks_comprehend.py`,
`lgwks_steering.py`, `lgwks_ground.py`, `lgwks_verify.py`, `lgwks_jepa.py` ·
bot-fabric slop work: `lgwks_bot_slop_math.py` + docs/bot-fabric/U6-SLOP-MATH.md (prior art
in-repo — read before building flag detectors; do not re-spec an existing fence).

## Contract

Emits `lgwks.engine.v1`: `{C, G, P?, flags[{class, span, turn, confidence}],
selections[], attention?}`. P optional until calibrated (absence is honest). Consumers:
PRD-04 (folds into inbound schema), PRD-07 (both projections), PRD-08 (persisted).

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 06-a claim extractor | on 20 hand-labeled transcript turns (incl. the three documented lies: "pytest isn't installed" etc.): unverified-claim detection precision ≥0.8 / recall ≥0.6 measured; spans verbatim |
| 06-b required/grounded sets | for 10 frozen intents: required_nodes set printed, human-auditable, deterministic across runs; C computed; disagreements logged as corpus fixes not code hacks |
| 06-c cortex | live session tailed → per-turn record within 2s of turn end; replayable from jsonl (same file → same records) |
| 06-d flag gates | each flag class ships only with measured precision on its labeled set ≥ pre-registered threshold (SCIENCE §6); below-threshold classes exist cockpit-only |
| 06-e P calibration | after ≥30 labeled session outcomes: reliability curve + Brier score reported; P enters Opus projection only if Brier beats the always-predict-base-rate baseline |

## Open questions → SCIENCE.md (this PRD is mostly open questions — by design)

All of §7's terms (§2, §6, §7 there). Labeling protocol for session outcomes. Whether
intent-drift is detectable lexically. Attention: BERT salience vs tf-idf baseline.

RISK: shipping C/G/P un-calibrated converts the subconscious from defect-catcher to
defect-amplifier — numbers carry false authority precisely because they are numbers.
