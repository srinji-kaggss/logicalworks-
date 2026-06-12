# gemini-dict

## Overview

Directory-based community: lgwks_verify

- **Size**: 21 nodes
- **Cohesion**: 0.1270
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| Outcome | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 23-27 |
| Klass | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 30-32 |
| OriginType | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 35-39 |
| Evidence | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 43-65 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 50-56 |
| from_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 59-65 |
| Verdict | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 69-121 |
| __post_init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 77-87 |
| provenance | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 90-92 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 94-103 |
| from_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 106-121 |
| Verifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 125-128 |
| check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 128-128 |
| GateRegistry | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 132-134 |
| run_pipeline | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 137-168 |
| LScore | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 175-195 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 188-195 |
| LCalculator | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 198-242 |
| from_verdicts | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 208-235 |
| to_report | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 238-242 |
| check_gate_evidence_completeness | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py | 245-252 |

## Execution Flows

- **from_dict** (criticality: 0.62, depth: 2)
- **cohere_command** (criticality: 0.58, depth: 3)
- **check** (criticality: 0.56, depth: 1)
- **check** (criticality: 0.56, depth: 1)
- **__post_init__** (criticality: 0.53, depth: 1)
- **check** (criticality: 0.51, depth: 2)
- **to_dict** (criticality: 0.49, depth: 1)
- **check** (criticality: 0.49, depth: 2)
- **comprehend_command** (criticality: 0.48, depth: 2)
- **from_verdicts** (criticality: 0.41, depth: 1)

## Dependencies

### Outgoing

- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_mixed_pipeline` (9 edge(s))
- `get` (7 edge(s))
- `append` (5 edge(s))
- `isinstance` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidence.test_verdict_json_with_structured_evidence` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_all_grounded_l_is_zero` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidenceCompleteness.test_complete_when_pass` (3 edge(s))
- `Enum` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_all_invented_l_is_one` (2 edge(s))
- `cls` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_verify.py::TestPipeline.test_hard_short_circuits_on_first_non_pass` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_verify.py::TestPipeline.test_internal_exception_mapped_to_cannot_decide` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidenceCompleteness.test_incomplete_when_fail_without_evidence` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidenceCompleteness.test_incomplete_when_cannot_decide_without_evidence` (2 edge(s))
- `str` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_verify.py` (11 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_idiom.py::IdiomVerifier.check` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_mixed_pipeline` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_comprehend.py::ComprehensionVerifier.check` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_framework.py::G3Verifier.check` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py::RuleVerifier._check_forbidden_import` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py::RuleVerifier._check_no_global_mutable` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gate_arch.py::RuleVerifier._check_ast_pattern` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py::G0Verifier.check` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidence.test_verdict_json_with_structured_evidence` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_all_grounded_l_is_zero` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestEvidenceCompleteness.test_complete_when_pass` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_lscore.py::TestLCalculator.test_all_invented_l_is_one` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_cohere.py::cohere` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_verify.py::TestPipeline.test_hard_short_circuits_on_first_non_pass` (2 edge(s))
