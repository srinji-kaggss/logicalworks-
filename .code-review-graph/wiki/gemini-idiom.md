# gemini-idiom

## Overview

Directory-based community: lgwks_gate_idiom

- **Size**: 4 nodes
- **Cohesion**: 0.0548
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| IdiomVerifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py | 19-148 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py | 23-25 |
| _corpus_embeddings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py | 27-62 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py | 64-148 |

## Execution Flows

- **check** (criticality: 0.56, depth: 1)

## Dependencies

### Outgoing

- `append` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Verdict` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py::Evidence` (4 edge(s))
- `Path` (3 edge(s))
- `relative_to` (3 edge(s))
- `isinstance` (3 edge(s))
- `type` (3 edge(s))
- `len` (2 edge(s))
- `read_text` (2 edge(s))
- `_embedding` (2 edge(s))
- `str` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_advisory_only_never_fail` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_score_and_report` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_embedder_failure_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_empty_corpus_cannot_decide` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_advisory_only_never_fail` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_score_and_report` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_embedder_failure_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_empty_corpus_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_duplicate_content_skipped` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_similarity_failure_cannot_decide` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_gate_idiom.py::TestIdiomGate.test_score_bounds_enforced` (1 edge(s))
