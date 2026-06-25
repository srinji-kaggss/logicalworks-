---
type: Archive
title: OSS Porting Notes — Mac Native + JEPA References
description: Date: 2026-06-06
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# OSS Porting Notes — Mac Native + JEPA References

Date: 2026-06-06

## Purpose

Decide what external open-source work can be ported into `lgwks`, under what license posture, and at what layer.

## Verified license posture

### JosefAlbers

- `mlx-code`: Apache-2.0
  - Source: repo page shows Apache-2.0 license and raw LICENSE confirms Apache 2.0.
  - URLs:
    - https://github.com/JosefAlbers/mlx-code
    - https://raw.githubusercontent.com/JosefAlbers/mlx-code/main/LICENSE
- `pvm` / `Phi-3-MLX`: MIT
  - Source: repo page shows MIT license and raw LICENSE confirms MIT.
  - URLs:
    - https://github.com/JosefAlbers/pvm
    - https://raw.githubusercontent.com/JosefAlbers/pvm/main/LICENSE

### alexzhaosheng

- `huko`: MIT
  - Source: repo page shows MIT license.
  - URLs:
    - https://github.com/alexzhaosheng/huko

### maruakshay

- `miii-cli`: MIT
  - Source: repo page shows MIT license.
  - URLs:
    - https://github.com/maruakshay/miii-cli

### matthart1983

- `syswatch`: MIT
  - Source: repo page shows MIT license.
  - URLs:
    - https://github.com/matthart1983/syswatch

### earthcomfy

- `db-git`: MIT
  - Source: repo page shows MIT license.
  - URLs:
    - https://github.com/earthcomfy/db-git

### ginwind

- `VLA-JEPA`: no verified license captured from the repo surface during this pass
  - Treat as research inspiration only for now
  - URL:
    - https://github.com/ginwind/VLA-JEPA

## What is actually useful

### From `mlx-code`

The strongest reusable patterns are product/runtime patterns:

1. Harness split
- separate `Agent`, `Tool`, and REPL pieces
- useful for `lgwks` because `seed/jepa/capture/portal` should be callable as library surfaces and shell surfaces

2. Backend seam
- local server, remote provider, or OpenAI-compatible endpoint
- useful for future `lgwks start` / `seed continue` shells

3. Git worktree isolation
- every session gets a fresh worktree
- useful for safe continuation runs and agent re-entry

4. Resume from checkpoint
- resume by commit/session state
- useful analogue for `seed:` / `jepa:` / `portal:` restoration

5. Pipe-friendly CLI
- shell-native composition matters
- useful for low-friction product intake

### From `pvm`

The strongest reusable patterns are Apple-first packaging patterns:

1. Mac-native local install story
2. MLX-first Apple Silicon runtime posture
3. clean command entrypoint for multimodal local execution

This is useful for future local JEPA/router execution on Apple Silicon.

### From `VLA-JEPA`

The strongest reusable ideas are research/architecture ideas, not immediate code ports:

1. latent world model above the action layer
2. explicit separation of base VLM and JEPA/world-model encoder
3. benchmark-driven evaluation against perturbation/task suites

This should influence:

- our hypothesis structure
- our control ladder
- our eventual temporal/event evaluation design

It should not yet influence direct code import.

### From `huko`

The strongest reusable patterns are agent-shell and setup patterns:

1. Project-scoped state
- state lives under a repo-local directory
- useful analogue for `seed`/`jepa` session state and continuation history

2. Chat-based setup that selects defaults
- user describes intended usage
- system chooses compaction, safety, and feature defaults
- useful for `lgwks seed setup` or `lgwks start`

3. Configurable compaction as a first-class product knob
- not just model context size, but explicit compaction tiers
- useful for package projection and continuation stream sizing

4. Lean tool surface
- fewer tools exposed to the model by default
- useful reinforcement for `lgwks` machine-contract discipline

5. Per-tool safety and sandbox wrapper
- allow/deny/confirm per tool
- sandboxed wrapper mode for risky continuation
- useful for future `seed continue --sandbox` and readiness tiers

### From `miii-cli`

The strongest reusable patterns are local context-governance patterns:

1. Local-first execution posture
- the agent runs on the user's machine by default
- useful reinforcement for the `lgwks` local-first moat

2. Goal-directed context compaction
- keep task-relevant context, not raw tool transcript ballast
- useful for continuation packet sizing and portal compilation

3. Repo-local instruction overlay
- a project instruction file steers the local agent
- useful analogue for repo-local `seed` and continuation policy overlays

### From `syswatch`

The strongest reusable patterns are human observability patterns:

1. Dense multi-tab observability
- many system slices visible without opening many tools
- useful for the JEPA visual workbench

2. Timeline + replay
- session history is scrub-able, not just current-state only
- useful for continuation replay and handoff radar

3. Plain-English anomaly cards
- heuristics become immediately legible operator signals
- useful for contradiction/risk/readiness cards

### From `db-git`

The strongest reusable patterns are branch-affined local-state patterns:

1. State follows branch checkout
- branch switch triggers local state reconciliation
- useful for repo-local JEPA/portal/resource state

2. Shared vs per-branch modes
- one state store with snapshots, or one state store per branch
- useful for continuation history, local caches, and future substrate snapshots

3. Hook-driven but non-blocking sync
- integrate with branch changes without making checkout brittle
- useful for future `lgwks` git-aware state refresh behavior

## Porting map into lgwks

### Port now

1. Worktree-isolated continuation shell
- inspired by `mlx-code`
- maps to `seed continue`

2. resumable session/package shell
- inspired by `mlx-code`
- maps to `seed continue <query|key> --resume`

3. backend-seamed local shell
- inspired by `mlx-code`
- maps to `lgwks start` or future harness shell

4. Apple Silicon local runtime posture
- inspired by `pvm`
- maps to future MLX router / local package predictor

5. Project-scoped continuation memory
- inspired by `huko`
- maps to repo-local `seed` state and continuation history

6. Conversational setup that compiles to machine config
- inspired by `huko setup`
- maps to `seed setup` / `lgwks start`

7. Compaction tiers
- inspired by `huko`
- maps to machine/human projection budgets and continuation packet sizing

8. Goal-directed context compaction
- inspired by `miii-cli`
- maps to continuation packets that preserve relevance rather than transcript bulk

9. Visual anomaly/radar workbench
- inspired by `syswatch`
- maps to dense human observability surfaces for package/repo state

10. Branch-affined local state sync
- inspired by `db-git`
- maps to repo-local caches, portal state, and future branch-aware resource snapshots

### Translate first, port later

1. REPL command vocabulary
- keep the idea of shell affordances
- do not mirror the exact interface

2. model-server bootstrap pattern
- keep the local-first startup flow
- translate into `lgwks` machine language

### Do not port directly now

1. `VLA-JEPA` training/eval code
- different problem domain
- unclear repo license posture during this pass
- useful as research direction, not a drop-in

## Machine-language translation

External OSS ideas should be rewritten into `lgwks` terms:

- `resume from commit` -> `resume from seed/jepa/portal package`
- `agent harness` -> `continuation shell`
- `tool list` -> `machine capability surface`
- `session worktree` -> `isolated continuation workspace`
- `VLA world model` -> `package/world-model predictor`

## Immediate product implication

The strongest near-term addition is:

- a Mac-native continuation shell
- worktree-isolated
- resumable from package keys
- backend-seamed

This fits the product thesis better than importing more model code.
