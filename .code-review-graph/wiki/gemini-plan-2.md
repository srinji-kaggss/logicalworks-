# gemini-plan

## Overview

Directory-based community: lgwks_project_plan

- **Size**: 3 nodes
- **Cohesion**: 0.0769
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| worker_cap | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_plan.py | 45-47 |
| build_plan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_plan.py | 53-108 |
| plan_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_plan.py | 111-119 |

## Execution Flows

- **deploy_command** (criticality: 0.54, depth: 3)
- **plan_command** (criticality: 0.45, depth: 2)

## Dependencies

### Outgoing

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_clamp` (4 edge(s))
- `join` (3 edge(s))
- `str` (2 edge(s))
- `dumps` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_terms` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_slug` (1 edge(s))
- `time` (1 edge(s))
- `len` (1 edge(s))
- `min` (1 edge(s))
- `mkdir` (1 edge(s))
- `write_text` (1 edge(s))
- `print` (1 edge(s))
- `compute_worker_cap` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_plan.py` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::deploy_command` (1 edge(s))
