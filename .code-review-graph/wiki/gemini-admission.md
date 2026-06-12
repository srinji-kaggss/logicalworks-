# gemini-admission

## Overview

Directory-based community: lgwks_admission

- **Size**: 28 nodes
- **Cohesion**: 0.2261
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| Admitted | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 59-63 |
| Rejected429 | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 67-73 |
| TokenBucket | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 80-124 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 90-104 |
| _refill | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 106-110 |
| try_acquire | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 112-118 |
| available | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 121-124 |
| AdmissionQueue | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 131-182 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 139-150 |
| submit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 152-168 |
| pop | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 170-174 |
| size | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 177-178 |
| seen_cids | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 181-182 |
| _jitter | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 189-197 |
| admission_decision | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 204-225 |
| TenantAdmissionGate | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 251-380 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 259-301 |
| _lane | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 304-313 |
| _verified_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 315-320 |
| fair_ceiling | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 322-325 |
| admit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 328-351 |
| lease | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 354-368 |
| release | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 370-373 |
| in_flight | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 376-377 |
| tenant_in_flight | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 379-380 |
| make_admission_gate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 387-406 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 413-426 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py | 429-463 |

## Execution Flows

- **available** (criticality: 0.53, depth: 1)
- **admit** (criticality: 0.44, depth: 2)
- **enqueue** (criticality: 0.43, depth: 1)
- **_cmd_info** (criticality: 0.43, depth: 2)
- **lease** (criticality: 0.41, depth: 2)

## Dependencies

### Outgoing

- `getattr` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_queue_full_is_rejected429` (5 edge(s))
- `get` (5 edge(s))
- `ValueError` (4 edge(s))
- `max` (4 edge(s))
- `add_argument` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_rate_limited_is_rejected429` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_rate_limited_retry_after_deterministic` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestZero5xx.test_no_exception_on_any_input` (3 edge(s))
- `len` (3 edge(s))
- `float` (3 edge(s))
- `compute_worker_cap` (2 edge(s))
- `_clock` (2 edge(s))
- `sum` (2 edge(s))
- `values` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission.py` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_queue_full_is_rejected429` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_rate_limited_is_rejected429` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestTyped429.test_rate_limited_retry_after_deterministic` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_admission_store.py::DurableAdmissionQueue.enqueue` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestStabilitySweep._run_load` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestIdempotentShed.test_duplicate_cid_one_row` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestZero5xx.test_no_exception_on_any_input` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestReplayable._run` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_admission_fairness.py::TestNoStarvation.test_flood_by_one_tenant_does_not_block_another` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py::TestIdempotentShed.test_different_cids_multiple_rows` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_admission_fairness.py::TestPerTenantQueue.test_one_tenant_fills_only_its_own_queue` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_admission_fairness.py::TestIdempotentShed.test_duplicate_cid_one_row` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_durable_queue.py::TestCrashDurable.test_rows_survive_reopen` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_durable_queue.py::TestBackpressureIdempotent.test_queue_full_is_backpressure_not_drop` (2 edge(s))
