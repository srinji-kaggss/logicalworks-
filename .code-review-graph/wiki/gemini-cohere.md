# gemini-cohere

## Overview

Directory-based community: lgwks_cohere

- **Size**: 7 nodes
- **Cohesion**: 0.0923
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| G0Verifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 26-86 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 31-32 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 34-86 |
| _log_verdicts | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 89-97 |
| cohere | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 100-137 |
| cohere_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 140-161 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py | 164-169 |

## Execution Flows

- **cohere_command** (criticality: 0.58, depth: 3)
- **check** (criticality: 0.56, depth: 1)

## Dependencies

### Outgoing

- `append` (10 edge(s))
- `Path` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Verdict` (4 edge(s))
- `print` (4 edge(s))
- `exists` (3 edge(s))
- `add_argument` (3 edge(s))
- `isinstance` (2 edge(s))
- `run` (2 edge(s))
- `splitlines` (2 edge(s))
- `strip` (2 edge(s))
- `to_dict` (2 edge(s))
- `str` (2 edge(s))
- `get` (1 edge(s))
- `CognitionLog` (1 edge(s))
- `set_defaults` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_cohere.py::TestCoherePipeline.test_hallucinated_api_blocked` (1 edge(s))
