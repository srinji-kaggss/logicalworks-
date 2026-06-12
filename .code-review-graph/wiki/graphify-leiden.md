# graphify-leiden

## Overview

Directory-based community: graphify

- **Size**: 9 nodes
- **Cohesion**: 0.2000
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| LeidenUnavailableError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 21-43 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 29-43 |
| ClusterResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 47-69 |
| as_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 59-69 |
| cluster | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 72-113 |
| _run_leiden | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 118-156 |
| _run_louvain | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 161-187 |
| _to_igraph | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 192-206 |
| _leidenalg_importable | Function | /Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py | 209-214 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `len` (3 edge(s))
- `float` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_deterministic_with_seed` (2 edge(s))
- `RuntimeError` (1 edge(s))
- `super` (1 edge(s))
- `find_partition` (1 edge(s))
- `louvain_communities` (1 edge(s))
- `sorted` (1 edge(s))
- `modularity` (1 edge(s))
- `list` (1 edge(s))
- `nodes` (1 edge(s))
- `enumerate` (1 edge(s))
- `Graph` (1 edge(s))
- `is_directed` (1 edge(s))
- `add_vertices` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/graphify/cluster.py` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_leiden_runs_and_result_carries_leiden` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_no_silent_fallback_raises_leiden_unavailable` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_deterministic_with_seed` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_leiden_communities_cover_all_nodes` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_force_louvain_runs_and_marks_forced` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_result_metadata_carries_py_version` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_graphify_cluster.py::test_as_dict_is_json_serializable` (1 edge(s))
