---
type: Archive
title: Handoff — CLI Ergonomics Sweep (Issues 157–159, 161–163)
description: Issue #160 (daemon JSONL event bus) is partially started but not complete:
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Handoff — CLI Ergonomics Sweep (Issues 157–159, 161–163)

**Date:** 2026-06-15
**Local HEAD:** `67a9a91` — **aligned with `origin/main`**
**Scope:** `ant`-ergonomics adoption set: inline resolver, validated config, machine-output transform, ANT naming disambiguation, intent classifier regression fix, full test-suite green-up.
**Commit:** `67a9a91 feat(cli): comprehensive fixes for issues 157-159, 161-163`

---

## What shipped

### Issue #157 — Unified `@path` / `@cid` payload resolver
- New module: `lgwks_inline.py`
- Supports `@./path`, `@/abs/path`, `@data://...`, binary auto-base64 + MIME sniff, and `axiom/` vault `@cid:<cid>` pointers.
- Size cap enforced; over-cap fails loud instead of silent truncation.
- Migrated ~8 ad-hoc `--file` readers per the issue body.
- Tests: `tests/test_inline.py` (10 passed).

### Issue #158 — Validated YAML config surface (`lgwks.config.v1`)
- Registered schema: `docs/schemas/lgwks.config.v1.json`
- New module: `lgwks_config.py`
- Precedence: env var > `~/.lgwks/config.yaml` / `./.lgwks/config.yaml` > coded defaults.
- Loud failure on schema violation.
- Tests: `tests/test_config.py` (10 passed).

### Issue #159 — `--transform` / `-r` field extraction for `--machine` output
- Global `--transform <path>` and `-r/--raw` flags added to `lgwks` CLI.
- Applied to machine-readable output path via `lgwks_transform.py`.
- No new lgwks→LLM call path introduced.

### Issue #161 — Disambiguate ANT from Anthropic `ant` CLI
- Module-level note in `lgwks_tokenizer.py` clarifies ANT = Aetherius Neural Tokenizer.
- Code identifiers use `atok` / `ant_tok` to avoid collisions.

### Issue #162 — Restore `SEMANTIC_METHODS` regression
- Constant restored in `lgwks_intent_classifier.py`.
- Authority gate no longer crashes with `NameError`.

### Issue #163 — Full test suite green-up
- `pytest tests/`: **1842 passed, 3 skipped, 0 failed** (was 29 failures).
- Removed `tests/test_lfm2_extract.py` (module `lgwks_lfm2_extract` does not exist).
- `make test-rust`: 3 passed, 0 failed.
- Schema registry: conformant (127 IDs in code, 135 rows known).

---

## Evidence

| Check | Result |
|---|---|
| `pytest tests/` | 1842 passed, 3 skipped |
| `make test-rust` | 3 passed |
| `python3 scripts/check_schema_registry.py` | conformant |
| `git status` | clean |
| `origin/main` | `67a9a91` (fast-forward pushed) |

---

## Files touched

| File | Change |
|---|---|
| `lgwks` | `--transform`, `-r`, inline/config integration |
| `lgwks_inline.py` | new: payload resolver |
| `lgwks_config.py` | new: validated config loader |
| `lgwks_transform.py` | new: field-extraction transform |
| `lgwks_intent_classifier.py` | restore `SEMANTIC_METHODS` |
| `lgwks_tokenizer.py` | ANT disambiguation note |
| `lgwks_daemon.py` | add `DaemonPaths.bus` |
| `docs/schemas/lgwks.config.v1.json` | new schema |
| `docs/schemas/lgwks.daemon.bus.event.v1.json` | new schema |
| `docs/schemas/REGISTRY.md` | register new schemas |
| `tests/test_inline.py` | new tests |
| `tests/test_config.py` | new tests |
| `tests/test_lfm2_extract.py` | deleted (orphaned) |
| `tests/test_model_*.py`, `tests/test_substrate.py`, `tests/test_codebase.py`, `tests/test_home.py`, `tests/test_rmeter.py` | regression fixes |

---

## RISK / GAP

Issue #160 (daemon JSONL event bus) is **partially started but not complete**:
- Schema `lgwks.daemon.bus.event.v1` registered.
- `DaemonPaths.bus` path added.
- Still needed: daemon writer, Rust TUI tail/dedupe, `--machine` consumer, stubbed workflow execution wired to bus events.

PR #153 (TUI cockpit) was already effectively merged; closed. Use current `main` as the base for remaining #160 work.

---

## Queued threads

1. **Daemon JSONL bus (#160)** — next concrete seam.
2. **Issue #164** — CLI surface gaps from hands-on simulation.
3. **Issues #154/#155** — security/quality audits remain open and are larger than this sweep.

---

## Next suggested actions

1. Finish #160: implement `DaemonBusWriter` in `lgwks_daemon.py`, tail it from `tui/src/main.rs`, and expose it to `lgwks ... --machine`.
2. Address #164 (CLI surface gaps) from real simulation feedback.
3. Schedule dedicated hardening passes for #154/#155 with red-team agents.

Co-Authored-By: Claude <noreply@anthropic.com>
