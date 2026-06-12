# gemini-classify

## Overview

Directory-based community: lgwks_intent_classifier

- **Size**: 22 nodes
- **Cohesion**: 0.2692
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ClassifyResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 121-150 |
| plan_only | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 130-139 |
| grants_full_authority | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 142-150 |
| _clamp_for_method | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 153-165 |
| IntentClassifier | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 172-336 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 181-193 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 198-237 |
| classify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 241-271 |
| _classify_coreml | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 273-283 |
| _classify_cosine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 285-312 |
| _classify_keyword | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 314-327 |
| classes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 332-333 |
| is_ready | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 335-336 |
| _load_manifest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 343-350 |
| _embed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 353-366 |
| _cosine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 369-381 |
| _verb_signature | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 384-393 |
| _probe_embedder_tag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 396-404 |
| _centroid_cache_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 407-408 |
| _load_or_build_centroids | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 411-443 |
| _build_centroids | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 446-464 |
| classify_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py | 471-485 |

## Execution Flows

- **classify_command** (criticality: 0.41, depth: 4)

## Dependencies

### Outgoing

- `get` (10 edge(s))
- `round` (8 edge(s))
- `bool` (5 edge(s))
- `len` (5 edge(s))
- `sum` (4 edge(s))
- `max` (3 edge(s))
- `min` (3 edge(s))
- `exists` (3 edge(s))
- `dumps` (3 edge(s))
- `sort` (2 edge(s))
- `replace` (2 edge(s))
- `append` (2 edge(s))
- `strip` (2 edge(s))
- `perf_counter` (2 edge(s))
- `sqrt` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent_classifier.py` (12 edge(s))
