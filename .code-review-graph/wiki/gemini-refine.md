# gemini-refine

## Overview

Directory-based community: lgwks_machine

- **Size**: 16 nodes
- **Cohesion**: 0.1340
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| classify_intent | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 61-69 |
| detect_gaps | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 72-76 |
| specificity | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 79-89 |
| _entities | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 92-100 |
| _questions | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 103-114 |
| _authority | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 117-136 |
| refine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 139-178 |
| _log_coverage_gap | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 181-190 |
| _log_commit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 193-204 |
| refine_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 209-225 |
| _state_hash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 228-229 |
| snapshot | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 232-239 |
| freeze | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 242-246 |
| _frozen | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 249-251 |
| _brier | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 254-259 |
| promote | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py | 262-270 |

## Execution Flows

- **snapshot** (criticality: 0.44, depth: 1)
- **refine_command** (criticality: 0.40, depth: 2)

## Dependencies

### Outgoing

- `print` (6 edge(s))
- `lower` (5 edge(s))
- `round` (4 edge(s))
- `sum` (4 edge(s))
- `get` (4 edge(s))
- `len` (3 edge(s))
- `findall` (3 edge(s))
- `append` (3 edge(s))
- `dumps` (3 edge(s))
- `max` (3 edge(s))
- `mkdir` (3 edge(s))
- `min` (3 edge(s))
- `getattr` (3 edge(s))
- `CognitionLog` (2 edge(s))
- `items` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_machine.py` (16 edge(s))
