/-
  Framework.lean — the Excellent Code Framework, formal skeleton.

  STATUS — read this before trusting it.
  This file is the *reference definition* of the three framework concepts
  (`CoreGroundedCorrect`, `Hallucinated`, `Excellent`) and the twenty evidence
  atoms. It is the authority that `schema/concepts.json` MUST match: the
  conformance obligation in `src/conformance.mjs` (run by `src/qualify.mjs`,
  the ORG.selftest entry) parses the three defs below and asserts the JSON
  formulas are structurally identical — same atom leaf-set, same boolean shape.

  MACHINE-CHECKED (#646, ledger item 6). This skeleton TYPECHECKS: `lake build` (the package
  here — lakefile.toml + lean-toolchain v4.31.0, pure Lean 4 core, no Mathlib) compiles it, and
  `excellent_not_hallucinated` depends on NO axioms (`#print axioms` — fully constructive, no
  `sorry`). `src/qualify.mjs` now runs that build as the `lean-skeleton-machinecheck` row via the
  `tool: lean` seam (src/adapters/lean.mjs), so the conformance reference is COMPILED, not merely
  transcribed. When the toolchain is absent the build row degrades to SKIP (`unknown`, never a
  pass — Lean depth is purchasable, docs/05 §5.2) and the always-on structural check below still
  gates. The first compile caught a real bug: a `/-- -/` docstring above `variable` (Lean rejects
  it) — the transcribed-vs-compiled gap this work closes.

  WHAT IS STILL STRUCTURAL. `src/conformance.mjs` asserts `schema/concepts.json` matches the three
  defs below (same atom leaf-set, same boolean shape). That is a structural transcription check; it
  is the machine-check ABOVE that proves the Lean itself is sound. The skeleton is a faithful
  transcription of docs/02 §2.4. NOT yet done — per-atom proof grafting: binding
  type_soundness/totality/invariant_preservation of an arbitrary TARGET unit to a Lean proof. The
  `tool: lean` proof-term node exists (the seam); deeper per-atom proofs are purchasable (docs/05 §5.2).

  Atom ids below are the canonical snake_case ids of schema/atoms.json (n = 1..20).
-/

namespace ExcellentCode

/-- The twenty evidence atoms. Ids and order match `schema/atoms.json` (`n` field). -/
inductive Atom where
  | referential_truth                  -- n=1
  | specification_fidelity             -- n=2
  | type_soundness                     -- n=3
  | precondition_correctness           -- n=4
  | postcondition_correctness          -- n=5
  | invariant_preservation             -- n=6
  | totality_or_controlled_partiality  -- n=7
  | boundary_completeness              -- n=8
  | compositionality                   -- n=9
  | minimal_sufficient_complexity      -- n=10
  | algorithmic_efficiency             -- n=11
  | state_minimization                 -- n=12
  | data_model_truth                   -- n=13
  | error_semantics                    -- n=14
  | security_by_construction           -- n=15
  | idempotence                        -- n=16
  | concurrency_correctness            -- n=17
  | observability                      -- n=18
  | testability_falsifiability         -- n=19
  | change_locality                    -- n=20
  deriving DecidableEq

/-
  An evidence assignment maps each atom to whether it has been DEMONSTRATED.
  Keel instantiates `holds a` only from a real Tier-1 measurement; an atom with
  no bound evidence is `unknown`, never `True` (the three-valued discipline,
  docs/02 §2.6, is modelled in the engine — the skeleton states the floor).
  (Plain block comment, not a `/-- -/` docstring: Lean 4 attaches docstrings only
  to declarations that accept them, and `variable` does not — `lake build` rejects it.)
-/
variable (holds : Atom → Prop)

open Atom

/--
  `CoreGroundedCorrect` — grounding ∧ type evidence ∧ total correctness ∧ spec.
  The four core atoms (n = 1, 3, 7, 2). This is the conjunction `schema/concepts.json`
  concept `CoreGroundedCorrect` must equal.
-/
def CoreGroundedCorrect : Prop :=
  holds referential_truth
  ∧ holds type_soundness
  ∧ holds totality_or_controlled_partiality
  ∧ holds specification_fidelity

/-- `Hallucinated` is COMPUTED, not judged: exactly the negation of the core. -/
def Hallucinated : Prop := ¬ CoreGroundedCorrect holds

/--
  `Excellent` — the conjunction of all twenty atoms. The aspirational ceiling
  `schema/concepts.json` concept `Excellent` must equal (order-insensitive set).
-/
def Excellent : Prop :=
  holds referential_truth
  ∧ holds specification_fidelity
  ∧ holds type_soundness
  ∧ holds precondition_correctness
  ∧ holds postcondition_correctness
  ∧ holds invariant_preservation
  ∧ holds totality_or_controlled_partiality
  ∧ holds boundary_completeness
  ∧ holds compositionality
  ∧ holds minimal_sufficient_complexity
  ∧ holds algorithmic_efficiency
  ∧ holds state_minimization
  ∧ holds data_model_truth
  ∧ holds error_semantics
  ∧ holds security_by_construction
  ∧ holds idempotence
  ∧ holds concurrency_correctness
  ∧ holds observability
  ∧ holds testability_falsifiability
  ∧ holds change_locality

/--
  The theorem the verdict adheres to: an Excellent program is not Hallucinated.
  `Excellent` entails `CoreGroundedCorrect` (its first four conjuncts), and
  `Hallucinated` is the negation of `CoreGroundedCorrect`, so the two are disjoint.
-/
theorem excellent_not_hallucinated (h : Excellent holds) : ¬ Hallucinated holds := by
  intro hbad
  exact hbad ⟨h.1, h.2.2.1, h.2.2.2.2.2.2.1, h.2.1⟩

end ExcellentCode
