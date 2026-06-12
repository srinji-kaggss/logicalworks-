# gemini-click

## Overview

Directory-based community: lgwks_browser

- **Size**: 16 nodes
- **Cohesion**: 0.1140
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _click_candidate_score | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 41-78 |
| _classify_click_outcome | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 81-91 |
| _should_stop_click_discovery | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 94-104 |
| _browser_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 107-118 |
| available | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 121-130 |
| _text_from | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 133-134 |
| _remote_allowed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 137-162 |
| _headers | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 165-170 |
| _route_handler | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 173-184 |
| handler | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 176-183 |
| _session_for_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 187-206 |
| render | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 209-277 |
| _click_candidates_js | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 280-329 |
| discover_clicks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 332-460 |
| on_popup | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 400-402 |
| save_session | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py | 463-570 |

## Execution Flows

- **save_session** (criticality: 0.49, depth: 2)
- **render** (criticality: 0.40, depth: 2)
- **discover_clicks** (criticality: 0.39, depth: 2)

## Dependencies

### Outgoing

- `get` (22 edge(s))
- `str` (13 edge(s))
- `close` (10 edge(s))
- `int` (6 edge(s))
- `urlparse` (6 edge(s))
- `lower` (6 edge(s))
- `wait_for_timeout` (5 edge(s))
- `print` (5 edge(s))
- `sync_playwright` (4 edge(s))
- `strip` (4 edge(s))
- `new_page` (4 edge(s))
- `goto` (4 edge(s))
- `type` (4 edge(s))
- `sub` (3 edge(s))
- `launch` (3 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_browser.py` (16 edge(s))
