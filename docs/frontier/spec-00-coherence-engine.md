---
type: Spec
title: SPEC-00 — The Coherence Engine (more than a compiler)
description: AI code generation already compiles.
tags: [frontier, spec]
timestamp: 2026-06-02T16:48:56-04:00
---

# SPEC-00 — The Coherence Engine (more than a compiler)

> The core contribution. Read MAP.md first. Audience: Kimi build agents + orchestrating AI.

## L0 — Intent

AI code generation already compiles. That is the easy 80%. The failures that remain are the ones
a compiler is structurally blind to:

| Observed failure | Plain description | Root cause |
|---|---|---|
| **Architectural drift** | locally correct, globally incoherent; each generation wanders from the established structure | the model generates locally (next-token, file-at-a-time) with **no enforced model of the whole system** |
| **"Weird" / non-idiomatic** | technically fine but not how this team/codebase writes it | the model emits the **mean of all code it ever saw**, not *this* repo's conventions |
| **Framework-blind** | calls APIs that don't exist, or exist only in an old version; ignores real idioms | training cutoff + averaged knowledge; **no live grounding in the installed surface** |
| **Intent miss** | builds the wrong thing correctly | intent was never formalized into a checkable spec |

The Coherence Engine makes each of these into an explicit **gate** that runs *around* any generator.
It is not a generator. It is the layer that grounds generation before, and checks it after.

## L1 — Reality gap

These properties are *softer* than type-checking. Some have hard oracles (does this API symbol
exist in the vendored version? yes/no). Some are only scorable (is this idiomatic? 0–1). The engine
must be honest about which is which — enforce the hard ones to 100%, surface the soft ones as a
calibrated report. Conflating the two is the oversimplification sin; pretending idiom is 100% is a lie.

## L2 — Mechanism: the gate pipeline

Generation (from any model, free or the orchestrating AI) flows through gates in order. Each gate
is a `Verifier` (spec-01). Hard gates **reject → retry**; advisory gates **score → surface**.

```
intent ──[G4 human/AI confirms spec]──► spec
spec   ──► GENERATOR (any model) ──► candidate code
candidate ─► G0 compiler/types/formal ─► G1 architecture ─► G3 framework-reality ─► G2 idiom ─► ship
              (HARD, reject)              (HARD where         (HARD, reject)        (ADVISORY,
                                           invariant exists)                         report)
```

| Gate | Checks | Oracle | Class | Forks from |
|---|---|---|---|---|
| **G0** Compiler / type / formal | syntax, types, memory safety, functional contracts | `rustc`, `cargo test`, Kani/Creusot/Prusti | **HARD 100%** | existing tools |
| **G1** Architecture | conforms to layering / ownership / trust-boundary rules | rule checker over `arch-rules.json` (spec-03 U5) | **per-rule HARD\|ADVISORY declared in `arch-rules.json`** (never chosen at runtime) | `arch-rules.json` (canvas-motion ER rules added later) |
| **G2** Idiom | matches *this repo's* learned conventions (naming, error style, structure) | embedding-distance to repo corpus + lint profile | **ADVISORY** (score only) | cognition-log, repo embeddings |
| **G3** Framework-reality | **version-skew** (symbol exists but at a different installed version than assumed) + **pre-generation grounding** (hand the generator the real installed surface) | `cargo metadata` + rustdoc JSON / ctx7 | **HARD** for version-skew where the extractor is complete; ADVISORY where it is not | dependency lockfile, ctx7 |
| **G4** Intent → spec | the human/AI agrees the spec captures intent | human-in-loop confirmation | **NOT automatable to 100%** | the membrane (model #1) |

> **G3 is NOT "does this symbol exist."** For compiled Rust, `rustc` already rejects a nonexistent symbol
> (E0433/E0425) at **G0** — G3 must not reimplement the compiler. G3's distinct value is (i) *version-skew*
> (the symbol exists but the model assumed a signature from a different version) and (ii) *pre-generation
> grounding* (feed the generator the real surface so it never hallucinates in the first place). On
> non-compiled surfaces (config keys, env vars, external HTTP APIs) G3 also does existence — but on Rust, G0 owns it.

## L3 — Structure that makes drift unviolable

Drift is not "the model forgetting." It is the absence of an *enforced* invariant. The fix is structural:
the architecture is not held in the model's context — it is held in **G1 as a checkable constraint** the
output must satisfy. The model may propose anything; only architecture-conformant output passes. Idiom
is held in G2 as the repo corpus, not the global average. Framework reality is held in G3 as the *vendored*
API surface, not training memory. The model's fallibility becomes invisible because the gates are the truth.

## L4 — Invariants + evidence

- `ship(candidate)` is reachable **only** if every HARD gate returns `pass`. (test: feed code with a
  hallucinated API → G3 rejects → never ships.)
- G2 never blocks; it always returns a calibrated score + a diff-of-idioms report. (test: ECE of the
  idiom score on a held-out set < 0.1.)
- Gate verdicts are append-only in the cognition-log → every ship is auditable (who/what/which gate/verdict).

## L5 — Industry parallel

G0 = CompCert/RustBelt (proven). G3 = the discipline behind language servers + dependency-aware linters,
but applied as a *generation gate*, not an editor hint. The novel composition: the industry does G1/G2/G3
through *human review* — inconsistently, un-scalably, and exactly the thing humans collaborate at badly.
The engine machine-holds the coherence humans cannot maintain together.

## How it serves a context-engineered AI (e.g. the orchestrating model)

The engine is the AI's **context provider and verifier**, the realization of "the CLI is the only skill":
- **Before generation** it hands the AI the relevant ER subgraph (G1), the repo idioms (G2 retrieval),
  and the real framework surface (G3 grounding) — so the AI spends tokens on *reasoning*, not on
  rediscovering the codebase. (Direct token economy: load the AI at 4% and let the tool carry the rest.)
- **After generation** it checks the AI against those same constraints — so the AI *cannot* drift across
  a long session. The engine makes a probabilistic generator behave deterministically at the boundary.

## How it serves a deterministic human

The architecture is explicit and enforced, framework facts are real, output is idiomatic. The coherence
that a team fails to maintain collectively (everyone knowing the real APIs, agreeing on idiom, keeping a
large system structurally sound) is now machine-held and audited. The human supplies entities and
direction (G4); the engine holds the rest.

## Why it is different, not a copy

Copilot / Cursor / et al. improve the **generator** — faster, smoother autocomplete over the mean of
GitHub. They make the same four mistakes faster. The Coherence Engine is **orthogonal**: generator-agnostic
ground + gate. It does not compete to generate better; it makes *any* generator coherent with *this* system
and *real* frameworks. "Improve what's out there" = take the generation everyone already has and add the
coherence layer no one has — and do it with free models, vendor-agnostic. That layer is the moat: it cannot
be reached by scaling a generator, because it is not a generator problem.
