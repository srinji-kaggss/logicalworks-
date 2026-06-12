# gemini-dict

## Overview

Directory-based community: lgwks_aup

- **Size**: 30 nodes
- **Cohesion**: 0.2791
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _anonymise | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 40-41 |
| Verdict | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 48-51 |
| Severity | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 54-58 |
| Rule | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 62-93 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 72-81 |
| from_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 84-93 |
| AUPCheck | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 97-117 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 107-117 |
| _RefusalLog | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 287-345 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 293-298 |
| _init_file | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 300-308 |
| append | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 310-322 |
| read | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 324-335 |
| flush | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 337-345 |
| AUPGate | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 353-613 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 380-389 |
| _canonical_request | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 391-393 |
| _validate_request | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 395-404 |
| _match_keyword | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 410-416 |
| _match_semantic | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 418-436 |
| _match | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 438-444 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 450-525 |
| _maybe_log | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 527-534 |
| intent_gate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 540-580 |
| export_audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 586-609 |
| export_rules_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 611-613 |
| _aup_check_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 620-652 |
| _aup_audit_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 655-665 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 668-685 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py | 688-705 |

## Execution Flows

- **intent_gate** (criticality: 0.43, depth: 4)
- **main** (criticality: 0.43, depth: 5)
- **_aup_audit_command** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `add_argument` (12 edge(s))
- `print` (11 edge(s))
- `get` (10 edge(s))
- `getattr` (6 edge(s))
- `dumps` (5 edge(s))
- `set_defaults` (5 edge(s))
- `str` (4 edge(s))
- `len` (3 edge(s))
- `round` (2 edge(s))
- `lower` (2 edge(s))
- `embedding` (2 edge(s))
- `hexdigest` (2 edge(s))
- `sha256` (2 edge(s))
- `encode` (2 edge(s))
- `strip` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_aup.py` (22 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_anonymise_is_deterministic` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_anonymise_different_inputs_different_outputs` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_review_is_logged` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_custom_rules_override` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_medium_maps_to_review` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_low_maps_to_allow` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_advisory_match_logs_telemetry` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_rule_round_trip` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_aup.py::test_deny_is_logged` (1 edge(s))
