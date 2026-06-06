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

### JEPA-014 — Mac-native continuation shell

- Inspired by reusable patterns from `mlx-code`
- Add a local continuation shell for `seed continue`
- Requirements:
  - worktree isolation
  - backend seam
  - resume from package key
  - shell-friendly stdin/pipe behavior

### JEPA-015 — OSS incorporation guardrail

- Record license and provenance for imported ideas/code
- Block direct code import from repos with unclear license posture
- Require translation into `lgwks` machine language before merge

### JEPA-016 — Session/package search

- Search across:
  - seeds
  - jepa packages
  - portal packets
  - continuation outputs
- Goal: continuation should start from lookup, not memory

### JEPA-017 — Forkable continuation

- Resume a prior seed/package and branch it into a new continuation lane
- Preserve the original package lineage

### JEPA-018 — Readiness score for autonomy

- Score whether a repo/package is ready for:
  - read-only continuation
  - edit continuation
  - mission/multi-agent continuation
- Similar spirit to Factory readiness, but grounded in `lgwks` ontology

### JEPA-019 — Mission-mode continuation

- Run structured continuation with:
  - researcher worker
  - repo-grounding worker
  - critic/contradiction worker
  - reducer/planner worker

### JEPA-020 — Beginner ingress / one-door workflow

- Make `seed` the obvious product entrypoint
- Optimize for:
  - zero folder discipline
  - vague human intent
  - "continue yesterday's thing" queries
- Hide machine nouns unless the user opts into them

### JEPA-021 — Headless seed execution

- Add a one-shot product surface analogous to `jepa`/`portal` internals
- Likely shape:
  - `lgwks seed exec <prompt|key>`
- Requirements:
  - text output by default
  - structured output mode for agents/automation
  - safe-by-default continuation behavior

### JEPA-022 — Readiness report artifact

- Emit a durable readiness report per repo/package
- Include:
  - package completeness
  - repo binding quality
  - contradiction density
  - continuation safety level
  - suggested autonomy ceiling

### JEPA-023 — Preview gates for irreversible actions

- Add preview/apply flow for higher-risk continuations
- Show:
  - planned mutations
  - sampled outputs
  - unresolved uncertainty
- Promote only after explicit approval or policy match

### JEPA-024 — Silent-failure checks

- Detect when expected sources, crawls, bindings, or refreshes stop updating
- Prefer explicit degraded state over false success

### JEPA-025 — Agent-readable package publishing

- Make package artifacts easier for external agents to consume directly
- Candidate surfaces:
  - package index text
  - `llms.txt`-style seed summary
  - stable machine-readable capability/resource descriptions

### JEPA-026 — Explicit scope contract

- Require higher-risk commands to emit intended scope before mutation
- Include:
  - files
  - resources
  - external calls
  - expected artifacts

### JEPA-027 — Dry-run / preview mode for seed workflows

- Add preview support to `seed continue` and related commands
- Surface:
  - planned edits
  - repo refresh targets
  - validations
  - unresolved warnings

### JEPA-028 — Typed machine errors with next actions

- Replace ambiguous prose errors on agent-facing surfaces
- Errors should recommend:
  - retry
  - narrow scope
  - request approval
  - abort

### JEPA-029 — Evidence pack contract

- Standardize artifact bundle emitted by important runs
- Minimum contract:
  - intent
  - scope
  - plan
  - validations
  - warnings
  - final side effects

## Research issues

### JEPA-R01 — Thesis validation for `H1`

- Do multi-view packages improve retrieval and next-step quality?

### JEPA-R02 — Thesis validation for `H2`

- Does latent alignment reduce wording sensitivity?

### JEPA-R03 — Thesis validation for `H5`

- Does deterministic CLI control reduce token and compute burden?

### JEPA-R04 — Gate to full LLM-JEPA training

- Only proceed if package-level controls show real wins
