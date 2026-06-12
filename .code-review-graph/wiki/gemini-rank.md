# gemini-rank

## Overview

Directory-based community: lgwks_rank

- **Size**: 16 nodes
- **Cohesion**: 0.0984
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| RankError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 45-46 |
| RankRecord | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 99-117 |
| build_tensor | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 128-196 |
| _set | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 152-155 |
| _l2_norm | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 205-206 |
| _normalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 209-215 |
| _sparse_matvec | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 218-234 |
| power_iteration | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 237-313 |
| compute_delta | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 331-358 |
| _to_f32 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 366-368 |
| _centrality | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 371-390 |
| _ranks_from | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 393-400 |
| rank_graph | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 403-448 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 456-470 |
| _cmd_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 473-525 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py | 528-536 |

## Execution Flows

- **_cmd_run** (criticality: 0.39, depth: 4)

## Dependencies

### Outgoing

- `print` (17 edge(s))
- `get` (11 edge(s))
- `len` (8 edge(s))
- `items` (7 edge(s))
- `getattr` (4 edge(s))
- `range` (4 edge(s))
- `add_argument` (4 edge(s))
- `sum` (3 edge(s))
- `enumerate` (3 edge(s))
- `max` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_seed_stability_synthetic` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_seed_stability_real` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestDeterminismReplay.test_shift_preserves_eigenvector_ranking` (3 edge(s))
- `abs` (3 edge(s))
- `sqrt` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_rank.py` (16 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_seed_stability_synthetic` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_seed_stability_real` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestDeterminismReplay.test_shift_preserves_eigenvector_ranking` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_convergence_synthetic` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_convergence_lw_graph` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestPowerIteration.test_convergence_os_graph` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestOrderCollapse.test_order_collapse` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestDeterminismReplay.test_determinism_synthetic` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestDeterminismReplay.test_determinism_real` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestRRFMath._rr` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestBuildTensor.test_nodes_indexed` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestBuildTensor.test_symmetrized` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestBuildTensor.test_confidence_weight` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_rank.py::TestDeltaDistribution._check_graph` (1 edge(s))
