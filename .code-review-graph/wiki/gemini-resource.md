# gemini-resource

## Overview

Directory-based community: lgwks_ingest

- **Size**: 12 nodes
- **Cohesion**: 0.1465
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _ResourceHarvester | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 61-86 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 65-68 |
| _add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 70-75 |
| handle_starttag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 77-86 |
| _classify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 89-103 |
| _fetch_page | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 106-139 |
| _is_wall | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 154-173 |
| _embed_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 176-184 |
| ingest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 187-291 |
| _embed_media_resource | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 294-303 |
| _vrows | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 306-320 |
| _emit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py | 323-326 |

## Execution Flows

- **ingest** (criticality: 0.45, depth: 2)

## Dependencies

### Outgoing

- `get` (30 edge(s))
- `strip` (7 edge(s))
- `append` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_substrate_io.py::_sha` (6 edge(s))
- `len` (5 edge(s))
- `startswith` (4 edge(s))
- `lower` (4 edge(s))
- `search` (4 edge(s))
- `Path` (3 edge(s))
- `urlparse` (3 edge(s))
- `dumps` (3 edge(s))
- `render` (3 edge(s))
- `sub` (3 edge(s))
- `str` (3 edge(s))
- `split` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_ingest.py` (10 edge(s))
