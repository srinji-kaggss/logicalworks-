# tests-no

## Overview

Directory-based community: tests

- **Size**: 2347 nodes
- **Cohesion**: 0.1615
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| hello | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/fixtures/crate/src/lib.rs | 2-4 |
| Widget | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/fixtures/crate/src/lib.rs | 10-20 |
| new | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/fixtures/crate/src/lib.rs | 11-15 |
| greet | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/fixtures/crate/src/lib.rs | 17-19 |
| helper | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/fixtures/crate/src/lib.rs | 23-25 |
| _StepClock | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 40-50 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 43-45 |
| __call__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 47-50 |
| TestStabilitySweep | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 57-139 |
| _run_load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 66-90 |
| test_half_load_stable | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 92-108 |
| test_overload_no_5xx | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 110-129 |
| test_queue_full_bounded | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 131-139 |
| TestIdempotentShed | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 146-164 |
| test_duplicate_cid_one_row | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 149-157 |
| test_different_cids_multiple_rows | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 159-164 |
| TestTyped429 | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 171-208 |
| test_rate_limited_is_rejected429 | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 174-184 |
| test_rate_limited_retry_after_deterministic | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 186-197 |
| test_queue_full_is_rejected429 | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 199-208 |
| TestZero5xx | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 215-226 |
| test_no_exception_on_any_input | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 218-226 |
| TestReplayable | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 233-249 |
| _run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 236-244 |
| test_two_runs_identical | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 246-249 |
| TestTokenBucket | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 256-280 |
| test_initial_full | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 259-265 |
| test_refills_over_time | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 267-274 |
| test_invalid_params | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_admission.py | 276-280 |
| TestAgentOs | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 13-195 |
| setUp | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 14-51 |
| _git | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 53-56 |
| _init_git_repo | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 58-64 |
| _write_agent | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 66-70 |
| test_bootstrap_context_writes_links_and_cards | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 72-86 |
| test_doctor_reports_green_when_bundle_complete | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 88-99 |
| _mk_orch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 104-113 |
| test_orchestrator_scans_agent_manifests | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 115-119 |
| test_orchestrator_spawn_creates_worktree_with_inputs | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 121-137 |
| test_orchestrator_collect_reads_output | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 139-146 |
| test_orchestrator_collect_reports_pending_when_no_output | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 148-152 |
| test_orchestrator_spawn_two_agents_no_collision | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 154-168 |
| test_orchestrator_close_removes_worktree | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 170-177 |
| test_orchestrator_spawn_unknown_agent_raises | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 179-183 |
| test_orchestrator_spawn_git_fail_audit_and_raise | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_agent_os.py | 185-195 |
| _fake_vector | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_apple_provider.py | 32-36 |
| TestAppleAvailability | Class | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_apple_provider.py | 43-67 |
| test_is_available_returns_bool | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_apple_provider.py | 44-46 |
| test_unavailable_on_non_darwin | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_apple_provider.py | 48-56 |
| test_unavailable_when_mlx_missing | Test | /Users/srinji/logicalworks-/.worktrees/gemini/tests/test_apple_provider.py | 58-67 |

*... and 2297 more members.*

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `assertEqual` (1152 edge(s))
- `assertTrue` (410 edge(s))
- `Path` (377 edge(s))
- `assertIn` (360 edge(s))
- `unittest.TestCase` (308 edge(s))
- `len` (239 edge(s))
- `patch` (225 edge(s))
- `write_text` (189 edge(s))
- `TemporaryDirectory` (173 edge(s))
- `assertFalse` (165 edge(s))
- `str` (143 edge(s))
- `any` (134 edge(s))
- `object` (118 edge(s))
- `range` (117 edge(s))
- `dumps` (109 edge(s))

### Incoming

- `assertEqual` (1149 edge(s))
- `assertTrue` (406 edge(s))
- `assertIn` (359 edge(s))
- `Path` (305 edge(s))
- `len` (226 edge(s))
- `patch` (219 edge(s))
- `assertFalse` (165 edge(s))
- `TemporaryDirectory` (163 edge(s))
- `write_text` (151 edge(s))
- `any` (132 edge(s))
- `object` (110 edge(s))
- `loads` (105 edge(s))
- `str` (99 edge(s))
- `assertRaises` (93 edge(s))
- `read_text` (88 edge(s))
