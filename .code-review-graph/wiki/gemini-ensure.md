# gemini-ensure

## Overview

Directory-based community: lgwks_cache

- **Size**: 10 nodes
- **Cohesion**: 0.1786
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _ensure | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 29-30 |
| _hash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 33-34 |
| _path_for | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 37-40 |
| _safe_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 43-53 |
| put | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 56-69 |
| has | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 72-76 |
| get_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 79-90 |
| get_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 93-95 |
| entries | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 98-109 |
| status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py | 112-115 |

## Execution Flows

- **get_text** (criticality: 0.43, depth: 2)
- **put** (criticality: 0.41, depth: 1)

## Dependencies

### Outgoing

- `exists` (4 edge(s))
- `len` (3 edge(s))
- `mkdir` (2 edge(s))
- `str` (2 edge(s))
- `hexdigest` (1 edge(s))
- `sha256` (1 edge(s))
- `fullmatch` (1 edge(s))
- `ValueError` (1 edge(s))
- `urlparse` (1 edge(s))
- `split` (1 edge(s))
- `_replace` (1 edge(s))
- `urlunparse` (1 edge(s))
- `splitlines` (1 edge(s))
- `read_text` (1 edge(s))
- `strip` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cache.py` (10 edge(s))
