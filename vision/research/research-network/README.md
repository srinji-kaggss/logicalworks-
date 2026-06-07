# LGWKS Research Network

This folder is the local research database framework for machine-first language work. It turns websites into object-storage artifacts, SQLite rows, embedding vectors, and graph files without depending on a hosted research agent.

## Command

Run a deep website expedition:

```bash
./lgwks website --seed-file vision/research/research-network/seeds/gnn-compiler-expedition.json --name gnn-compiler-expedition --max-pages 12
```

Run against one site:

```bash
./lgwks website https://distill.pub/2021/gnn-intro/ --name distill-gnn --max-pages 8
```

Inspect local research storage:

```bash
./lgwks drive status
```

## What It Writes

Each expedition writes a run folder under `vision/research/research-network/runs/`:

- `raw/` - markdown captured by `crwl`.
- `records/` - normalized JSONL documents, chunks, nodes, and edges.
- `db/research.sqlite` - relational index over sources, documents, chunks, nodes, edges, and embeddings.
- `graph/research-map.mmd` - Mermaid relationship graph.
- `graph/research-map.html` - self-contained graph inspector.
- `logs/commands.jsonl` - exact crawler commands and outcomes.
- `REPORT.md` - top concepts, strongest semantic links, and crawl failures.
- `run-manifest.json` - checksums, model metadata, limits, and generated artifact paths.

Generated runs are gitignored. Schemas, seed packs, and command code are tracked.

## Model Boundary

The crawler and graph builder are deterministic. Ollama embeddings are used when available, with `qwen3-embedding:8b` as the default. If embedding fails, the pipeline falls back to deterministic feature-hash vectors so the DB and graph still build.

Reasoning/advisory generation is optional and uses an OpenRouter model id when configured. Set `LGWKS_TONGUE_MODEL` or pass `--reasoning-model` / `--model`; use `none` to record no reasoning model. Research ingestion stays independent from interpretation.

## Why This Exists

The goal is not a prettier bookmark folder. It is a research substrate where graph structure naturally emerges:

- source pages become document nodes;
- text chunks become semantic nodes;
- recurring technical phrases become concept nodes;
- cosine similarity creates semantic edges;
- co-occurrence creates candidate ontology edges;
- schemas and DB tables make the result auditable and rerunnable.

This makes the research base usable by humans, local models, future GNN experiments, and compiler passes.
