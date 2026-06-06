# ML Hardening Handoff — 2026-06-06

Scope for this pass:

- harden the local ML runtime as a single inspectable contract
- keep the deterministic path as the equalizer and token saver
- make semantic upgrades explicit, optional, and locally verifiable

What was tightened:

- `lgwks_model_hub.convert_to_coreml()` now uses a shared Python-version gate instead of crashing on missing `sys`.
- `lgwks model-hub doctor` now reports the end-to-end local ML state:
  - repo model inventory
  - CoreML conversion eligibility
  - intent-classifier readiness
  - Foundation/NaturalLanguage backend availability
  - local semantic Eye status
- tiny or single-label classifier fine-tunes now fail early with a clear error instead of pretending to train something meaningful.

Why this matters:

- one command can now answer whether `lgwks` is operating in:
  - deterministic-only mode
  - local semantic mode
  - partially configured broken mode
- that reduces agent slop because the runtime contract is explicit before any LLM is asked to infer capability from symptoms.

Operator commands:

```bash
./lgwks doctor
./lgwks model-hub doctor
python scripts/setup_models.py all tiny-bert
```

Interpretation:

- If `semantic_eye.up=false`, the system still works, but only the deterministic moat is active.
- If `intent_classifier.coreml_model_loaded=false`, routing stays advisory-safe and cannot unlock full authority through the semantic classifier path.
- If Foundation backends are unavailable, extraction remains deterministic/T2-first; this is acceptable and honest.
