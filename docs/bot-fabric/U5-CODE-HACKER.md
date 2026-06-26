---
type: Reference
title: U5 — Code Hacker Bot
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T10:43:25-04:00
---

# U5 — Code Hacker Bot

Status: spec

## Purpose

Implement the first deterministic security-focused bot lane over repo code and artifacts.

This is not a pentest agent. It is a bounded static/hybrid analyzer that emits bot records conforming to `lgwks.bot.record.v1`.

## Inputs

- target repo path
- optional changed-files list
- optional repo graph cache
- optional package/world-db bindings

## Outputs

- `findings/code-hacker.jsonl`

Every output line must validate as `lgwks.bot.record.v1`.

## Scope

The first version should focus on four deterministic surfaces:

1. shell execution
2. file mutation
3. network egress
4. secret handling

## Detection families

### H1 — Dangerous shell execution

Flag:

- `os.system`
- `subprocess.*` with shell-like interpolation risk
- string-built commands crossing trust boundaries

Evidence:

- file path
- symbol if available
- excerpt or AST/node metadata

### H2 — Unsafe file mutation

Flag:

- broad delete patterns
- unbounded file writes outside expected roots
- path traversal shaped joins in mutation paths

### H3 — Unbounded network egress

Flag:

- raw network calls in modules that are supposed to remain deterministic/local
- imports violating architecture walls
- undeclared outbound hosts in sensitive modules

### H4 — Secret exposure / logging risk

Flag:

- token-like values echoed to logs
- exception surfaces likely to leak credentials
- env/Keychain material passed into human output paths

## Severity mapping

- `critical`
  - credential leak or destructive shell/file surface with weak boundary
- `high`
  - likely exploitable unsafe execution or boundary break
- `medium`
  - risky pattern with local mitigations present
- `low`
  - suspicious but weakly actionable

## Confidence mapping

Deterministic rules should set coarse confidence bands:

- `0.9`
  - explicit unsafe primitive match
- `0.7`
  - strong heuristic match
- `0.5`
  - suspicious but context-dependent

## Design constraints

1. no LLM calls
2. no internet dependency
3. fail closed on parse errors by emitting structured analyzer-failure records where appropriate
4. findings must always link to local drill-down paths

## Likely file targets

- `lgwks_review.py`
- or new `lgwks_bot_code_hacker.py`
- `tests/test_bot_code_hacker.py`

## Acceptance

1. The bot emits valid `lgwks.bot.record.v1` records.
2. Dangerous shell usage is detected in seeded fixtures.
3. Secret/logging risks are detected in seeded fixtures.
4. Architecture-wall network violations can be surfaced from repo-local rules.
5. The bot can run on a changed-file subset without scanning the full repo.
