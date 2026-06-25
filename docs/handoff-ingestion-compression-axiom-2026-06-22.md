---
type: Handoff
title: Handoff — Ingestion = aggressive compression; #308 reframed (2026-06-22)
description: Status: course-correction session.
tags: [handoff]
timestamp: 2026-06-22T20:22:32-04:00
---

# Handoff — Ingestion = aggressive compression; #308 reframed (2026-06-22)

Status: **course-correction session. No code landed. Repo clean at `5b2bfaf` (== origin/main).**
Author terminated the session after multiple canary failures (below). Read this before
touching #308 or the daemon capture path.

---

## What this session was supposed to do
Continuation of the #311 close-out. Stated plan: "work on 1 first and then 2":
1. Arm the daemon Stop + PostToolUse hooks so the daemon captures the agent side of trajectories.
2. Fix #308 — Keel eval cache keys on command spec, not runtime inputs (warm cache serves stale verdict).

Both framings were wrong. The session is a record of *why*, so the next agent doesn't repeat them.

---

## Canary failures (what I got wrong, precisely)

**Canary 1 — "arm the hooks for ingestion."**
I accepted gap #1 without checking the mechanism. Ingestion does **not** need hooks and must
not use them. Evidence gathered this session:
- `lgwks_transcript.py` already parses the FULL trajectory from the Claude Code JSONL —
  `_block_text` handles `thinking`/`tool_use`/`tool_result`; `_extract_role` returns `tool_result`.
- `lgwks_daemon.run_forever` → `_resolve_capture_target` (`discover_live_transcript` finds the
  freshest live session *with no hook*) → `_maybe_process_cortex` → `lgwks_cortex.process_transcript`,
  every ~5s. Wired at `lgwks_daemon.py:767`.
- Proof it runs: `store/cortex/73cc3752-….cortex.jsonl` (Jun 21, live) = **3198 turns: 2198 assistant,
  925 tool_result, 75 human.** The "agent side" the hooks were meant to capture is *already captured,
  completely, from the durable JSONL.*
- The `tool_call=0 / transcript_turn=0` I cited as the gap was reading `daemon-events.db` — the
  lifecycle event lane, the WRONG store. The training corpus is `store/cortex/*.cortex.jsonl`, and it's full.
- My own memory already recorded the Director's ruling: *"the DAEMON is the core capture path; a hook
  is ONLY an optional low-latency push-trigger, never a prerequisite. lgwks must work hook-free."* My
  gap analysis contradicted both that and landed reality (#245/#246).

**Lesson:** hooks are for real-time *control* (scope-guard intercept before a tool runs, subconscious
injection) — never for *ingestion*. The JSONL is the durable source of truth; the daemon tails it.
Re-emitting turns via hooks would duplicate a complete record and add a dedup/fragility burden.
Task killed. Memory `project_lgwks_data_pipeline_capture_gap` recall-line corrected.

**Canary 2 — "fix #308 by tuning the glob list."**
I reproduced #308 cleanly (see below), then proposed three fixes that were all the same wrong axis:
"pick a better list of file extensions" (`SRC_GLOBS`). Keying staleness on file *type* is itself a
goofy data model — the same category error as the original bug (keying on spec not inputs), one level up.

**Canary 3 — "make the boundary smarter" (trace reads / content-address inputs).**
After the file-type critique I reframed to "observe the reads and hash exactly those" — still wrong.
I kept trying to make the ingest boundary *smarter* instead of *dumber*.

---

## The corrected axiom (Director, 2026-06-22) — THIS is the durable takeaway

**Ingestion is just an aggressive, content-addressed compression algorithm. Take ALL the bytes,
dedup by content hash, store. No filtering, no type-gating, no "is this a valid/relevant input"
decision at the boundary. Cleanup — what matters, what's structured, what's dropped — is a separate
downstream pass against the full compressed store.**

Why:
- Filtering at the boundary is **irreversible loss** — you can't recover what you refused to ingest.
  (Director's irreversible-vs-purchasable doctrine: ingest is the irreversible moment.)
- Content-addressing **is** the compression — identical bytes collapse to one node — so "take everything"
  is cheap *by construction*. There is no speed/coverage tension to manage; you do not curate to stay fast.
- Under-coverage (dropping/ignoring an input) = the cardinal sin (it yields stale-pass / fake acceptance).
  Over-coverage is merely slower. Fail toward "ingest more," never "ingest less."

Already-correct vs violating:
- Ingestion obeys it: `lgwks_substrate_run.py:225` `chunk_id = chunk-{sha(content)[:16]}`; no extension
  logic in `lgwks_content_extract.py` / `lgwks_chunking.py`.
- **The violation is `SRC_GLOBS`** (`lgwks_verify/keel/src/anchor.mjs:25`) — a file-type allowlist
  deciding what counts as a real input at the hashing boundary. Cleanup logic smuggled into the
  ingest/compress primitive.

---

## #308 — root cause PROVEN, fix direction CORRECTED, NOT implemented

**Reproduced (deterministic, airtight):** node id = `H(kind, params, [unitFingerprint, evidenceFingerprint, channel])`.
`unitFingerprint` (no `scope`) = `contentFingerprint` over `SRC_GLOBS` = **code extensions only**.
An atom whose tool reads a non-code input (`lgwks.profile.json`, a JSON/data fixture) gets a node id
that does not move when that input changes. Inline repro: atom reads `data.json`, flip `{"threshold":1}`→`{"threshold":0}`
so the real verdict goes true→false; warm run served the stale **PASS** (`cached=true`, identical id) —
fake acceptance. This matches last session's stale `testability=false`, which followed a `lgwks.profile.json`
edit (a `.json`, invisible to `SRC_GLOBS`).

**Corrected fix (do NOT tune the glob list, do NOT add a read-tracer at the boundary):**
- Retire `SRC_GLOBS` as a *type allowlist*. The default unit fingerprint should compress the **whole
  content tree** (content-addressed → complete + cheap), excluding only runtime-**output** roots
  (`store/`, `.ci-runs/`, `.keel/`). That exclusion is a **layout** boundary (where outputs live), NOT a
  type filter. Under-coverage (the stale-pass sin) then becomes structurally impossible: the default is everything.
- This converges Keel's staleness onto the *one* content-addressed model ingestion already uses, instead
  of running a parallel, weaker, type-based model. Aligns with the elected State Fabric / "I want 1" data model.
- "Which subset atom X actually reads" stays a **later, optional speed optimization** (the existing
  `scope` seam, #647) — never a correctness gate.

**Caveat to verify before implementing:** `store/cortex/*.cortex.jsonl` (1MB+, rewritten constantly by
the daemon) must be outside the fingerprinted tree, or a "hash everything under source" default will bust
the cache every run. The fix is to exclude output *locations*, and/or ensure runtime output does not live
inside the verified content tree — a layout decision, confirmed with the Director, not a type filter.

---

## Repo / board state (verified)
- `git status`: clean. Branch `main`, HEAD `5b2bfaf`, `== origin/main`.
- #308 OPEN (unchanged; my reframe is in this doc + should be added as an issue comment by the next agent
  once the Director confirms the "retire SRC_GLOBS / compress whole tree minus output roots" direction).
- #311 closed/landed (PR #318, prior session). Daemon capture is live and hook-free (#245/#246).
- Daemon hook-arming task: **deleted** (wrong mechanism — see Canary 1).

## Next agent — start here
1. Get the Director's explicit go on the #308 direction above (retire `SRC_GLOBS` type-allowlist;
   default fingerprint = whole content tree minus output roots). It mutates the verification authority's
   staleness semantics — spec→implement→harden.
2. Do NOT arm daemon hooks. Ingestion is hook-free by design.
3. Internalize the axiom: ingestion = dumb aggressive content-addressed compression; cleanup is downstream.
