# gemini-url

## Overview

Directory-based community: lgwks_extract

- **Size**: 16 nodes
- **Cohesion**: 0.2544
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _bin | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 42-43 |
| _trim | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 46-47 |
| _ext_of | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 50-52 |
| _is_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 55-56 |
| _is_http_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 59-60 |
| _host_is_blocked | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 63-85 |
| _remote_allowed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 88-89 |
| _headers | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 92-99 |
| _SafeRedirectHandler | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 103-134 |
| redirect_request | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 107-134 |
| _opener | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 137-139 |
| _pdf | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 142-159 |
| _office | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 162-168 |
| _html | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 176-211 |
| _download | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 214-229 |
| extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py | 232-276 |

## Execution Flows

- **redirect_request** (criticality: 0.49, depth: 2)
- **extract** (criticality: 0.40, depth: 3)

## Dependencies

### Outgoing

- `urlparse` (6 edge(s))
- `Path` (5 edge(s))
- `lower` (4 edge(s))
- `Request` (4 edge(s))
- `open` (3 edge(s))
- `strip` (3 edge(s))
- `exists` (3 edge(s))
- `read` (2 edge(s))
- `note_auth_failure` (2 edge(s))
- `str` (2 edge(s))
- `run` (2 edge(s))
- `sub` (2 edge(s))
- `decode` (2 edge(s))
- `bool` (2 edge(s))
- `read_text` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_extract.py` (15 edge(s))
