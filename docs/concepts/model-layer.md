---
type: Concept
title: Two-Plane Model Layer — one port, locality axis
description: lgwks_model_port is the one selector across a locality axis (local Mesh ⊕ cloud models.dev ⊕ reserved Aetherius), orthogonal to the trust-tier ladder.
tags: [concepts, model, port, mesh, models-dev, locality]
owning_issue: "335"
timestamp: 2026-06-25T00:00:00Z
---

# The shape

Every cognition request flows through **one gateway**, `lgwks_model_port`. It composes
**two orthogonal axes**:

- **Trust-tier ladder** (WHICH tier answers): `deterministic → sensor → generative`
  — prefer determinism; the LLM is the last resort, even when present. The model id is
  pinned by the law (`lgwks_model_mesh.MESH_LAW`), never a literal — "LAW IS TRUTH".
- **Locality axis** (WHERE the model runs): `LOCAL ⊕ CLOUD ⊕ AETHERIUS`.
  - **LOCAL** = the on-device Model Mesh (MESH_LAW + `lgwks_model_hub`). Privacy-first,
    no network. The **default**.
  - **CLOUD** = `lgwks_models_dev` (Google-OKF-unrelated; the [models.dev](https://models.dev)
    catalog). **Opt-in only** — never silently chosen; defers when unconfigured.
  - **AETHERIUS** = the future end-of-ingestion trained model. **Reserved slot, deferred**
    ("data is a whole workstream"). Resolves to `None` today.

# Canonical entry points

| Concern | Symbol |
|---|---|
| The one selector | `lgwks_model_port.resolve_model(role, *, locality, trust_class)` |
| Active plane (env > persisted > default) | `lgwks_model_port.active_locality()` |
| Durable choice | `.lgwks/model-selection.json` (atomic, gitignored) |
| Two-plane catalog (TUI/CLI projection) | `lgwks_model_port.catalog()` |
| Cloud catalog client | `lgwks_models_dev.resolve(ref)` / `refresh()` (offline-first) |
| User surface | `lgwks models {list,get,use,locality}` |
| Human projection | TUI `Mode::Models` (`tui/`) — projects `catalog()`, no Rust-side catalog |

# Why it matters (the bug it closed)

The embed id was hardcoded (`"Qwen3-VL-Embedding-8B"`), and worse, `MESH_LAW` pinned
role=embed to a **hallucinated** `Qwen3.7-VL-8B-Instruct` (a visual-GUI agent, not an
embedder), contradicting its own source spec
([MODEL-RUNTIME-FINALIZATION §92/§117](/spec/second-harness/MODEL-RUNTIME-FINALIZATION-2026-06-13.md)).
So "LAW IS TRUTH" was a lie for embed. Correcting the law to its source + routing
`lgwks_run.embed` resolution through the port made the invariant true for the first
time, closing the #222 embed bypass.

# Provenance

Epic #335 (S1 #336 `e6aed45` · S2 #337 `2e60f1c` · S3 #338 `2dc718a`), branch
`feat/two-plane-model-layer`. Full suite 2291 pass / 0 genuine failures.

# Remaining (tracked, out of epic)

- Aetherius training (data workstream).
- `lgwks_embed_port` image/video **store-path** id resolution (same single Eye, not a
  drift bug — lower-priority convergence).
- Other #222 callers: `lgwks_map`, `lgwks_geoexpr`, `lgwks_score`.

# Citations

[1] Model law as data — [lgwks_model_mesh](/docs/AUTHORITY.md)
[2] Escalation order — [ESCALATION-LADDER-LAW](/docs/ESCALATION-LADDER-LAW.md)
