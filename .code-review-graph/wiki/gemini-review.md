# gemini-review

## Overview

Directory-based community: lgwks_do

- **Size**: 19 nodes
- **Cohesion**: 0.2266
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _slugify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 31-32 |
| PhaseResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 40-46 |
| DoRun | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 50-82 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 61-82 |
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 85-86 |
| _build_review_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 89-109 |
| _run_review | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 112-138 |
| _run_aup_check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 141-170 |
| _run_aup_audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 173-188 |
| _do_code | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 195-215 |
| _do_research | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 218-287 |
| _do_govern | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 290-323 |
| _do_cleanup | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 326-352 |
| _do_ship | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 355-379 |
| _run_refactor | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 386-400 |
| _verdict_from_phases | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 403-413 |
| _emit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 416-439 |
| do_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 446-459 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py | 462-511 |

## Execution Flows

- **do_command** (criticality: 0.46, depth: 3)

## Dependencies

### Outgoing

- `getattr` (28 edge(s))
- `add_argument` (27 edge(s))
- `time` (20 edge(s))
- `append` (18 edge(s))
- `str` (12 edge(s))
- `get` (8 edge(s))
- `print` (7 edge(s))
- `Path` (6 edge(s))
- `round` (5 edge(s))
- `max` (5 edge(s))
- `set_defaults` (5 edge(s))
- `resolve` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py::_is_repo` (4 edge(s))
- `float` (4 edge(s))
- `spine` (4 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py` (18 edge(s))
