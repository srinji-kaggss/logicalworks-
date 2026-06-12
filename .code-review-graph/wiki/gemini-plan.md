# gemini-plan

## Overview

Directory-based community: lgwks_run

- **Size**: 40 nodes
- **Cohesion**: 0.2263
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| compute_file_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 55-57 |
| write_universal_index | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 60-92 |
| adopt_axiom_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 95-158 |
| index_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 161-178 |
| adopt_axiom_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 181-188 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 191-216 |
| _run_compat_dispatch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 219-223 |
| _crawl_dispatch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 226-257 |
| _plan_from_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 260-293 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 296-303 |
| ScopeError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 306-307 |
| GateError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 310-311 |
| GateVerdict | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 315-319 |
| sign_verdict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 322-323 |
| RunPlan | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 327-336 |
| FetchResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 340-344 |
| RunResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 348-361 |
| assert_gates_clicked | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 367-382 |
| _host | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 388-389 |
| _in_scope | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 392-393 |
| HostRate | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 396-409 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 397-399 |
| wait | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 401-409 |
| _scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 415-417 |
| host_is_blocked | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 420-435 |
| _allowed_hop | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 438-445 |
| fetch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 448-526 |
| _NoRedirect | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 494-496 |
| redirect_request | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 495-496 |
| _deterministic_embed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 529-536 |
| embed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 539-577 |
| EmbeddingProviderUnavailable | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 580-581 |
| embed_dual | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 584-632 |
| RunLog | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 638-668 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 643-648 |
| append | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 650-659 |
| verify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 661-668 |
| _chunk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 671-673 |
| execute_plan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 679-760 |
| _demo_plan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py | 763-782 |

## Execution Flows

- **_run_compat_dispatch** (criticality: 0.43, depth: 5)

## Dependencies

### Outgoing

- `get` (25 edge(s))
- `len` (14 edge(s))
- `print` (14 edge(s))
- `dumps` (12 edge(s))
- `add_argument` (12 edge(s))
- `str` (9 edge(s))
- `ValueError` (7 edge(s))
- `max` (5 edge(s))
- `Path` (5 edge(s))
- `signing_key` (4 edge(s))
- `tuple` (4 edge(s))
- `round` (4 edge(s))
- `set_defaults` (4 edge(s))
- `resolve` (4 edge(s))
- `embed_one` (4 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_run.py` (35 edge(s))
