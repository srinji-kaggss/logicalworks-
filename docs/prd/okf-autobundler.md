---
type: PRD
title: OKF Auto-Bundler — lgwks reads code, moves docs into OKF, flags dupes
description: Future lgwks capability that organizes the repo into the OKF bundle by MOVING files (never editing content) and flagging duplicate concepts as it goes.
tags: [prd, okf, factory-spec, daemon, future]
owning_issue: TBD
timestamp: 2026-06-25T00:00:00Z
---

# Problem

`scripts/gen_okf.py` makes the bundle *conformant in place* (derives frontmatter,
synthesizes indexes). It does **not** decide where a concept should *live*. Today a
human/agent still places files. The Director's target: lgwks reads the code + docs and
**auto-organizes the repo into our OKF format by MOVEMENT only** — no content edits —
while **flagging duplicate concepts** it encounters. Eventually run by the lgwks daemon;
for now invocable by a human/agent.

# The one capability (literal scope)

> Read code → propose/execute file **moves** into the OKF bundle topology → **flag
> dupes** during the walk. **No file-content edits. No rewrites. Movement only.**

This keeps the irreversible-content surface at zero: `git mv` is fully reversible and
diff-reviewable; content authorship stays with humans/agents and `gen_okf.py`.

# Interfaces (factory-speccable)

- **Entry:** `scripts/okf_autobundle.py` (stdlib; mirror `gen_navmap.py`/`gen_okf.py`
  conventions). Later surfaced via the daemon, not a new top-level CLI verb.
- **Input:** the repo tree + the navmap (`docs/navmap/index.json`) for the code graph.
- **Plan model** (`okf.autobundle.plan.v1`): a list of
  `{src, dst, reason, type, dup_of?}` move proposals. `dup_of` is set when the walk
  detects a near-duplicate concept (see Dedup).
- **Modes:**
  - `--plan` (default): emit the move plan as JSON; touch nothing.
  - `--apply`: execute the plan with `git mv` (so history follows the file); re-run
    `gen_okf.py --write` after to refresh indexes. Never writes file *bodies*.
  - `--report-dupes`: emit only the dup clusters.
- **Placement rules:** reuse `gen_okf.derive_type()` → target subdirectory by type
  (`schemas/`, `research/`, `handoff/`, `proofs/`, `concepts/`, `prd/`, …). A concept
  already in the right place is a no-op.

# Dedup (flag, never auto-delete)

- Cluster concepts by (a) title/CID similarity and (b) navmap subsystem overlap.
- For each cluster emit `{members[], canonical_hint, why}` — a **flag for a human/agent
  to collapse**, consistent with the doctrine "a slightly-different copy IS the bug,
  collapse to one canonical." The autobundler MUST NOT merge or delete; it surfaces.

# Acceptance criteria

- [ ] `--plan` produces a valid `okf.autobundle.plan.v1` and changes nothing on disk.
- [ ] `--apply` only ever runs `git mv` + index regeneration; a content diff on any
      moved file's body fails the run (assert body bytes unchanged across the move).
- [ ] Post-apply, `gen_okf.py --check` is conformant and `gen_okf.py --write` is a
      no-op (bundle is fresh).
- [ ] Dedup flags are emitted for known duplicate-concept clusters; none are
      auto-resolved.
- [ ] Reversible: `git` restores the pre-run tree exactly.

# Non-goals

- No content editing, summarizing, or rewriting (movement only).
- No automatic duplicate resolution (flag-only).
- No new top-level CLI verb (daemon-surfaced; `scripts/` for now).

# Relationship

Downstream of [knowledge-format](/docs/concepts/knowledge-format.md) and the
[navmap](/docs/navmap/README.md). The "documentation-before-CI" Keel gate (this PRD's
sibling) keeps the bundle fresh; this capability keeps it *organized*.
