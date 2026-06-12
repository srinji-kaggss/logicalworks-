# gemini-rustdoc

## Overview

Directory-based community: lgwks_gate_framework

- **Size**: 10 nodes
- **Cohesion**: 0.1333
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _strip_rust_noncode | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 33-39 |
| G3Verifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 42-254 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 46-47 |
| _cargo_metadata | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 49-65 |
| _find_rustdoc_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 67-75 |
| _generate_rustdoc_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 77-98 |
| _installed_symbols | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 100-126 |
| _extract_references | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 128-171 |
| _grounding_context | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 173-175 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py | 177-254 |

## Execution Flows

- **check** (criticality: 0.51, depth: 2)

## Dependencies

### Outgoing

- `add` (8 edge(s))
- `group` (5 edge(s))
- `len` (5 edge(s))
- `get` (5 edge(s))
- `Path` (4 edge(s))
- `finditer` (4 edge(s))
- `isinstance` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Verdict` (4 edge(s))
- `sub` (4 edge(s))
- `join` (3 edge(s))
- `exists` (3 edge(s))
- `str` (3 edge(s))
- `run` (2 edge(s))
- `set` (2 edge(s))
- `split` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.setUp` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_missing_crate_dir_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_missing_rustdoc_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_valid_reference_passes` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_hallucinated_symbol_fails` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_grounding_context_emitted` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_token_based_layer_catches_macro_paths` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_framework.py::TestG3Gate.test_comment_path_does_not_create_reference` (1 edge(s))
