# gemini-stage

## Overview

Directory-based community: lgwks_pipeline

- **Size**: 44 nodes
- **Cohesion**: 0.1442
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| PipelineChunk | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 102-112 |
| EmbedResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 116-123 |
| RankedChunk | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 127-137 |
| NoiseRecord | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 141-145 |
| _cosine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 152-155 |
| _l2_norm | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 158-160 |
| _vec_mean | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 163-172 |
| _weighted_centroid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 175-186 |
| _first_principal_component | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 189-207 |
| _tokenize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 239-242 |
| bm25_score | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 245-269 |
| compute_fact_density | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 272-278 |
| compute_noise_score | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 281-313 |
| extract_chunk_entities | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 316-323 |
| entity_overlap_score | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 326-335 |
| _resolve_text_provider | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 343-358 |
| embed_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 361-372 |
| _read_substrate_dims | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 375-387 |
| _mm_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 390-392 |
| embed_multimodal | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 395-439 |
| _sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 451-453 |
| _chunk_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 456-457 |
| _iter_substrate_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 460-522 |
| _iter_url_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 525-551 |
| _iter_jsonl_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 554-587 |
| _iter_csv_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 590-613 |
| _iter_dir_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 616-668 |
| iter_dataset | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 671-695 |
| _gemma_paraphrase | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 709-740 |
| disambiguate_chunk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 743-776 |
| recall_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 783-798 |
| fast_rank_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 805-834 |
| heavy_rank_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 841-873 |
| rerank_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 880-919 |
| pack_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 927-1014 |
| _get_research_start | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1021-1039 |
| research_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1042-1082 |
| cleanup_stage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1089-1108 |
| _parameter_snapshot | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1115-1136 |
| run_pipeline | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1143-1417 |
| _embed_one | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1223-1236 |
| _run_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1424-1449 |
| _params_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1452-1454 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py | 1457-1484 |

## Execution Flows

- **_run_command** (criticality: 0.40, depth: 4)

## Dependencies

### Outgoing

- `len` (48 edge(s))
- `get` (33 edge(s))
- `print` (30 edge(s))
- `str` (27 edge(s))
- `append` (17 edge(s))
- `max` (17 edge(s))
- `round` (16 edge(s))
- `sum` (13 edge(s))
- `strip` (11 edge(s))
- `dumps` (9 edge(s))
- `min` (9 edge(s))
- `loads` (8 edge(s))
- `float` (8 edge(s))
- `exists` (7 edge(s))
- `add_argument` (7 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_pipeline.py` (45 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_pipeline.py::TestPipeline.test_compute_noise_score` (1 edge(s))
