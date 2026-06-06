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
