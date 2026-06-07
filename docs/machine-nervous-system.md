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

