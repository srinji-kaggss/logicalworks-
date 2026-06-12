# gemini-url

## Overview

Directory-based community: lgwks_auth_runtime

- **Size**: 13 nodes
- **Cohesion**: 0.1494
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 37-49 |
| _active_sites | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 52-62 |
| _latest_active_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 65-77 |
| _matches | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 80-83 |
| site_for_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 86-91 |
| _safe_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 94-101 |
| request_keyring | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 104-119 |
| rate_floor_seconds | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 122-131 |
| _keychain_secret | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 134-146 |
| _headers_from_secret | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 149-158 |
| auth_policy_for_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 161-184 |
| headers_for_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 187-194 |
| note_auth_failure | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py | 197-199 |

## Execution Flows

- **headers_for_url** (criticality: 0.63, depth: 3)
- **note_auth_failure** (criticality: 0.62, depth: 2)

## Dependencies

### Outgoing

- `get` (9 edge(s))
- `strip` (8 edge(s))
- `lower` (6 edge(s))
- `str` (4 edge(s))
- `startswith` (3 edge(s))
- `split` (3 edge(s))
- `urlparse` (3 edge(s))
- `rstrip` (2 edge(s))
- `group` (2 edge(s))
- `items` (1 edge(s))
- `run` (1 edge(s))
- `endswith` (1 edge(s))
- `exists` (1 edge(s))
- `splitlines` (1 edge(s))
- `read_text` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_auth_runtime.py` (13 edge(s))
