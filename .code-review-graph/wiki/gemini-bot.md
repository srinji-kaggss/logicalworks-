# gemini-bot

## Overview

Directory-based community: lgwks_project_artifacts

- **Size**: 36 nodes
- **Cohesion**: 0.1859
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 76-78 |
| _terms | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 81-90 |
| _embedding | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 93-102 |
| _sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 105-106 |
| _clamp | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 109-111 |
| jsonl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 114-115 |
| write_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 118-120 |
| deploy_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 123-124 |
| worker_leases | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 133-152 |
| token_ledger | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 155-165 |
| critic_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 168-185 |
| model_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 188-201 |
| model_lineage | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 204-226 |
| machine_packets | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 229-254 |
| graph_edges | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 257-284 |
| _is_str | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 317-318 |
| _is_nonempty_str | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 321-322 |
| _require | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 325-343 |
| _reject_unknown_keys | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 346-347 |
| _is_datetime_str | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 350-355 |
| validate_bot_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 358-504 |
| validate_bot_plan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 507-626 |
| _stable_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 634-635 |
| _canonical_relpath | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 638-643 |
| _dedupe_strings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 646-655 |
| _record_primary_evidence | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 658-661 |
| _normalized_record_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 664-670 |
| _normalize_bot_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 673-690 |
| _merge_bot_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 693-728 |
| _cluster_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 731-740 |
| _blast_radius | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 743-752 |
| _recommended_read | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 755-763 |
| _recommended_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 766-774 |
| reduce_bot_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 777-884 |
| build_jepa_package | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 887-1008 |
| evaluate_artifact_strength | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py | 1011-1067 |

## Execution Flows

- **deploy_command** (criticality: 0.54, depth: 3)
- **plan_command** (criticality: 0.45, depth: 2)
- **validate_bot_plan** (criticality: 0.42, depth: 2)
- **reduce_bot_records** (criticality: 0.39, depth: 3)

## Dependencies

### Outgoing

- `get` (80 edge(s))
- `append` (77 edge(s))
- `extend` (38 edge(s))
- `isinstance` (24 edge(s))
- `list` (17 edge(s))
- `len` (13 edge(s))
- `sorted` (12 edge(s))
- `max` (6 edge(s))
- `encode` (6 edge(s))
- `enumerate` (6 edge(s))
- `round` (5 edge(s))
- `dumps` (5 edge(s))
- `hexdigest` (5 edge(s))
- `sha256` (5 edge(s))
- `replace` (4 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_artifacts.py` (36 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::deploy_command` (18 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_plan.py::build_plan` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_run_non_ml_execution` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_embedding_record` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_operator_profile` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_model_state` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_model_lineage` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_machine_packets` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_source_records` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_project_deploy.py::_learning_records` (1 edge(s))
