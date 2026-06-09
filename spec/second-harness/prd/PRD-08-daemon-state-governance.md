# PRD-08 — Daemon, State & Governance

Parent: [PRD.md](../PRD.md) §5 side-effects + U10 + §14 risk register · Status: draft v0.1
Replaces: observability/governance SaaS; also owns what §14 names but no parent unit owns.

## Problem

§14 is honest that the hard new engineering is statefulness: daemon lifecycle, single-writer
db, per-session keying, stale results. The parent assigns those risks to no unit. This PRD
owns them, plus the entire security/data posture (T0-grade, previously unspecified).

## Scope

- IN: daemon lifecycle — per-session keyed, single-instance (lockfile), idempotent restart,
  crash-consistent, orphan-reaped on SessionEnd.
- IN: state db — sqlite, WAL, ONE writer process (the daemon); all other processes
  (hooks, CLI, cockpit) read-only or enqueue. //why: hooks fire concurrently; two writers
  is the §14 risk realized.
- IN: side-effect capture (U10): PostToolUse/FileChanged/Task*/ConfigChange → audit rows
  (who/what/capability/decision — SOC2 shape) + work-tracking + independent static review
  fired to cockpit, zero Opus actions.
- IN: **security & data handling (new, T0):**
  - secret redaction at ingest: transcripts pass a redaction filter (key/token/credential
    patterns + entropy heuristic) BEFORE any db write; raw secrets never persisted.
  - db file mode 0600, owned by the user; no network listener except the cockpit server.
  - cockpit auth: signed capability token minted at daemon start, required on every
    request incl. localhost (trust is cryptographic, never `if host == localhost`).
    Pause-Opus is a privileged capability, separately scoped.
  - retention: transcripts-derived rows TTL-configurable; default 90d; purge verb exists.
- IN: ledgers consumed by others: injection budget (04-c), tap latency (07), failure feed (INV-9).
- OUT: analysis semantics (PRD-06), rendering (PRD-07).

## Builds on (candidates — verify at unit start)

`lgwks_substrate_db.py`, `lgwks_sqlite.py`, `lgwks_session.py`, `lgwks_monitor.py`,
`lgwks_hooks.py`, `lgwks_keyvault.py`/`lgwks_vault.py` (secrets handling prior art),
`lgwks_sign.py` (capability signing prior art), `lgwks_review.py` + gate modules
(`lgwks_gate_arch/framework/idiom.py`) for independent static review.

## Contract

db schema versioned `lgwks.state.v1` (migrations forward-only). Daemon control:
`lgwks daemon start|stop|status|doctor`. Audit row: `{ts, session, actor, event, target,
capability, decision, evidence_ref}`.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 08-a single-writer | property test: N concurrent hook fires + CLI reads during daemon writes → zero lost writes, zero `database is locked` surfacing to callers |
| 08-b lifecycle | kill -9 daemon mid-write → restart → db consistent (WAL recovery proven); double-start refused via lockfile; SessionEnd reaps |
| 08-c redaction | fixture transcript salted with 20 secret shapes (AWS keys, JWTs, .env lines, high-entropy strings) → zero reach db; measured recall on the fixture set = 100%, precision reported |
| 08-d capability auth | cockpit request w/o token → 401; with read token → read only; pause requires privileged token; tokens expire with session |
| 08-e audit capture | a real session's tool calls reproduced as audit rows; row count matches transcript tool-call count; review findings fire cockpit-side with zero Opus turns |
| 08-f retention | purge verb removes expired rows + proves via count; TTL config honored |

## Open questions → SCIENCE.md

Redaction recall beyond fixtures (adversarial corpus, §9); whether review gates' precision
justifies auto-flagging vs cockpit-only (same precision-gate discipline as 06-d).

RISK: this child carries all T0 exposure — a leaky db or an unauthenticated pause-Opus
endpoint converts an oversight tool into an attack surface on the Director's own machine.
