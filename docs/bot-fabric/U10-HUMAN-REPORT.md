# U10 — Human Sitemap Report

Status: spec

## Purpose

Project the canonical JEPA package into two surfaces:

1. A dense human report — anomaly cards, sitemap, drill-down index, next actions
2. A compact machine packet — bytecode context for the next AI session

Both surfaces are derived entirely from the grounded package. L budget: 0.
If synthesis ran, LLM claims are labelled and segregated from grounded claims.

## Inputs

- reduced package from U3/U4
- optional synthesizer output from U9
- L score (if synthesis ran)

## Human report output

File: `findings/report.md`

### Structure

```
# Session Report — <date>

## Health radar
  <5-line dense grid: severity counts, L score, contradiction count, freshness>

## Anomaly cards (top 8)
  Each card:
    - title (from finding summary)
    - severity
    - why it matters (one sentence, grounded — no LLM invention unless labelled)
    - drill-down: file:line or symbol
    - recommended command

## Sitemap
  <flat list of all files touched by findings, grouped by cluster>
  <each entry: file path, finding count, highest severity>

## Contradictions
  <each contradiction: subject, conflicting claims, resolution command>

## Next actions
  <ranked list: read X, run Y, fix Z>
  <grounded actions come first; LLM-suggested actions labelled [LLM]>

## L score
  <coefficient value, what it means, breakdown by layer>
```

### Rules

- one finding = one card. No merging in the report (merging is the reducer's job).
- LLM-originated claims are labelled `[LLM]` inline. Auditor sees the boundary.
- no prose summaries beyond one sentence per card.
- all drill-down links must be repo-local paths.

## Machine packet output

File: `findings/machine-packet.json`

Schema: `lgwks.machine.packet.v1` (already defined in U4)

Extended with:
```json
{
  "l_score": 0.08,
  "l_budget_used": "53%",
  "session_date": "...",
  "grounded_claim_count": 42,
  "invented_claim_count": 4,
  "synth_status": "complete | skipped | unavailable"
}
```

This is the bytecode context. The next AI session loads this, not the chat log.

## Design constraints

1. report is generated deterministically from the package — same package = same report
2. LLM claims are always labelled — never silently merged into grounded content
3. L score is always present, even if synthesis was skipped (L=0 when skipped)
4. report fails closed: if package is invalid, emit a structured error report, not silence
5. machine packet must pass `lgwks.machine.packet.v1` schema validation

## Likely file targets

- `lgwks_report.py`
- `tests/test_report.py`

## Acceptance

1. Report generated from seeded package contains all sections.
2. LLM claims are labelled `[LLM]` in the human report.
3. Machine packet validates against `lgwks.machine.packet.v1`.
4. L score is present and correct in both outputs.
5. Invalid package input produces a structured error report, not a crash.
6. Same package input produces identical output on repeated runs (deterministic).
