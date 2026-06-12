# gemini-read

## Overview

Directory-based community: lgwks_substrate_io

- **Size**: 9 nodes
- **Cohesion**: 0.0000
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 18-20 |
| _slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 23-26 |
| _read_jsonl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 29-43 |
| _emit_jsonl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 46-51 |
| _emit_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 54-57 |
| _json_cell | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 60-62 |
| _iter_text_files | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 65-77 |
| _read_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 80-85 |
| _load_run_manifest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py | 88-96 |

## Execution Flows

- **_crawl_site** (criticality: 0.55, depth: 2)
- **_vector_search** (criticality: 0.48, depth: 2)
- **ingest** (criticality: 0.45, depth: 2)
- **_build_index_db** (criticality: 0.43, depth: 1)
- **_upsert_global_fact_vectors** (criticality: 0.43, depth: 1)

## Dependencies

### Outgoing

- `dumps` (3 edge(s))
- `read_text` (3 edge(s))
- `mkdir` (2 edge(s))
- `len` (2 edge(s))
- `lower` (2 edge(s))
- `append` (2 edge(s))
- `exists` (2 edge(s))
- `loads` (2 edge(s))
- `strip` (2 edge(s))
- `write_text` (1 edge(s))
- `open` (1 edge(s))
- `write` (1 edge(s))
- `rglob` (1 edge(s))
- `any` (1 edge(s))
- `relative_to` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py::ingest` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_db.py::_upsert_global_fact_vectors` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py::_vrows` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_db.py::_build_index_db` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_vector.py::_stored_vector_space` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py::_embed_media_resource` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_crawl.py::append_doc` (1 edge(s))
