---
type: Reference
title: Machine Nervous System
description: This document describes the intended end-to-end runtime for lgwks after the
tags: [reference]
timestamp: 2026-06-09T18:24:42-04:00
---

# Machine Nervous System

This document describes the intended end-to-end runtime for `lgwks` after the
Jarvis/Substrate bridge. It is written for coding agents first. Human interfaces
should be thin TUI/frontends over the same machine contracts.

## One-Line Shape

```
intent/site/repo -> capture -> substrate -> embeddings -> graph/index -> memory/JEPA package -> query/reason
```

The durable product is not a chat answer. The durable product is a typed,
replayable local substrate: manifests, chunks, vectors, graph artifacts, and
machine packets that later agents can inspect without trusting raw web content.

## Runtime Lanes

### 1. Intake

Inputs can be:

- site URL
- local file/folder/repo
- operator intent
- multiple views of the same target

For a site URL, the primary command is:

```bash
lgwks --machine jarvis crawl <url>
```

Jarvis is only the compatibility/front-door command. URL crawls delegate to
`lgwks_substrate.build_run()`.

### 2. Capture

Capture turns ambient input into explicit machine records:

- target
- project/run id
- auth policy
- browser policy
- chunking policy
- embedding policy
- artifact paths

No model should be needed to capture. Capture is an audit boundary.

### 3. Substrate Build

Substrate does the mechanical work:

- fetch/crawl or read local content
- normalize source and document records
- chunk text
- extract lightweight facts/stems
- build graph input rows
- write run artifacts
- write `manifest.json`

Artifacts live under `store/substrate/<run_id>/`.

### 4. Embedding

Embedding should always write a semantic lane for new substrate builds when a
semantic provider is available. Deterministic vectors should remain available as
a second lane for audit, lexical collision detection, and offline fallback.

Recommended policy:

- `semantic`: required-by-default for site/repo substrate recall.
- `deterministic`: always allowed as an auxiliary/audit lane.
- `deterministic-only`: explicit offline/fail-safe mode, never silently labeled
  as semantic.

Semantic and deterministic vectors mean different things:

- Semantic vectors come from learned model weights. They encode meaning-like
  proximity and support semantic retrieval.
- Deterministic feature-hash vectors come from token hashing. They encode
  lexical/surface overlap and are reproducible without model weights.

Do not compare vectors across spaces unless the manifest says the space matches.
The vector-space descriptor in `manifest.json` is the authority.

### 5. Graph And Index

Substrate writes two complementary structures:

- `graph.json` / `graph.db`: relationships between documents, chunks, entities,
  and facts.
- `substrate.db`: searchable index over sources, documents, chunks, facts, and
  vectors.

Graph edges must label their evidence source. A lexical/hash edge is not a
semantic edge.

### 6. BERT / Small Encoder

BERT-class models do not belong in the crawl path by default.

Their correct role is closed-set classification and routing:

- intent classification
- command/schema routing
- safety gate classification
- cheap local TUI/backend routing

Tiny-BERT/DistilBERT should answer: "which known command/schema is this?" They
should not be the main retrieval embedding for site knowledge unless explicitly
trained and evaluated for that retrieval task.

**Live status (2026-06-09).** The L1 intent membrane (`lgwks_intent_classifier`) is
functional: it routes through the Qwen Eye (semantic, method `eye`) with a deterministic
fallback, and its 175-verb centroids are cached (`store/intent/`, 201s→0.09s load).
Calibration is margin-based — the top1−top2 separation, not the absolute cosine, gates
abstention (gibberish → `plan_only`). On top of L1, the **Human Assumption Decoder**
(`lgwks_had`) turns an utterance into a typed intent + a scored assumption ledger that
abstains to human review on low confidence or risky verbs. Two more owned organs landed
alongside: `lgwks_algorithms` (L4 narrow-ML: spike/trend/logistic, deferral registry) and
`lgwks_sast` (a real CFG + flow-sensitive taint static-review engine, 6 CWE classes live).
See `spec/second-harness/BUILDLOG-model-stack.md` for the build log + deferral ledger.

### 7. JEPA

The current `lgwks jepa` is a runtime package surface, not a trained JEPA model.

Its correct near-term role:

- collect multiple views of a target
- align shared anchors across views
- bind capture/substrate/portal artifacts
- produce a machine packet and human projection

The future trained JEPA role is different:

- learn latent state transitions
- predict missing/next view representations
- detect surprise/drift between expected and observed substrate state

Do not call the current package builder a trained JEPA predictor.

### 8. LLM / Tongue

LLMs are optional reasoning/advisory tools.

They should:

- read manifests and selected evidence packets
- produce hypotheses, summaries, or next actions
- write advisory artifacts

They should not:

- mutate graph facts directly
- decide vector-space compatibility
- replace deterministic capture
- become required for crawl/index

Current policy: OpenRouter is the optional generation seam; local Ollama is the
embedding Eye only.

## Site URL End-To-End

```bash
lgwks --machine jarvis crawl https://example.com \
  --max-pages 12 \
  --max-depth 2 \
  --embed-provider ollama
```

Expected flow:

1. CLI parses machine args.
2. Jarvis detects URL source.
3. Jarvis builds substrate args.
4. Substrate crawls the site.
5. Auth wall detection may trigger browser handoff.
6. Documents are normalized.
7. Chunks and facts are generated.
8. Semantic vectors are written using the requested provider.
9. Deterministic audit vectors should be written if dual-lane mode is enabled.
10. Graph and substrate DB are built.
11. Manifest records the exact vector spaces and artifact paths.
12. CLI emits only JSON.

## Target Architecture

The backend should treat the CLI as a stable RPC surface:

- no spinners/progress text in `--machine`
- JSON in, JSON out where practical
- no human wording in machine paths
- TUI reads machine JSON and renders it for humans
- backend can call the same commands without terminal assumptions

The CLI is not the product UI. It is the control bus.

## Runtime Language Split

The current implementation is Python-heavy because the system is still
contract-discovery heavy:

- model setup and training use PyTorch/Transformers/CoreMLTools/MLX-class tools;
- browser/auth/crawl glue changes quickly;
- substrate schemas and machine JSON contracts are still being stabilized;
- tests can cover behavior faster than an FFI boundary can be designed.

That is not the final compute posture. The intended split is:

| Layer | Current | Target | Reason |
|---|---|---|---|
| CLI/control bus | Python | Python or thin Rust wrapper | Contract orchestration, subprocess glue, JSON surface |
| Model training | Python | Python/MLX/PyTorch | Training libraries, autograd, CoreML export tooling |
| Model inference adapters | Python | CoreML/MLX/Ollama/OpenRouter ports | Provider-specific, swappable |
| Content hashing / CID | Rust island exists under `axiom/rust` | Rust | Small, deterministic, security-sensitive |
| Canonical wire/schema validation | Python today | Rust | Stable, low-level, audit-critical |
| Substrate indexing/search hot path | Python/SQLite today | Rust service/library where measured | Throughput, memory, concurrency |
| Graph algorithms | Python today | Rust where graph size justifies it | Traversal/search hot path |
| Browser automation/auth | Python today | Keep behind provider port | Browser APIs dominate cost; optimize only after contract stabilizes |
| TUI | not built | Rust or native frontend over JSON | Human rendering only; no business logic |

So Python is not the optimization answer; it is the current integration and
training lane. Rust should absorb stable, deterministic, high-throughput, or
security-sensitive pieces once their data contracts stop moving.

Do not rewrite the whole system in Rust. Move seams in this order:

1. content-addressing / canonical wire / schema validation;
2. substrate JSONL -> SQLite/index writer;
3. vector search and graph traversal hot paths;
4. long-running backend daemon if the CLI becomes too process-heavy.

Keep model training in Python/MLX/PyTorch. CoreML is a deployment artifact, not
a training framework. Rust can call frozen model artifacts later, but it should
not be the first training runtime.

## Open Decisions

1. Should every new substrate build write dual lanes by default:
   semantic + deterministic?
2. Should `jarvis crawl <url>` default to semantic now that `qwen3-embedding:8b`
   is downloaded?
3. Which semantic provider should be canonical on Apple Silicon:
   Ollama, MLX, CoreML, or another local server?
4. Should BERT be promoted only for intent routing, or also for cheap local
   entity/type classification?
5. What should count as a JEPA package promotion: repeated anchors, substrate
   graph agreement, or a future trained predictor score?
6. Which substrate hot path should be the first Rust migration:
   canonical wire/schema, index writer, vector search, or graph traversal?
