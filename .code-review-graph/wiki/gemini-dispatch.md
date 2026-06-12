# gemini-dispatch

## Overview

Directory-based community: lgwks

- **Size**: 72 nodes
- **Cohesion**: 0.1661
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _import_substrate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 41-43 |
| utc_now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 66-67 |
| slugify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 70-73 |
| sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 76-77 |
| tokens | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 80-81 |
| word_count | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 84-85 |
| normalize_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 88-95 |
| same_site | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 98-99 |
| parse_keywords | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 102-108 |
| deterministic_embedding | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 111-123 |
| cosine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 126-129 |
| query_variants | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 132-149 |
| TextHTMLParser | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 152-185 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 153-159 |
| handle_starttag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 161-169 |
| handle_endtag | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 171-175 |
| handle_data | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 177-185 |
| FetchResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 189-196 |
| fetch_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 199-224 |
| run_googler | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 227-240 |
| fallback_search_url | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 243-245 |
| chunk_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 248-260 |
| concept_terms | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 263-273 |
| semantic_type_scores | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 276-281 |
| JarvisDB | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 284-504 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 285-288 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 290-292 |
| init | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 294-441 |
| columns | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 443-448 |
| add_column_if_missing | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 450-452 |
| migrate_legacy | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 454-491 |
| insert | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 493-501 |
| count | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 503-504 |
| make_snapshot | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 507-524 |
| emit_embedding | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 527-546 |
| estimate_seconds | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 549-553 |
| build_seed_urls | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 556-588 |
| score_page | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 591-595 |
| write_jsonl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 598-601 |
| _crawl_via_substrate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 604-655 |
| crawl_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 658-1020 |
| next_questions | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1023-1043 |
| write_gnn_exports | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1046-1080 |
| write_graph | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1083-1105 |
| write_report | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1108-1138 |
| remap_db_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1141-1178 |
| build_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1181-1568 |
| _solve_dispatch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1571-1573 |
| _home_dispatch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1576-1578 |
| _repl_dispatch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks | 1581-1583 |

*... and 22 more members.*

## Execution Flows

- **_auth_dispatch** (criticality: 0.42, depth: 3)
- **remap_db_command** (criticality: 0.40, depth: 3)
- **crawl_command** (criticality: 0.39, depth: 3)
- **_akinator_dispatch** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `add_argument` (67 edge(s))
- `add_parser` (66 edge(s))
- `print` (48 edge(s))
- `append` (41 edge(s))
- `len` (33 edge(s))
- `str` (27 edge(s))
- `dumps` (25 edge(s))
- `get` (24 edge(s))
- `join` (21 edge(s))
- `getattr` (20 edge(s))
- `set_defaults` (17 edge(s))
- `round` (15 edge(s))
- `execute` (13 edge(s))
- `extend` (12 edge(s))
- `max` (10 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks` (61 edge(s))
