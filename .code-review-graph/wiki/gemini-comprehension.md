# gemini-comprehension

## Overview

Directory-based community: lgwks_comprehend

- **Size**: 9 nodes
- **Cohesion**: 0.1556
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ComprehensionArtifact | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 23-42 |
| from_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 33-42 |
| ComprehensionVerifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 45-165 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 49-52 |
| _load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 54-64 |
| _unit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 66-71 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 73-165 |
| comprehend_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 168-190 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py | 193-198 |

## Execution Flows

- **comprehend_command** (criticality: 0.48, depth: 2)

## Dependencies

### Outgoing

- `get` (13 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Verdict` (8 edge(s))
- `set` (7 edge(s))
- `list` (6 edge(s))
- `print` (5 edge(s))
- `exists` (3 edge(s))
- `isinstance` (3 edge(s))
- `add_argument` (3 edge(s))
- `resolve` (2 edge(s))
- `Path` (2 edge(s))
- `open` (2 edge(s))
- `load` (2 edge(s))
- `sorted` (2 edge(s))
- `cls` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_comprehend.py::TestComprehensionGate.test_cli_returns_verdict_object` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_comprehend.py::TestComprehensionGate.setUp` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_comprehend.py::TestComprehensionGate.test_cli_returns_verdict_object` (1 edge(s))
