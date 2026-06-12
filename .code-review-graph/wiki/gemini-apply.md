# gemini-apply

## Overview

Directory-based community: lgwks_sqlite

- **Size**: 16 nodes
- **Cohesion**: 0.3333
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _apply_pragmas | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 32-56 |
| connect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 59-118 |
| ConnectionPool | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 121-193 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 132-146 |
| _make_conn | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 148-149 |
| acquire | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 151-162 |
| release | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 164-176 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 178-187 |
| __enter__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 189-190 |
| __exit__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 192-193 |
| MigrationManager | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 196-275 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 208-209 |
| init | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 211-222 |
| current_version | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 224-230 |
| apply | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 232-268 |
| is_applied | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py | 270-275 |

## Execution Flows

- **acquire** (criticality: 0.63, depth: 3)
- **apply** (criticality: 0.61, depth: 1)
- **release** (criticality: 0.49, depth: 1)
- **__exit__** (criticality: 0.45, depth: 1)

## Dependencies

### Outgoing

- `execute` (10 edge(s))
- `RuntimeError` (4 edge(s))
- `get` (4 edge(s))
- `fetchone` (3 edge(s))
- `Path` (2 edge(s))
- `commit` (2 edge(s))
- `Queue` (1 edge(s))
- `Lock` (1 edge(s))
- `put` (1 edge(s))
- `executescript` (1 edge(s))
- `info` (1 edge(s))
- `rollback` (1 edge(s))
- `error` (1 edge(s))
- `int` (1 edge(s))
- `upper` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_sqlite.py` (4 edge(s))
