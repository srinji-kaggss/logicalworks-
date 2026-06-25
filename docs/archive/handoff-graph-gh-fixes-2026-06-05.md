---
type: Archive
title: Handoff — Graph Rust Indexing + GH Branch Awareness
description: _rust_import_to_path uses file-existence heuristics with progressive fallback.
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Handoff — Graph Rust Indexing + GH Branch Awareness

**Date:** 2026-06-05  
**Local HEAD:** `0273466` — **aligned with `origin/main`** (`git status` clean, `HEAD == origin/main`).

---

## What shipped

### Issue #37 — `lgwks graph` indexes Rust files (CRITICAL)
- **Root cause:** `extract_from_repo` had `if not rel_path.endswith(".py"): continue`, skipping 100% of `.rs` files.
- **Fix:**
  - Zero-dependency Rust regex parser (`_parse_rust_file`) extracting `use`, `mod`, `fn`, `struct`, `enum`, `trait`, `impl`, `let`, and call sites.
  - `_rust_import_to_path` maps `crate::`, `super::`, `self::` to file paths with progressive fallback (e.g. `crate::auth::session` → `src/auth/session.rs`, then `src/auth.rs` if the first is missing).
  - `extract_from_repo` now accepts `.rs` alongside `.py`.
- **Hardening:** `_detect_unindexed_languages` warns when a dominant source language has 0 indexed files — kills the hollow-green trap.

### Issue #38 — `lgwks gh issue` is blind to local branches (Medium)
- **Root cause:** `_compute_issue_next` only checked GitHub API state, never local `git branch --list`.
- **Fix:**
  - `_local_branches_for_issue(number)` discovers branches matching `*{number}*`.
  - `_compute_issue_next` now surfaces:
    - `push` — when current branch matches the issue.
    - `checkout` — when other local branches match.
    - `start` — only when no local branch exists (the old behavior).

---

## Evidence

- **9 new tests** in `tests/test_graph_rust.py`:
  - `test_parse_rust_file_extracts_all_constructs`
  - `test_rust_import_to_path_crate`
  - `test_rust_import_to_path_super`
  - `test_rust_import_to_path_self`
  - `test_detect_unindexed_languages_warns`
  - `test_detect_unindexed_languages_silent_when_indexed`
  - `test_extract_from_repo_indexes_rust_files`
  - `test_local_branches_for_issue_finds_match`
  - `test_compute_issue_next_shows_local_branch`
- **Full suite:** 669 passed (excludes pre-existing `test_openrouter_embed.py` failure, unrelated to this change).

---

## Files touched

| File | Change |
|---|---|
| `lgwks_graph.py` | Rust parser, import mapping, language detection |
| `lgwks_gh.py` | Local branch awareness in issue next-actions |
| `tests/test_graph_rust.py` | 9 new tests (new file) |

---

## RISK / GAP

`_rust_import_to_path` uses file-existence heuristics with progressive fallback. If `crate::foo::bar` is defined inline inside `src/foo.rs` (not in `src/foo/bar.rs`), the fallback will map the import to `src/foo.rs`. This is correct for graph connectivity but may over-link. No inline-submodule false-linking test exists yet.

---

## Queued threads (discussed, not implemented)

1. **Graph visual + query layer** — user wants a localhost:3000 HTML interface (D3.js force-directed) that doubles as a visual query builder. Spec exists at `docs/plan-graph-visual-query-layer.md`; not built.
2. **Multi-layer testing analysis** — user wants end-to-end workflow simulation across layers (not just single-level unit tests). Discussed; not implemented.

---

## Next suggested actions (if this session resumes)

1. **H0-falsification test for inline Rust modules** — ensure `mod bar { fn baz() {} }` inside `src/foo.rs` does not create a false edge to a non-existent `src/foo/bar.rs`.
2. **Graph visual layer** — implement the localhost:3000 interface per `docs/plan-graph-visual-query-layer.md`.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
