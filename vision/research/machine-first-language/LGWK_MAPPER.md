# LGWK Mapper

`lgwk mapper` is the local OS ingestion loop. It rebuilds the useful crawler/research-agent pattern for this app without depending on Firecrawl, ctx7, or external APIs.

## Current CLI

This repo now exposes the crawler as:

```bash
./lgwks jarvis crawl <website> --keywords "keyword one
keyword two" --max-pages 40 --workers 2
```

Keyword-only mode uses `googler --json` when available:

```bash
./lgwks jarvis crawl "temporal graph neural network crawler" --max-pages 12
```

For URL + keyword runs, add `--search-expansion` to ask `googler` for bounded `site:<host>` expansion queries before the same-site crawl starts.

The command prints an estimated compute time before the crawl and supports dry estimation:

```bash
./lgwks jarvis crawl https://example.com --keywords "protocol;state machine" --estimate-only
```

Legacy expedition databases can be upgraded in place:

```bash
./lgwks jarvis remap-db vision/research/research-network/runs/<run-id>
```

## Command

```bash
./lgwk mapper <file|folder|url> --prompt "what to map"
```

Optional local model:

```bash
LGWK_OLLAMA_MODEL=llama3.1 ./lgwk mapper . --prompt "map OS build blindspots"
```

If no Ollama model is installed, it still runs with deterministic questions and synthesis.

Model-agnostic local Qwen embedding mode:

```bash
./lgwk mapper <url-or-folder> \
  --prompt "map this into OS nodes" \
  --provider deterministic \
  --final-provider deterministic \
  --embed-provider ollama \
  --embed-model qwen3-embedding:8b
```

## Outputs

Each `lgwks jarvis crawl` run writes to `vision/research/research-network/runs/<run-id>/`:

- `documents/` - normalized markdown documents from the source.
- `raw/` - normalized markdown documents from crawled pages.
- `db/research.sqlite` - canonical schema, including separated `understandings` and `question_events`.
- `records/*.jsonl` - append-friendly document/chunk/node/edge exports.
- `gnn/` - `nodes.csv`, `edges.csv`, and `features.jsonl` for graph/transformer experiments.
- `graph/research-map.mmd` and `graph/research-map.html` - quick visual graph output.
- `run-manifest.json` - run metadata and termination state.

It also appends promoted, non-sandboxed OS intel to `notes/os-intel.jsonl` and keeps speculative questions in `notes/mapper-triage.jsonl`.

Provider contract lives in `LGWK_MAPPER_FACTORY_SPEC.md`.

## Lifecycle

1. Give a source and prompt.
2. Mapper crawls the source locally with bounded concurrent workers.
3. Mapper creates chunks, deterministic 256-d embeddings, typed concept nodes, lexical edges, and late-fusion similarity edges.
4. Mapper stores a before/after snapshot pair.
5. Mapper writes research understanding separately from question traces.
6. Mapper emits three deterministic frontier questions per keyword drill, with a `what_were_you_thinking` rationale and separate vector.

## Design Rule

Triage is allowed to be speculative. The OS stream is not. A structure can stay as a candidate node in triage until the final synthesis promotes it, bins it down a level, or leaves it sandboxed.
