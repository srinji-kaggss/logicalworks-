# gemini-records

## Overview

Directory-based community: lgwks_project_deploy

- **Size**: 17 nodes
- **Cohesion**: 0.1529
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _worker_leases | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 55-74 |
| _token_ledger | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 77-87 |
| _critic_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 90-107 |
| _model_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 110-123 |
| _model_lineage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 126-148 |
| _machine_packets | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 151-176 |
| _graph_edges | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 179-206 |
| _learning_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 209-236 |
| _operator_profile | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 239-277 |
| _worker_map | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 280-294 |
| _embedding_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 297-312 |
| _artifact_embeddings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 315-327 |
| _event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 330-342 |
| _source_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 345-368 |
| _deploy_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 375-377 |
| _run_non_ml_execution | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 380-456 |
| deploy_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py | 459-563 |

## Execution Flows

- **deploy_command** (criticality: 0.54, depth: 3)
- **review_command** (criticality: 0.45, depth: 2)

## Dependencies

### Outgoing

- `get` (19 edge(s))
- `append` (17 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::jsonl` (14 edge(s))
- `dumps` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_sha` (7 edge(s))
- `str` (6 edge(s))
- `time` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::write_json` (5 edge(s))
- `type` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_clamp` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py::_terms` (3 edge(s))
- `write_text` (3 edge(s))
- `items` (2 edge(s))
- `prompt_ref` (2 edge(s))
- `join` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py` (17 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_review.py::review_project` (1 edge(s))
