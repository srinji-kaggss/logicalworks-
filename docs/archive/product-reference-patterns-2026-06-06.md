---
type: Archive
title: Product Reference Patterns — 2026-06-06
description: Purpose: record useful product/runtime patterns from external references without copying branding, wording, or visual structure.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Product Reference Patterns — 2026-06-06

Purpose: record useful product/runtime patterns from external references without copying branding, wording, or visual structure.

## References reviewed

1. Factory docs
- https://docs.factory.ai/welcome
- useful for:
  - headless execution
  - autonomy levels
  - readiness reports
  - skills/subagents as versioned files
  - mission-style orchestration

2. Termdock beginner guide
- https://www.termdock.com/en/blog/ai-cli-beginner-guide
- useful for:
  - beginner ingress framing
  - terminal fear reduction
  - "describe intent, get working result" promise
  - one obvious door for non-engineers

3. Simon Beauloye site and essays
- requested URL returned `404` during review, so the live site and related essays were used instead:
  - https://simonbeauloye.com/
  - https://simonbeauloye.com/writing/bootstrapping/zero-base-operations/
  - https://simonbeauloye.com/writing/building-with-ai/ai-building-failures/
- useful for:
  - agent-readable publishing surfaces (`llms.txt`, agent-oriented layers)
  - operator-first workflow design
  - "human experience / opinion / data" as the moat above commodity models
  - preview/review gates for confident-but-wrong automation

4. Propel Code agent-first CLI design
- https://www.propelcode.ai/blog/agent-first-cli-design-coding-agents
- useful for:
  - structured output first
  - explicit pre-execution scope
  - first-class dry-run and diff preview
  - introspectable capabilities
  - typed errors with next actions
  - evidence packs as review artifacts

5. huko
- https://github.com/alexzhaosheng/huko
- useful for:
  - project-scoped agent state
  - conversational setup that chooses defaults from intended use
  - explicit compaction tiers
  - lean tool surface
  - per-tool safety and sandboxable execution

6. gloomberb
- https://github.com/vincelwt/gloomberb
- useful for:
  - dense multi-pane visual context
  - keyboard-first drill-down
  - command bar as global jump surface
  - extensible pane/plugin surface

7. OpenBB
- https://github.com/OpenBB-finance/OpenBB
- useful for:
  - one infrastructure layer serving many consumption surfaces
  - "connect once, consume everywhere" product framing
  - agent-facing, API-facing, and human-facing surfaces over one core platform

8. miii-cli
- https://github.com/maruakshay/miii-cli
- useful for:
  - local-first execution posture
  - goal-directed context compaction
  - repo-local instruction overlays

9. syswatch
- https://github.com/matthart1983/syswatch
- useful for:
  - dense multi-tab observability
  - timeline + replay
  - plain-English anomaly cards
  - one terminal surface replacing many scattered tools

10. db-git
- https://github.com/earthcomfy/db-git
- useful for:
  - branch-affined local state
  - shared vs per-branch storage modes
  - git-hook-driven sync without blocking checkout

## Direct implications for lgwks

1. `seed` should be the default product noun
- not because it is pretty
- because it hides the machine ontology until the user needs it

2. `seed continue` should have both interactive and headless forms
- interactive for BAU collaboration
- headless for automation and repeatable continuations

3. readiness should become an artifact, not a vibe
- the system should be able to say whether a repo/package is safe for:
  - read-only continuation
  - edit continuation
  - mission continuation

4. beginner success is not "understands JEPA"
- beginner success is:
  - dumped context
  - system routed it
  - came back later
  - continuation started without chat archaeology

5. operator success is not "the model sounded smart"
- operator success is:
  - the system exposed what it would change
  - quiet failures had checks
  - higher-risk continuations had preview gates
  - human review sat at the irreversible boundary

6. the moat is above the model layer
- commodity model access is not enough
- durable advantage comes from:
  - accumulated context packages
  - schema libraries
  - gold-standard corpora
  - outcome-linked event history

7. agent-first CLI quality is review quality
- if the machine surface is ambiguous, reviewers inherit the ambiguity
- `lgwks` commands should be judged by whether a later reviewer or agent can reconstruct:
  - intent
  - scope
  - planned operations
  - validations
  - final side effects

8. setup should compile human intent into config
- a good setup flow does not ask for low-level knobs first
- it asks what kind of work the user wants to do, then selects defaults
- this fits the `seed` thesis better than manual config-first onboarding

9. dense visuals can be a context compressor for humans
- the human analogue to a compact machine packet is not more prose
- it is a map with distinct panes and drill-down paths

10. the infrastructure layer should not be surface-bound
- one core layer should feed:
  - CLI
  - visual workbench
  - machine packets
  - future APIs and agent surfaces

11. humans need anomaly cards, not only graphs
- dense visuals are necessary but insufficient
- the system should also emit plain-language cards for:
  - contradictions
  - stale bindings
  - failed refreshes
  - risky continuations

12. local state should be branch-aware where it matters
- some package/resource/cache state should track the active branch
- one mode will not fit every repo

13. compaction should preserve mission relevance, not just shorten text
- the point is not “smaller context”
- the point is “retain what still matters for the current goal”

## Translation rule

Keep the external pattern. Rewrite the interface in `lgwks` language.
