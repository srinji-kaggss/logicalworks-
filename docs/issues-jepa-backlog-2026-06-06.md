# JEPA Backlog — 2026-06-06

This is the working issue list for the JEPA/product-seed path.

## P0

### JEPA-001 — Product-facing `seed` surface

- Add `seed ingest|continue|refine|show|ls`
- Keep `jepa/capture/portal` as the machine substrate
- Product goal: human should not need to think in machine verbs

### JEPA-002 — Seed index and lookup

- Store seed metadata in an index
- Support lookup by:
  - key
  - repo
  - anchor
  - date
  - query text

### JEPA-003 — Continuation packet for coding agents

- Resolve best package for a continuation ask
- Refresh repo graph
- Emit compact technical stream
- Emit human fit summary

### JEPA-004 — Event ledger for package transitions

- Log:
  - seed build
  - repo bind
  - continue
  - command
  - outcome
  - contradiction/update

### JEPA-005 — Benchmark harness for continuation quality

- Compare:
  - raw prompt continuation
  - deterministic package continuation
  - semantic router continuation

## P1

### JEPA-006 — Candidate project binding

- Auto-suggest likely repo/project targets
- Preserve uncertainty instead of forcing one destination

### JEPA-007 — Human/AI projection divergence check

- Detect unsupported claims appearing only in human projection

### JEPA-008 — Seed resource folder contract

- Standardize:
  - raw views
  - extracted resources
  - citations
  - crawl products

### JEPA-009 — Daytime low-discipline intake mode

- Make ingest trivial for giant dumps / links / fragments
- Optimize for "capture now, structure later"

## P2

### JEPA-010 — ModernBERT seed router

- Predict:
  - continuation package
  - candidate repo
  - likely tranche
  - abstain when unclear

### JEPA-011 — Package-level JEPA predictor dataset

- Build training dataset from canonical packages
- Capture multiple views and aligned targets

### JEPA-012 — Temporal GNN event graph

- Learn on:
  - package
  - portal
  - command
  - outcome
  - contradiction

### JEPA-013 — Package-level controls and ablations

- `C0`: deterministic only
- `C1`: semantic router only
- `T1`: latent package predictor
- `T2`: predictor + GNN

## Research issues

### JEPA-R01 — Thesis validation for `H1`

- Do multi-view packages improve retrieval and next-step quality?

### JEPA-R02 — Thesis validation for `H2`

- Does latent alignment reduce wording sensitivity?

### JEPA-R03 — Thesis validation for `H5`

- Does deterministic CLI control reduce token and compute burden?

### JEPA-R04 — Gate to full LLM-JEPA training

- Only proceed if package-level controls show real wins
