# U11 — Artifact Strength Gate

Status: spec

## Purpose

Prevent weak packages from reaching the synthesizer or the human.

This is the core anti-black-box rule:

- the LLM may improve the artifact
- it may not be required to make the artifact make sense

## Gate inputs

- `review-packet.json`
- `package.json`
- `machine/packet.json`
- `index/links.json`

## Required checks

### C1 — Ranked findings exist

- at least one ranked finding
- severity and confidence present

### C2 — Drill-down exists

- each top finding has at least one valid local drill-down link

### C3 — Contradictions are explicit

- if contradictions exist, they are represented as structured records

### C4 — Next steps exist

- package exposes at least one next read or next command

### C5 — No prose-only dependency

- all critical claims must map to:
  - evidence records
  - links
  - package anchors

### C6 — Degraded mode is explicit

- if synth is skipped/unavailable, output state must say:
  - `synth_status = skipped|unavailable`
  - package still considered `actionable = true|false`

## Gate outputs

```json
{
  "schema": "lgwks.artifact.strength.v1",
  "package_id": "pkg:lgwks-self-review:abc123",
  "pass": true,
  "checks": {
    "ranked_findings": true,
    "drilldown": true,
    "contradictions": true,
    "next_steps": true,
    "prose_dependency": true,
    "degraded_mode": true
  },
  "actionable_without_synth": true
}
```

## File targets

Likely implementation files:

- `lgwks_review.py`
- `lgwks_jepa.py`
- `tests/test_artifact_strength.py`

## Acceptance

1. A package missing drill-down links fails.
2. A package with only prose summary fails.
3. A package with no next-step structure fails.
4. Synth-disabled runs can still pass when the machine packet is strong enough.
