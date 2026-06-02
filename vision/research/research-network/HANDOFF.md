# LGWKS Research Network Handoff

Date: 2026-05-31
Branch: `feat/harden-vision-adr067-a2a`

## Current State

The repo now has a local research-network command layer for machine-first language and graph research.

Primary command:

```bash
./lgwks
```

Tracked framework files:

- `lgwks` - root command wrapper.
- `vision/research/research-network/lgwks_research.py` - crawler, DB builder, embedding mapper, graph export, tensor export, advisory prompt builder.
- `vision/research/research-network/schemas/` - source, document, node, edge, run, policy, and advisory schemas.
- `vision/research/research-network/seeds/` - reusable source seed packs.
- `vision/research/research-network/tools/lgwks-research-bot.yaml` - CyberStrikeAI-style tool manifest.
- `vision/research/research-network/RESEARCH_BOT_ARCHITECTURE.md` - system architecture and authority split.
- `vision/research/research-network/CYBERSTRIKEAI_PATTERN_LOG.md` - imported/rejected CyberStrikeAI patterns.

Generated research runs are stored under:

```bash
vision/research/research-network/runs/
```

That folder is intentionally gitignored. It behaves as local object storage, while Git versions the schemas, command code, policies, and seeds.

## Completed Local Runs

### GNN/compiler expedition

Run folder:

```bash
vision/research/research-network/runs/gnn-compiler-expedition-20260531-141016
```

Counts:

- Sources: 12
- Documents: 9
- Chunks: 132
- Embedded chunks: 132
- Nodes: 293
- Edges: 1555

Artifacts:

- `REPORT.md`
- `run-manifest.json`
- `db/research.sqlite`
- `graph/research-map.mmd`
- `graph/research-map.html`
- `gnn/nodes.csv`
- `gnn/edges.csv`
- `gnn/features.jsonl`
- `gnn/tensor-manifest.json`

### Co-scientist research-bot expedition

Run folder:

```bash
vision/research/research-network/runs/coscientist-research-bot-20260531-142318
```

Counts:

- Sources: 10
- Documents: 10
- Chunks: 92
- Embedded chunks: 90
- Nodes: 252
- Edges: 1206

Artifacts:

- `REPORT.md`
- `run-manifest.json`
- `db/research.sqlite`
- `graph/research-map.mmd`
- `graph/research-map.html`
- `gnn/nodes.csv`
- `gnn/edges.csv`
- `gnn/features.jsonl`
- `gnn/tensor-manifest.json`

The 90 embedded chunks are from the configured `--max-total-chunks 90`; the remaining chunks are still stored as text records.

## Command Contract

Plan from an exact architecture:

```bash
./lgwks bot plan "DeepMind co-scientist GNN visual compiler with tabula rasa evidence discipline" --name my-run
```

Crawl and compile from a seed:

```bash
./lgwks website --seed-file vision/research/research-network/seeds/coscientist-research-bot.json --name coscientist-research-bot
```

Rebuild graph visuals deterministically:

```bash
./lgwks graph export latest
```

Export deterministic GNN tensors:

```bash
./lgwks graph tensorize latest
```

Generate AI advisory only:

```bash
./lgwks expert latest --question "What research gaps should we crawl next?"
```

Inspect local object storage:

```bash
./lgwks drive status
```

## Authority Boundary

AI can propose sources, hypotheses, critiques, and research gaps.

AI cannot compile or mutate graph facts.

Deterministic code owns:

- DB rows
- chunk records
- node records
- edge records
- Mermaid/HTML graph output
- GNN tensor exports

Embeddings are coordinates, not truth. Similarity edges are candidate structure, not promoted claims.

## CyberStrikeAI Pattern Import

Useful architecture patterns imported from `/Users/srinji/CyberStrikeAI`:

- YAML tool manifests.
- SQLite audit/persistence.
- HITL approval model.
- non-blocking task event bus.
- role/skill separation.
- knowledge-base-as-durable-records.

Rejected:

- offensive tool execution.
- C2/session primitives.
- arbitrary shell/Python execution from research output.
- AI-controlled graph mutation.

## Validation Performed

Commands run:

```bash
python3 -m py_compile vision/research/research-network/lgwks_research.py
for f in vision/research/research-network/schemas/*.json vision/research/research-network/seeds/*.json; do python3 -m json.tool "$f" >/dev/null || exit 1; done
./lgwks graph export latest --max-nodes 90 --max-edges 180
./lgwks graph tensorize latest
./lgwks drive status --limit 10
git diff --check
git diff --cached --check
```

All passed.

## Git Actions Completed

- Created commit `451d037 vision: add local research network bot`.
- Fetched `origin`.
- Merged `origin/main` into `feat/harden-vision-adr067-a2a`.
- Merge commit created: `db44b7d Merge remote-tracking branch 'origin/main' into feat/harden-vision-adr067-a2a`.

Current branch was ahead of `origin/feat/harden-vision-adr067-a2a` after the merge. This handoff should be committed on top.

## Next Build Slice

1. Add a `promote` command for human-approved claim promotion.
2. Add a `crawl-only` mode and a `compile` mode so acquisition and graph compilation can be run independently.
3. Add cluster labeling that is deterministic by default and advisory-only when model-assisted.
4. Add NetworkX/PyTorch Geometric example loaders for `gnn/`.
5. Add per-source content filters so navigation boilerplate does not become concept noise.
