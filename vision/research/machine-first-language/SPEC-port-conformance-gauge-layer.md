# SPEC — Port-Conformance & the Gauge Layer (lgwks radar, ratatui end-state)

**Status:** PROPOSED (draft for lgwks ADR-005) · 2026-06-06 · machine-first (next reader is an AI)
**CORRECTION (2026-06-06, post-review):** this SPEC overclaimed. Rust/Java parity does NOT *derive
validity* — it **measures the human-legibility residual** (how far our system degrades to a human
standard). Actual validity must come from the AI-native self-play physics (RLVR), still unbuilt — the
keystone. The divergence gauge (ADR-004 D5) is also NOT AI-native; it's a generic agreement score whose
only discipline is channel-independence (a P-property). See HANDOFF-2026-06-06 for the full correction set.
**Scope:** the **gauge/radar layer** of lgwks and its first hard validity instrument — the **algebraic
port** of our framework to two bracketing standards (Rust, Java). Realizes SPEC-translation-chain §4.4/§4.5
and ADR-004 D4/D5. **Adopts** logic-os-kernel ADR-079 (global-handoff radar) as a fact *source*, never forks
it. Render target: **ratatui** (Rust TUI, v0.30 — ships `Gauge`/`Sparkline`/`Chart`/`BarChart`/`Table`/`Block`).

## §0 The frame — a gauge is a fold, not a feeling
End-state = a full TUI cockpit (gloomberg density: multi-panel, real-time, information-dense). The pipeline
is one-directional and fences the AI out of the load-bearing half:
```
execution trace (ADR-068 facts) ──fold──▶ GaugeState (plain data) ──render──▶ ratatui widget
  harness-captured emissions       pure reduce()                      Gauge/Sparkline/Chart/Table
        ▲ AI may NOT author facts (INV-8)     ▲ AI may NOT touch the fold (INV-7)
```
Every panel is `reduce(trace)`. AI fills operands *inside* a node; never the fold, never system-health.

## §1 The algebraic port — coefficient = a measured forgetful functor
Lowering our proof-carrying term (capability+provenance+L typed) to a target **erases** what the target
can't express. `lower_T : Ours → T` for `T ∈ {Rust, Java}`. Validity is whether the square commutes:
```
        lower_T
  Ours ─────────▶ T
   │              │
 eval_ours      eval_T          coefficient_T = fraction of corpus where
   ▼              ▼             eval_T(lower_T(P)) == erase_T(eval_ours(P))
 behavior ══erase══ behavior
```
**Two coefficients per target (Director, 2026-06-06 — "both, layered"):**
- **ceiling = structural embedding** — `dim(our_types ∩ embeddable_in(T_types)) / dim(our_types)`. A static,
  proof-theoretic measure of which of our guarantees the target's type system can even hold. No execution.
- **floor = behavioral conformance** — differential test: same program run our-way vs lowered-to-T; fraction
  of the benchmark corpus where observable behavior matches `erase_T(·)`. Runnable, gauge-able today.
- **`gap(ceiling, floor)` = OUR lowering's own defect** — guarantees the target *could* hold that our
  lowering failed to preserve at runtime. This is the self-critical instrument: it points at us, not the target.

## §2 Why Rust + Java — they bracket the space, so two derives what one cannot
| Target | Pole | Of OURS that survives | Erases (coefficient → 0) |
|---|---|---|---|
| **Rust** | static-linear; borrow-checker = a proof system | linear non-cloneable resource + capability-flows-up (our T3 binning antidote *is* affine typing) | provenance, L, the `basis` DAG |
| **Java/JVM** | managed portable-bytecode + VM | the off-ramp: compile→bytecode→VM, forward-compat class format | ownership/linearity (GC aliases all), provenance, L |
Faithful lowering to **both** poles ⇒ the design is not overfit to one paradigm (cross-paradigm conformance
> single-target). **The residual neither standard can represent at all = provenance + capability + L = the
moat**, now a number: "the part with ceiling 0 against every standard." That is the **legibility-residual**
metric — how much we exceed every human standard — NOT a validity proof (see CORRECTION above).

## §3 The unification — port-parity IS gauges on the same dashboard
Four port coefficients (Rust/Java × ceiling/floor) + the divergence gauge (ADR-004 D5) are all folds over
traces, one ratatui render tree, zero AI in any fold. Concrete panels (gloomberg layout):
- `Gauge` — L, R, divergence, the 4 parity coefficients (scalars).
- `Sparkline` — L / R / divergence over the run timeline.
- `Chart` — term-DAG flow (clicks vs holes); `Table` — the gap ledger (open Holes, nearest_known).
- ADR-079 handoff-radar pings = one input channel (capability movements), folded, never narration-fed.

## §4 Invariants (testable)
- INV-G1 every gauge value is `reduce(trace)` of harness-captured facts; recomputing from the same trace is
  byte-identical (deterministic fold). No AI in the fold (carries SPEC INV-7).
- INV-G2 no gauge reads the agent's narration; divergence = disagreement(narration, radar) (carries INV-8).
- INV-G3 `coefficient_T` is recomputed by an independent harness over a fixed corpus; never self-reported
  (mirrors ADR-004 D4). The corpus and its CID are pinned per measurement.
- INV-G4 `floor ≤ ceiling` always; a measured `floor > ceiling` is a bug in the instrument, not a result.
- INV-G5 a guarantee with `ceiling_Rust = ceiling_Java = 0` is logged as moat-residual (provenance/cap/L) —
  the thing we add that no standard holds.
- INV-G6 the gauge layer degrades to plain text when the TUI can't render (fail-open-to-dumb; SPEC INV-6).

## §5 Build sequence (this SPEC commits to)
1. **Corpus + lowerings** — a small pinned benchmark corpus (CID'd); `lower_rust`, `lower_java`, and the
   matching `erase_T`. Smallest core-calculus sublanguage first (the intersection all three express).
2. **floor harness** — differential runner → `coefficient_floor_T`; verification: a deliberately broken
   lowering drops the coefficient (INV-G3/G4 test).
3. **ceiling analysis** — structural type-embedding check → `coefficient_ceiling_T`; emits moat-residual set.
4. **ratatui cockpit** — fold→`GaugeState`→widgets; divergence gauge first (ADR-004 D5 build #3), then the
   4 parity gauges. Plain-text fallback (INV-G6).
5. ADR-079 radar pings folded in as a channel once 1–4 hold.

## §6 Open forks / next
1. Promote to lgwks **ADR-005** once the floor harness shows a real coefficient on the core calculus.
2. Core-calculus boundary: exactly which constructs are in the Ours∩Rust∩Java intersection (the 1:1 set)?
3. `erase_T` must be specified per target (what proof is dropped) — it is the formal definition of the off-ramp.
