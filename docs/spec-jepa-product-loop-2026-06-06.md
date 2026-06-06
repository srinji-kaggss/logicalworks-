# SPEC — JEPA Product Loop (v0)

Status: proposed and partially implemented  
Scope: replace long raw-chat intent recovery with a package-first human/AI workflow

## 0. Problem

Today, too much intent lives in:

- long chats
- stale memory
- half-remembered links
- repo-local code state
- mental models in the human's head

This creates a massive intent tax:

```text
human wants to continue work
-> agent must recover context from prose
-> repeated token spend
-> wording drift
-> stale repo understanding
-> slop
```

The system should assume **zero discipline from the human**.

## 1. Product promise

The product promise is:

```text
feed messy information during the day
-> lgwks compiles it into a world-model package
-> later, say "let's work on X"
-> agent loads the package, repo graph, and current JEPA understanding
-> agent clarifies fit, hardens what is needed, updates the map, and continues
```

The user should not need to manually preserve continuity.

## 2. Actors

### Human

- dumps thoughts, links, docs, snippets, videos, portals, repo references
- may be inconsistent
- may revisit the same idea with different wording
- may have low operational discipline

### lgwks

- ingests views
- crawls/builds/maps
- routes material to the right folder/run/package
- compiles machine-first artifacts
- emits human projections
- preserves provenance and bindings

### Coding AI

- loads compact technical stream + graph + JEPA package
- clarifies how the current ask fits prior packages and repo state
- uses lgwks for hardening / graph refresh / package update
- continues implementation work

## 3. End-to-end loop

### Mode A — passive daytime intake

Examples:

- links from search
- giant thought dump
- article / video / reel
- "this matters somehow"
- fragments with no clear project yet

Desired behavior:

```text
lgwks seed ingest <views...>
-> normalize
-> crawl/extract
-> package into JEPA seed
-> store machine packet + human packet + resources
-> auto-suggest candidate project bindings
```

### Mode B — BAU project continuation

Examples:

- "let's work on auth"
- "continue the crawler hardening"
- "pick up the research package from yesterday"

Desired behavior:

```text
lgwks seed continue <query or key> --repo <path>
-> resolve best prior package / seed
-> refresh repo graph and changed files
-> emit technical stream for AI
-> emit human fit summary
-> propose hardening actions
-> update map and continue
```

### Mode C — clarification mode

Examples:

- "I clarified my intent better"
- "the original thing was wrong, this is the real angle"

Desired behavior:

```text
lgwks seed refine <key> <new-view>
-> bind the correction as a new view
-> preserve prior package
-> recompute anchors / contradictions / recommended bindings
-> never rewrite history silently
```

## 4. Canonical artifact contract

Every seed/package should produce:

- machine packet
- human projection
- resource index
- repo bindings
- anchor set
- contradictions
- outcome/event ledger

Suggested shape:

```text
store/jepa/
store/captures/
repo/.lgwks/portals/
repo/.lgwks/seeds/
```

Seed packet responsibilities:

- capture views from different times/modalities
- preserve source provenance
- compute shared anchors
- classify candidate project/repo bindings
- expose contradictions and uncertainty
- emit a compact AI-facing stream

## 5. Product surfaces

### Human-first verbs

- `lgwks seed ingest`
- `lgwks seed continue`
- `lgwks seed refine`
- `lgwks seed show`
- `lgwks seed ls`

### Machine-first verbs

- `lgwks jepa build`
- `lgwks jepa show`
- `lgwks jepa doctor`
- `lgwks portal code`
- `lgwks capture build`

Rule:

```text
seed = product language
jepa/capture/portal = machine language
```

## 6. High-level success criteria

The system is successful when:

1. the human can dump messy context without planning file structure
2. the system auto-routes material into stable packages
3. later continuation requires package loading, not chat archaeology
4. coding agents can recover intent with fewer tokens and fewer wrong starts
5. package updates preserve history instead of silently rewriting it

## 7. Current state vs end state

### Current

- `capture` exists
- `portal` exists
- `jepa` runtime package exists
- ML/runtime doctor exists

### Missing

- product-facing `seed` verbs
- auto-routing into per-project seed directories
- event/outcome ledger on seed transitions
- benchmark harness for continuation quality
- trained router / JEPA predictor / temporal GNN

## 8. First build-down path

1. Ship `seed` as a product alias over `jepa/capture/portal`
2. Add seed index + candidate-project binding
3. Add continuation command that emits compact AI stream
4. Add event ledger for `seed -> continue -> outcome`
5. Benchmark against raw-chat continuation

## 9. OSS incorporation policy

Open source should reduce implementation work, but not replace the `lgwks` ontology.

Rules:

1. Port behavior, not branding.
2. Strip developer-facing narrative down to machine/product contracts.
3. Preserve attribution and license obligations.
4. Prefer borrowing seams/patterns over copying repo structure wholesale.
5. Unlicensed or unclear-license repos are research references only, not source donors.

Current assessment:

- `JosefAlbers/mlx-code` is Apache-2.0 and functionally relevant.
- `JosefAlbers/pvm` is MIT and functionally relevant.
- `ginwind/VLA-JEPA` is relevant as a research reference, but no verified repo license is currently locked in this spec, so it should not be treated as a code donor yet.

See also:

- `docs/oss-porting-mac-jepa-2026-06-06.md`

## 10. Product patterns worth absorbing from Factory

Factory is useful here primarily as a product reference for reducing context tax.

Relevant patterns:

1. session search / resume
- search across prior sessions, documents, and tool outputs
- maps to `seed ls` + `seed continue`

2. forkable continuation
- resume one thread, fork it into a new branch of work
- maps to `seed continue --fork`

3. worktree-isolated sessions
- keep risky continuation work out of the main checkout
- maps to the `seed continue` shell and future continuation workspace

4. interactive vs headless symmetry
- one product, two surfaces:
  - interactive continuation
  - non-interactive automation
- maps to `seed continue` and future `seed exec`

5. mission mode
- structured multi-step orchestration with worker roles
- maps to future `seed continue --mission`

6. readiness scoring
- not just "can the agent run?"
- but "is this repo/package mature enough for higher autonomy?"
- maps to a future `seed readiness` / `jepa readiness`

The important point:

```text
we should absorb the continuation ergonomics
without adopting Factory's product language or visual structure
```

## 11. Beginner ingress constraints

The Termdock beginner guide is useful mainly as a reminder that most users do not want a capability map first. They want one obvious door.

Relevant product lessons:

1. one command should feel sufficient
- users should not need to choose between `capture`, `portal`, `jepa`, `substrate`, and `memory`
- this reinforces `seed` as the main product verb

2. the system should assume intent language, not file discipline
- "build this idea", "organize these notes", "continue the thing from yesterday"
- product language must accept vague asks and route them into machine structure

3. basic terminal literacy is a ceiling for beginners
- four-command mental models matter
- product surface should avoid requiring users to reason about paths, worktrees, or schema names up front

4. the core promise is working state, not explanation
- the user should get a package, a continuation path, and a visible next action
- documentation can explain later

Implication for `lgwks`:

```text
seed is not just an alias
it is the anti-tax membrane between human intent and machine ontology
```

## 12. Operator and trust-calibration constraints

As the system gets better, the bottleneck shifts from generation to operator attention.

Relevant product lessons:

1. human-time becomes the new bottleneck
- faster generation does not remove review, routing, or decision pressure
- `lgwks` should optimize operator attention, not just model throughput

2. the moat is not the base model
- durable value comes from:
  - grounding corpora
  - schemas
  - outcome-linked event history
  - human judgement encoded into packages and reviews

3. silent failure is worse than visible failure
- seed/package continuations need checks that surface:
  - missing sources
  - stale repo bindings
  - contradictions
  - unverified transformations

4. confident-but-wrong runs need preview gates
- high-impact actions should support:
  - preview
  - sample review
  - explicit promote/apply

Implication for `lgwks`:

```text
the system should save tokens
but spend operator attention exactly at the irreversible edge
```

## 13. Agent-first CLI constraints

The machine-facing `lgwks` surface should be reviewable by downstream agents and humans without chat reconstruction.

Relevant product lessons:

1. structured output first, prose second
- commands should expose stable machine-readable output
- human summaries are projections, not the primary contract

2. scope before side effects
- higher-risk commands should declare intended files, resources, and external calls before mutation
- unknown scope should fail closed

3. dry-run and preview should be first-class
- users and agents should be able to ask:
  - what will this touch?
  - what will it emit?
  - what validations will run?

4. capabilities should be introspectable
- agent-facing commands should make modes, schemas, and expected artifacts discoverable

5. every important run should emit an evidence pack
- minimum pack:
  - intent
  - scope
  - planned operations
  - validations
  - warnings
  - final outputs

Implication for `lgwks`:

```text
reviewability is not a nice-to-have
it is part of the machine contract
```

## 14. Setup and state constraints

The product should not assume users know which machine defaults matter.

Relevant product lessons:

1. setup should start from intended usage
- ask:
  - what kind of work is this?
  - what repo or project is this for?
  - how risky is the expected continuation?
- then compile that into config

2. state should be project-scoped when possible
- continuation memory, local policies, and package history should bind to the project context
- global state should exist, but local state should dominate during active work

3. compaction should be explicit and controllable
- different tasks need different packet budgets
- `lgwks` should eventually expose compaction tiers for:
  - continuation streams
  - machine projections
  - human projections

4. the tool surface should stay lean
- every additional exposed capability increases ambiguity and token overhead
- disable or hide irrelevant tools from the active continuation surface

Implication for `lgwks`:

```text
good setup is a compiler from human work-shape
to machine defaults and policy
```
