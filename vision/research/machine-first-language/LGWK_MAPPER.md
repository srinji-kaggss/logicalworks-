# LGWK Mapper

`lgwk mapper` is the local OS ingestion loop. It rebuilds the useful crawler/research-agent pattern for this app without depending on Firecrawl, ctx7, or external APIs.

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

Each run writes to `artifacts/lgwk-mapper/<run-id>/`:

- `documents/` - normalized markdown documents from the source.
- `jarvis-schema.json` - structural graph schema with SHA-256 node ids, hyperbolic coordinates, binary buffers, security perimeter, and typed edges.
- `relationship-outputs.json` - final relationship list plus triage answers.
- `final-guide.md` - final OS-focused implementation guide.
- `embeddings.jsonl` - local deterministic embeddings for retrieval.
- `run-manifest.json` - run metadata and termination state.

It also appends promoted, non-sandboxed OS intel to `notes/os-intel.jsonl` and keeps speculative questions in `notes/mapper-triage.jsonl`.

Provider contract lives in `LGWK_MAPPER_FACTORY_SPEC.md`.

## Lifecycle

1. Give a source and prompt.
2. Mapper crawls the source locally.
3. Mapper creates the Jarvis-style schema.
4. Mapper asks one deeper production/blindspot question.
5. You answer, or type `terminate`.
6. On termination it writes final relationship outputs, final guide, embeddings, and promoted stream notes.

## Design Rule

Triage is allowed to be speculative. The OS stream is not. A structure can stay as a candidate node in triage until the final synthesis promotes it, bins it down a level, or leaves it sandboxed.
