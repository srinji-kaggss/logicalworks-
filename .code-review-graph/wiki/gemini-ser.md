# gemini-ser

## Overview

Directory-based community: lgwks_admission_store

- **Size**: 15 nodes
- **Cohesion**: 0.2188
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _ser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 73-74 |
| _deser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 77-78 |
| DurableAdmissionQueue | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 81-314 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 89-114 |
| _connect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 117-130 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 132-133 |
| _verified_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 136-140 |
| _active_tenants | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 142-147 |
| fair_ceiling | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 149-151 |
| enqueue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 154-195 |
| lease | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 198-247 |
| complete | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 250-267 |
| reap | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 270-289 |
| depth | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 292-299 |
| leased_count | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py | 301-314 |

## Execution Flows

- **__init__** (criticality: 0.48, depth: 1)
- **enqueue** (criticality: 0.43, depth: 1)

## Dependencies

### Outgoing

- `execute` (32 edge(s))
- `fetchone` (9 edge(s))
- `int` (5 edge(s))
- `max` (3 edge(s))
- `_clock` (3 edge(s))
- `ValueError` (2 edge(s))
- `connect` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py::Admitted` (2 edge(s))
- `ceil` (2 edge(s))
- `compute_worker_cap` (1 edge(s))
- `Path` (1 edge(s))
- `mkdir` (1 edge(s))
- `str` (1 edge(s))
- `executescript` (1 edge(s))
- `commit` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_durable_queue.py::_Base._q` (1 edge(s))
