# Handoff: Repo Cleanup — 2026-06-02

## What happened (the full sequence)

1. **Merged 2 open PRs** (#26 expression, #28 intent-classifier) into `main`.
2. **Rebased both PRs** onto latest `origin/main` before merge. PR #26 hit a conflict in `tests/test_research_stack.py` between `TestHomeQuickHints` (from main) and `TestExpressionParser` (from PR). Resolved by keeping both classes.
3. **Deleted 9 branches** (local + remote) that were merged or stale.
4. **Discovered dangling commits** — 14 orphaned objects from rebase + force-push + branch deletion.
5. **Audited every dangling commit** for content not present in `main`. Found:
   - 3 docs stranded on `feat/math-batch-human` (expression spec, classifier sizing, JSON schema)
   - 24 vision artifacts stranded on `feat/harden-vision-adr067-a2a` (research bot schemas, compiler docs, private-intent-fabric hardening)
6. **Extracted lost files** from dangling commits with `git show <commit>:<path>` and committed them to `main`.
7. **Purged dangling commits** with `git reflog expire --expire=now --all && git gc --prune=now --aggressive`.
8. **Removed 8 worktrees** and their branches.
9. **Fixed a typo** (`lass` → `class`) introduced during conflict resolution.
10. **Ran tests** at every step. 269 pass, 0 fail.

## Manual pain points (what burned tokens)

| Step | Time sink | Root cause |
|---|---|---|
| Rebase conflict resolution | ~15 min | `tests/test_research_stack.py` grew on both main and PR branch independently. No merge-driver for test files. |
| Worktree path mismatch | ~5 min | Intent-classifier worktree was at `.worktrees/intent-classifier` but I assumed `.worktrees/lgwks-intent`. |
| Branch merge verification | ~10 min | `git branch --merged` lies after squash-merge. Had to use `git cherry` and three-dot diff to know what was actually unique. |
| Dangling commit archaeology | ~20 min | 14 commits, each needed `git show`, `git ls-tree`, tree-hash comparison against main, and file-by-file existence check. |
| Vision artifact recovery | ~10 min | 33 files across 3 subdirs. Had to create directories, extract one-by-one, validate Python/JSON. |
| Reflog purge | ~2 min | `git gc` alone doesn't clear reflog. Need `git reflog expire --expire=now --all` first. |

## What `lgwks repo` should automate

### `lgwks repo audit`
One-shot health check. Exit non-zero if any issue found.

```
$ lgwks repo audit
[DANGER] 14 dangling commits (recoverable for 90d)
[WARN]   3 branches merged but not deleted: feat/auth-harden-capability-upkeep, ...
[WARN]   2 worktrees with uncommitted changes: lgwks-store-json-default (M lgwks, M tests/test_research_stack.py)
[INFO]   0 stashes
[INFO]   0 open PRs
```

**Checks:**
1. `git fsck --no-reflogs --dangling` → count dangling commits
2. `git branch --merged main` → find stale local branches
3. `git worktree list` + `git status --short` per worktree → find dirty worktrees
4. `git stash list` → find hidden stashes
5. `gh pr list --state open` → find open PRs
6. `git ls-files --others --exclude-standard` → find untracked files

### `lgwks repo recover [--dry-run]`
Scan dangling commits for file trees not present in `main`. Offer to extract or ignore.

```
$ lgwks repo recover
Scanning 14 dangling commits...
[FOUND] 54cea1a0 — 33 files in vision/ not in main
  vision/artifacts/foundation.logic-os-grounding.md
  vision/research/research-network/schemas/research-source.schema.json
  ...
[FOUND] bb856c73 — 3 docs not in main
  docs/lgwks-expression-v1-spec.md
  docs/ml-001-intent-classifier-sizing.md
  docs/schemas/lgwks-expression-v1.schema.json
[SKIP]  24c06b74 — all blobs already in main (PR #32 squash-merge)
Recover 36 files? [y/N/dry-run]:
```

**Algorithm:**
1. `git fsck --no-reflogs --dangling` → get commit list
2. For each commit: `git ls-tree -r` → list all blobs
3. For each blob: check if hash exists in `main` tree (`git cat-file -t <blob>` in main)
4. If blob missing: group by directory, show sample, prompt for recovery
5. Recovery: `git show <commit>:<path> > <path>` + validate (py_compile, json.load) + `git add`

### `lgwks repo cleanup [--force]`
Safe deletion of merged branches + worktrees + stashes + gc.

```
$ lgwks repo cleanup
Will delete branches:
  local:  feat/auth-harden-capability-upkeep, feat/intent-classifier, feat/lgwks-expression-v1, ...
  remote: origin/feat/auth-harden-capability-upkeep, ...
Will remove worktrees:
  /Users/srinji/logical-works/lgwks-store-json-default (has uncommitted changes — SKIPPED unless --force)
Will clear stashes:
  stash@{0}: WIP on fix/store-json-default
Will run: git reflog expire --expire=now --all && git gc --prune=now
Proceed? [y/N]:
```

**Safety gates:**
- Skip worktrees with uncommitted changes unless `--force`
- Skip branches not in `git branch --merged main` unless `--force`
- Always run `git gc --prune=now` last

### `lgwks repo merge <pr-number>`
Rebase PR onto main, resolve common conflicts, push, merge via API.

```
$ lgwks repo merge 26
Fetching PR #26... feat/lgwks-expression-v1
Rebasing onto main...
[CONFLICT] tests/test_research_stack.py: TestHomeQuickHints vs TestExpressionParser
[RESOLVED] Kept both classes (pattern: keep-all-test-classes)
Force-pushing... Merged. Closed PR #26.
```

**Conflict resolution rules (auto-patterns):**
- `tests/test_research_stack.py` with `<<<<<<< HEAD\nclass Test` → keep both classes, delete markers
- `lgwks` script with argparse subparser additions → keep both additions, sort alphabetically
- Any `.py` file with `<<<<<<<` → abort and flag for manual review

### `lgwks repo handoff`
Generate a machine-readable report for the next agent.

```json
{
  "schema": "lgwks.repo.handoff.v0",
  "repo": "/Users/srinji/logicalworks-",
  "branch": "main",
  "sha": "2d43ab3",
  "health": {
    "uncommitted": 0,
    "untracked": 0,
    "stashes": 0,
    "dangling_commits": 0,
    "open_prs": 0,
    "dirty_worktrees": 0
  },
  "last_cleanup": {
    "date": "2026-06-02T22:24:00Z",
    "agent": "claude-opus-4.8",
    "actions": [
      "merged PR #26 (expression)",
      "merged PR #28 (intent-classifier)",
      "deleted 9 stale branches",
      "recovered 36 files from dangling commits",
      "purged 14 dangling commits",
      "removed 8 worktrees"
    ],
    "risks": [
      "reflog expired — no history recovery possible without backup",
      "worktree 'Logical Claude Works - a5-clock-plans' exists outside this repo"
    ]
  }
}
```

## Known external worktrees (do not touch)

These directories exist on disk but are NOT git worktrees of `logicalworks-`:
- `/Users/srinji/logical-works/Logical Claude Works - a5-clock-plans`
- `/Users/srinji/logical-works/Logical Claude Works - attest-boot`
- `/Users/srinji/logical-works/Logical Gemini Works`

They are separate repos. The cleanup script must scope to `git worktree list` only.

## Invariant for next agent

> **Before declaring a repo "clean", verify all six zeros:**
> `git status --short | wc -l == 0`
> `git stash list | wc -l == 0`
> `git worktree list | wc -l == 1` (main only)
> `git fsck --no-reflogs --dangling 2>&1 | grep -c 'dangling commit' == 0`
> `gh pr list --state open | wc -l == 0`
> `python3 -m unittest discover tests` → OK

If any is non-zero, run `lgwks repo audit` (or manual equivalent) before handoff.

## Rollback

If this handoff file is wrong or incomplete: delete it, re-run `lgwks repo audit`, regenerate.

---
*Generated by Claude Opus 4.8 during repo cleanup 2026-06-02.*
*269 tests pass. .git size 1.4M. 0 dangling commits.*
