# src-crawl

## Overview

Directory-based community: crawler

- **Size**: 139 nodes
- **Cohesion**: 0.1525
- **Dominant Language**: rust

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| CrawlRequest | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 34-46 |
| into_config | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 35-45 |
| ErrorEnvelope | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 49-52 |
| router | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 54-59 |
| gather_handler | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 63-72 |
| healthz | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 74-76 |
| crawl_handler | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 78-90 |
| serve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs | 93-98 |
| Chunk | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 12-18 |
| chunk_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 22-49 |
| empty_text_no_chunks | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 56-58 |
| windows_with_overlap_cover_all_words | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 61-70 |
| each_chunk_is_content_addressed | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 73-79 |
| deterministic | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs | 82-87 |
| StealthLevel | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/config.rs | 13-24 |
| Default | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/config.rs | 57-76 |
| default | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/config.rs | 58-75 |
| CrawlConfig | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/config.rs | 33-55 |
| cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 12-18 |
| cid_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 22-27 |
| normalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 31-36 |
| simhash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 40-59 |
| token_hash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 61-69 |
| hamming | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 71-73 |
| DedupIndex | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 92-113 |
| DupVerdict | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 86-90 |
| new | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 93-95 |
| check_and_insert | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 98-112 |
| cid_is_whitespace_and_case_stable | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 120-123 |
| exact_duplicate_caught | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 126-130 |
| near_duplicate_caught | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 133-142 |
| unrelated_is_fresh | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 145-152 |
| identical_simhash_zero_distance | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs | 155-157 |
| Engine | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 22-212 |
| new | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 23-26 |
| crawl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 28-192 |
| load_robots | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 196-211 |
| entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 214-223 |
| seed_jitter | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 225-232 |
| now_millis | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs | 234-239 |
| CrawlError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/error.rs | 36-49 |
| code | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/error.rs | 37-48 |
| Extracted | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 10-17 |
| Assets | Class | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 23-31 |
| extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 33-92 |
| extract_assets | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 94-129 |
| sel | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 131-134 |
| select_one | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 136-138 |
| resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 142-153 |
| title_and_canonical | Test | /Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs | 178-182 |

*... and 89 more members.*

## Execution Flows

- **crawl_handler** (criticality: 0.48, depth: 1)
- **gather** (criticality: 0.45, depth: 1)

## Dependencies

### Outgoing

- `assert_eq` (43 edge(s))
- `to_string` (36 edge(s))
- `assert` (29 edge(s))
- `push` (19 edge(s))
- `map` (15 edge(s))
- `Some` (15 edge(s))
- `format` (14 edge(s))
- `len` (13 edge(s))
- `Ok` (11 edge(s))
- `Vec::new` (11 edge(s))
- `insert` (10 edge(s))
- `clone` (9 edge(s))
- `select` (9 edge(s))
- `push_str` (9 edge(s))
- `get` (8 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/dedup.rs` (14 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/frontier.rs` (14 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/extract.rs` (11 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/schema.rs` (10 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/api.rs` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/gather.rs` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/main.rs` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/politeness.rs` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/chunk.rs` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/fetch.rs` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/fingerprint.rs` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/media.rs` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/engine.rs` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/robots.rs` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/crawler/src/config.rs` (4 edge(s))
