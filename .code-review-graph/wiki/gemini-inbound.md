# gemini-inbound

## Overview

Directory-based community: lgwks_inbound

- **Size**: 12 nodes
- **Cohesion**: 0.1295
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| InboundError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 57-58 |
| est_tokens | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 65-70 |
| _serialize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 73-75 |
| _dense_rank | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 82-85 |
| fuse | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 88-119 |
| build_pack | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 133-200 |
| assemble | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 161-180 |
| assemble_inbound | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 203-264 |
| _resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 230-234 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 271-291 |
| _cmd_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 294-348 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py | 351-357 |

## Execution Flows

- **_cmd_run** (criticality: 0.40, depth: 2)

## Dependencies

### Outgoing

- `print` (11 edge(s))
- `add_argument` (5 edge(s))
- `list` (5 edge(s))
- `append` (4 edge(s))
- `getattr` (3 edge(s))
- `dumps` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_cap_holds_fuzz` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_truncation_order_and_survival` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestRealGraph.test_real_graph_only_fusion_cap_and_no_prose` (3 edge(s))
- `rank_graph` (2 edge(s))
- `read` (2 edge(s))
- `get_record` (2 edge(s))
- `set_defaults` (2 edge(s))
- `len` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_determinism` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_inbound.py` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_cap_holds_fuzz` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_truncation_order_and_survival` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestRealGraph.test_real_graph_only_fusion_cap_and_no_prose` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_determinism` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestRealGraph.test_real_graph_fusion_deterministic` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_zero_dangling_handles` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_dangling_graph_cid_excluded` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_space_mismatch_surfaces` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestAssembleEndToEnd.test_graph_only_no_query` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestTenantScopedInbound.test_cross_tenant_nodes_dropped` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestTenantScopedInbound.test_tenant_store_path_avoids_raw_tenant_resolver` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_no_prose_fuzz` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestPackProperties.test_empty_pack_under_cap` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_inbound.py::TestRRFMath.test_two_list_fusion` (1 edge(s))
