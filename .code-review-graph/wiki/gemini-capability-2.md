# gemini-capability

## Overview

Directory-based community: lgwks_capability

- **Size**: 12 nodes
- **Cohesion**: 0.0734
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| CapabilityToken | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 77-91 |
| issue_token | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 98-129 |
| validate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 132-139 |
| _sign | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 142-147 |
| CapabilityError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 154-155 |
| guard | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 158-186 |
| require_scope | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 189-217 |
| make_tenant_filter | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 220-239 |
| _filter | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 231-237 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 246-257 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 260-277 |
| _cmd_issue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py | 280-294 |

## Execution Flows

- **_cmd_issue** (criticality: 0.56, depth: 2)

## Dependencies

### Outgoing

- `sorted` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTenantIsolation.test_no_cross_tenant_leak` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_tenant` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_nonce` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_sig` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_widened_scopes_fail_validation` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_escalated_token_rejected_by_require_scope` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_dropped_scopes_also_fail_validation` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestReservedWorldTenant.test_guard_world_tenant_rejected` (3 edge(s))
- `ValueError` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestValidToken.test_different_keys_cross_validate_fails` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTokenRequired.test_guard_empty_tenant_raises` (2 edge(s))
- `print` (2 edge(s))
- `dumps` (2 edge(s))
- `frozenset` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_capability.py` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestReservedWorldTenant.test_guard_world_tenant_rejected` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_escalated_token_rejected_by_require_scope` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTenantIsolation.test_no_cross_tenant_leak` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTokenRequired.test_guard_wrong_key_raises` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTokenRequired.test_guard_empty_tenant_raises` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestTierScopes.test_require_scope_absent_rejected` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_tenant` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_nonce` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestForgedToken.test_mutated_sig` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_widened_scopes_fail_validation` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestScopeEscalation.test_dropped_scopes_also_fail_validation` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_capability.py::TestValidToken.test_different_keys_cross_validate_fails` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_admission_fairness.py::TestFailOpenClosed.test_invalid_signature_raises_and_consumes_nothing` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_admission_fairness.py::TestFailOpenClosed.test_missing_tenant_rw_scope_rejected` (2 edge(s))
