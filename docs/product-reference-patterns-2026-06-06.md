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

## Translation rule

Keep the external pattern. Rewrite the interface in `lgwks` language.
