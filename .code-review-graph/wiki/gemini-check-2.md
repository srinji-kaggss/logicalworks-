# gemini-check

## Overview

Directory-based community: lgwks_gate_arch

- **Size**: 9 nodes
- **Cohesion**: 0.0839
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| RuleVerifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 22-231 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 24-27 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 29-44 |
| _check_forbidden_import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 46-127 |
| _literal_import_target | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 130-133 |
| _check_no_global_mutable | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 135-185 |
| _check_ast_pattern | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 187-231 |
| make_arch_verifiers | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 234-250 |
| _validate_rule | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py | 253-262 |

## Execution Flows

- **check** (criticality: 0.49, depth: 2)

## Dependencies

### Outgoing

- `isinstance` (19 edge(s))
- `get` (18 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Verdict` (16 edge(s))
- `Path` (7 edge(s))
- `exists` (6 edge(s))
- `append` (6 edge(s))
- `str` (4 edge(s))
- `join` (4 edge(s))
- `any` (3 edge(s))
- `parse` (3 edge(s))
- `read_text` (3 edge(s))
- `walk` (3 edge(s))
- `startswith` (3 edge(s))
- `ValueError` (3 edge(s))
- `len` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_hard_forbidden_import` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_conformant_passes` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_advisory_silent_except` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_advisory_no_global_mutable` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_dynamic_forbidden_import_detected` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_dynamic_allowed_import_does_not_fail` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_klass_read_from_data` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_arch.py::TestArchGate.test_malformed_rule_rejected` (1 edge(s))
