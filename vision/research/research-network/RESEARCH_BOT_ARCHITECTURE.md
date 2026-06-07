# LGWKS Research AI Bot Architecture

The research bot is not one agent. It is a governed research system with separated powers.

## Core Split

1. **Hunter**
   - Accepts an exact architectural framework from the user.
   - Builds a seed pack from source catalogs, arXiv search URLs, and explicit URLs.
   - May use AI to propose source gaps, but those proposals are stored as advisory artifacts only.

2. **Crawler**
   - Uses `crwl` to acquire documents.
   - Writes raw markdown and command logs.
   - Does not interpret claims.

3. **Compiler**
   - Normalizes documents into chunks, nodes, edges, DB rows, Mermaid, HTML, and tensor exports.
   - Must be deterministic.
   - AI cannot compile, promote, or mutate graph facts.

4. **Embedding Layer**
   - Uses local `qwen3-embedding:8b` where available.
   - Embeddings are vectors, not truth.
   - Similarity edges are candidate structure only.

5. **Expert Advisory**
   - Optionally uses a user-selected OpenRouter reasoning model.
   - Follows a co-scientist loop: generate, critique, rank, evolve, ground, human-review.
   - Follows Constitutional AI discipline: state principle, critique, revise, log.
   - Follows tabula-rasa discipline: separate observations from interpretations and minimize assumptions.
   - Writes to `advisory/`, never to graph tables.

6. **GNN Activation**
   - Starts from deterministic tensor export under `gnn/`.
   - Later experiments can train PyTorch Geometric, DGL, or NetworkX models.
   - The GNN may learn over the graph, but it does not define the graph.

## CyberStrikeAI Patterns Imported

From `/Users/srinji/CyberStrikeAI`, the useful patterns are architectural, not offensive:

- YAML-style tool manifests with names, descriptions, parameters, enable flags, and execution boundaries.
- SQLite-backed audit logs with query/export support.
- HITL interrupt model: pending decisions, approval/edit/reject, timeout, and durable status.
- Non-blocking event bus for long-running tasks.
- Knowledge-base layout where source material is first-class and searchable.
- Role/skill separation through progressive disclosure.

Those map cleanly into this repo:

- `logs/commands.jsonl` is the audit stream.
- `run-manifest.json` is the durable run contract.
- `schemas/` are the typed tool/data contracts.
- `advisory/` is the AI sandbox.
- `db/research.sqlite` is the local object index.
- `gnn/` is the deterministic graph-learning export.

## Commands

Plan from an architectural framework:

```bash
./lgwks bot plan "co-scientist GNN compiler research bot with deterministic graph compilation" --name coscientist-bot
```

Crawl and compile the generated seed:

```bash
./lgwks website --seed-file vision/research/research-network/runs/<run>/plan/seed.json --name coscientist-bot
```

Rebuild deterministic graph visuals:

```bash
./lgwks graph export latest
```

Export GNN-ready tensors:

```bash
./lgwks graph tensorize latest
```

Ask the expert advisory layer without mutating graph facts:

```bash
./lgwks expert latest --question "What research gaps should we crawl next?"
```

## Governance Rule

The bot can learn where to look. It cannot decide what is true.

Truth promotion happens through deterministic evidence, schema validation, and human acceptance.
