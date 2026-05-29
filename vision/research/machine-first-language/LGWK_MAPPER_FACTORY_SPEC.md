# LGWK Mapper Factory Spec

Version: `lgwk-mapper-factory/0.1`

This spec keeps the mapper model-agnostic. The deterministic crawl/map kernel is the product boundary; models are replaceable factories.

## Factory Interfaces

### CrawlFactory

Input:

```json
{"source":"file|folder|url","limits":{"max_files":160,"max_pages":40,"max_bytes":250000}}
```

Output:

```json
{"documents":[{"uid":"sha256","title":"","source":"","kind":"","text":"","tokens":[],"meta":{}}]}
```

Required behavior:

- Must terminate under configured limits.
- Must produce stable document IDs for unchanged inputs.
- Must not require network services for local file/folder sources.
- URL crawling is allowed, but must use local code and bounded traversal.

### MapFactory

Input: documents plus run prompt.

Output: `jarvis-schema.json` with:

- `system_manifest`
- `mathematical_coordinate_space`
- `network_topology_graph.nodes`
- `network_topology_graph.edges`

Required behavior:

- Node identity is SHA-256 over structural pattern.
- Ambiguous nodes are sandboxed.
- Relationships are typed before visual rendering.
- The schema remains valid without model output.

### GenerationFactory

Input: prompt plus compact schema summary.

Output:

```json
{"text":"one question or final synthesis"}
```

Provider names:

- `deterministic`
- `ollama`
- future: `apple-foundation-models`
- future: `coreml`
- future: `mlx`

Required behavior:

- Missing provider must fall back to deterministic behavior.
- Question generation returns exactly one deeper production/blindspot question.
- Final synthesis cannot directly promote sandboxed nodes.

### EmbeddingFactory

Input:

```json
{"text":"","dims":256}
```

Output:

```json
{"embedding":[],"provider":"","model":"","dimensions":0}
```

Provider names:

- `deterministic`: feature-hash vector, always available.
- `ollama`: local model endpoint, default `qwen3-embedding:8b`.
- future: `apple-foundation-models`
- future: `coreml`
- future: `mlx`

Required behavior:

- Embeddings are local.
- Failed neural embedding falls back to deterministic embedding.
- Embeddings are stored per document in `embeddings.jsonl`.

### PromotionFactory

Input: schema, final guide, triage answers.

Output:

- promoted stream rows in `notes/os-intel.jsonl`
- triage rows in `notes/mapper-triage.jsonl`

Required behavior:

- Triage can be speculative.
- OS intel cannot be speculative.
- Sandboxed nodes stay out of the OS stream unless a future verifier promotes them.

## CLI Contract

```bash
./lgwk mapper <source> \
  --prompt "..." \
  --provider deterministic|ollama \
  --model <generation-model> \
  --final-provider deterministic|ollama \
  --final-model <stronger-generation-model> \
  --embed-provider deterministic|ollama \
  --embed-model qwen3-embedding:8b
```

Recommended Qwen setup:

```bash
./lgwk mapper <url> \
  --prompt "Map this website into OS nodes" \
  --provider deterministic \
  --final-provider deterministic \
  --embed-provider ollama \
  --embed-model qwen3-embedding:8b
```

This keeps reasoning deterministic while using Qwen only for local embeddings.

## Controlled Swarm Target

The next factory layer should add `SwarmFactory`:

```json
{
  "workers": 4,
  "max_workers": 10,
  "max_depth": 10,
  "state": "stateless-worker",
  "merge": "deterministic-parent"
}
```

Worker contract:

- Each worker receives one URL node plus depth budget.
- Each worker emits documents and candidate edges only.
- Parent process deduplicates by SHA-256 and applies promotion rules.
- Workers never mutate `notes/os-intel.jsonl` directly.

## OS Rule

Models provide imagination and compression. Factories provide law.

