# gemini-classify

## Overview

Directory-based community: lgwks_intent_router

- **Size**: 8 nodes
- **Cohesion**: 0.1200
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _load_tinybert | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 59-76 |
| _get_router | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 82-86 |
| _heuristic_classify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 89-111 |
| classify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 114-168 |
| route | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 171-208 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 215-221 |
| _route_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 224-260 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py | 263-270 |

## Execution Flows

- **main** (criticality: 0.39, depth: 4)
- **_route_command** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `print` (12 edge(s))
- `any` (8 edge(s))
- `round` (4 edge(s))
- `len` (3 edge(s))
- `getattr` (3 edge(s))
- `add_argument` (3 edge(s))
- `time` (3 edge(s))
- `from_pretrained` (2 edge(s))
- `dumps` (2 edge(s))
- `item` (2 edge(s))
- `lower` (1 edge(s))
- `load_model` (1 edge(s))
- `isatty` (1 edge(s))
- `strip` (1 edge(s))
- `read` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_router.py` (9 edge(s))
