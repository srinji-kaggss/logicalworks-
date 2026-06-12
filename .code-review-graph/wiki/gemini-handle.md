# gemini-handle

## Overview

Directory-based community: lgwks_html

- **Size**: 7 nodes
- **Cohesion**: 0.0755
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| HTMLToMarkdownParser | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 32-279 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 33-63 |
| handle_starttag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 65-131 |
| handle_endtag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 133-197 |
| handle_data | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 199-215 |
| _render_table | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 217-279 |
| html_to_markdown | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py | 282-313 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `append` (31 edge(s))
- `join` (8 edge(s))
- `get` (7 edge(s))
- `strip` (5 edge(s))
- `range` (3 edge(s))
- `len` (3 edge(s))
- `int` (3 edge(s))
- `sub` (3 edge(s))
- `set` (2 edge(s))
- `enumerate` (2 edge(s))
- `max` (2 edge(s))
- `lower` (2 edge(s))
- `endswith` (2 edge(s))
- `HTMLParser` (1 edge(s))
- `super` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_html.py` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_html.py::test_html_to_markdown_basic` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_html.py::test_html_to_markdown_links` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_html.py::test_html_to_markdown_lists` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_html.py::test_html_to_markdown_table_colspan_rowspan` (1 edge(s))
