# gemini-merge

## Overview

Directory-based community: lgwks_crdt

- **Size**: 35 nodes
- **Cohesion**: 0.1923
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| GSet | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 51-81 |
| add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 63-65 |
| merge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 67-69 |
| value | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 71-73 |
| __eq__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 75-78 |
| __repr__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 80-81 |
| ORSet | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 89-150 |
| add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 104-110 |
| remove | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 112-123 |
| merge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 125-133 |
| value | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 135-142 |
| __eq__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 144-147 |
| __repr__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 149-150 |
| LWWRegister | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 158-191 |
| set | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 169-173 |
| merge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 175-179 |
| value | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 181-182 |
| __eq__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 184-188 |
| __repr__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 190-191 |
| merge_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 198-204 |
| serialise | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 211-234 |
| deserialise | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 237-248 |
| ConvergenceSink | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 262-271 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 269-269 |
| commit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 271-271 |
| JsonFileSink | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 274-308 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 281-282 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 284-288 |
| commit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 290-296 |
| locked | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 299-308 |
| _sink_lock | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 312-319 |
| reconverge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 322-349 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 356-366 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 369-383 |
| _cmd_merge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py | 386-408 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_divergent_replicas_converge_byte_identical_regardless_of_order` (12 edge(s))
- `frozenset` (11 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_lww_scalar_converges_to_dominant_clock_through_sink` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_entity_graph.py::TestEntityGraphQueries.test_edge_membership_add_wins_across_divergent_replicas` (10 edge(s))
- `get` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_reconverge_across_restart_accumulates` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_orset_remove_survives_concurrent_add_through_sink` (9 edge(s))
- `items` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_reconverge_is_idempotent_on_replay` (6 edge(s))
- `isinstance` (6 edge(s))
- `dict` (4 edge(s))
- `print` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_gset_roundtrip` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_type_mismatch_raises` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_first_run_starts_empty_then_persists` (3 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_crdt.py` (13 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_divergent_replicas_converge_byte_identical_regardless_of_order` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_lww_scalar_converges_to_dominant_clock_through_sink` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_entity_graph.py::TestEntityGraphQueries.test_edge_membership_add_wins_across_divergent_replicas` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_reconverge_across_restart_accumulates` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_orset_remove_survives_concurrent_add_through_sink` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_reconverge_is_idempotent_on_replay` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_gset_roundtrip` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_type_mismatch_raises` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.test_first_run_starts_empty_then_persists` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_lww_roundtrip` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestSerialiseRoundtrip.test_orset_roundtrip` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestReconvergePersistence.worker` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestLWWDeterminism._run` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_crdt.py::TestLWWDeterminism.test_no_wallclock_dependency` (2 edge(s))
