# gemini-concept

## Overview

Directory-based community: lgwks_concept

- **Size**: 31 nodes
- **Cohesion**: 0.3042
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _hash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 89-90 |
| _slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 93-95 |
| _tokenize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 98-100 |
| Concept | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 104-136 |
| fingerprint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 118-120 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 122-136 |
| ConceptRel | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 140-156 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 148-156 |
| ConceptExtractor | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 161-408 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 171-176 |
| ingest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 180-290 |
| _ensure_concept | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 294-316 |
| _infer_type | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 318-346 |
| _add_rel | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 348-357 |
| _build_cooccurrence_rels | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 361-376 |
| _build_attribute_rels | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 378-389 |
| _promote_confidence | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 391-399 |
| finalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 403-408 |
| concept_vector | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 416-459 |
| _add_component | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 424-432 |
| build_activation_map | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 464-485 |
| ConceptGraph | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 490-608 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 496-503 |
| resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 507-531 |
| what_is | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 533-550 |
| activated_by | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 554-559 |
| activates | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 561-566 |
| related | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 568-573 |
| nearest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 577-596 |
| export_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 600-608 |
| extract_from_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py | 613-623 |

## Execution Flows

- **__init__** (criticality: 0.43, depth: 3)

## Dependencies

### Outgoing

- `items` (12 edge(s))
- `group` (12 edge(s))
- `append` (10 edge(s))
- `lower` (10 edge(s))
- `get` (10 edge(s))
- `strip` (8 edge(s))
- `sorted` (7 edge(s))
- `finditer` (6 edge(s))
- `len` (6 edge(s))
- `values` (6 edge(s))
- `defaultdict` (5 edge(s))
- `any` (5 edge(s))
- `split` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_concept_vector_determinism` (3 edge(s))
- `set` (3 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_concept.py` (11 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_concept_vector_determinism` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_definition_extraction` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_ec2_meaning` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_activation_steering_lambda_to_ec2` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_concept.py::TestConceptExtractor.test_extract_from_chunks` (1 edge(s))
