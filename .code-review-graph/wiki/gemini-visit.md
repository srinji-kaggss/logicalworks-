# gemini-visit

## Overview

Directory-based community: lgwks_refactor

- **Size**: 33 nodes
- **Cohesion**: 0.1690
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| RefactorEngine | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 21-223 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 22-26 |
| rename_symbol | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 28-92 |
| RenameTransformer | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 30-87 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 31-32 |
| visit_Name | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 34-43 |
| visit_FunctionDef | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 45-54 |
| visit_AsyncFunctionDef | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 56-65 |
| visit_ClassDef | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 67-76 |
| visit_arg | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 78-87 |
| add_type_annotations | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 94-128 |
| AnnotationTransformer | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 96-124 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 97-98 |
| visit_FunctionDef | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 100-102 |
| visit_AsyncFunctionDef | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 104-106 |
| _annotate_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 108-124 |
| remove_unused_imports | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 130-215 |
| ImportCollector | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 135-148 |
| visit_Import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 136-140 |
| visit_ImportFrom | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 142-148 |
| NameUsageVisitor | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 158-169 |
| visit_Name | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 159-161 |
| visit_Import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 163-165 |
| visit_ImportFrom | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 167-169 |
| ImportFilter | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 179-211 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 180-181 |
| visit_Import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 183-196 |
| visit_ImportFrom | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 198-211 |
| apply | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 217-219 |
| preview | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 221-223 |
| refactor_file | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 226-262 |
| refactor_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 265-317 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py | 320-336 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `append` (16 edge(s))
- `generic_visit` (10 edge(s))
- `visit` (5 edge(s))
- `add_argument` (5 edge(s))
- `print` (5 edge(s))
- `str` (4 edge(s))
- `getattr` (3 edge(s))
- `ast.NodeTransformer` (3 edge(s))
- `fix_missing_locations` (3 edge(s))
- `spine` (3 edge(s))
- `parse` (2 edge(s))
- `ast.NodeVisitor` (2 edge(s))
- `set` (2 edge(s))
- `get` (2 edge(s))
- `fg` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py::RenameTransformer` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py::AnnotationTransformer` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py::ImportFilter` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py::NameUsageVisitor` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_refactor.py::ImportCollector` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_refactor.py::test_rename_symbol` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_refactor.py::test_add_type_annotations` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_refactor.py::test_remove_unused_imports` (1 edge(s))
