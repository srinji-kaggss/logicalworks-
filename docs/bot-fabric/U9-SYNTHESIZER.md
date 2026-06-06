# U9 — Synthesizer Seam

Status: spec

## Purpose

One typed interface between the fully grounded package (U4) and the LLM reasoning layer.
The LLM receives a pre-solved, pre-typed problem. Its job is judgment over the residual —
not context recovery, not invention.

L budget: measured and logged. Every claim the LLM adds is tagged `origin_type: invented`.

## Position in pipeline

```
U11 artifact strength gate
  → must pass before synthesizer is called
  → if gate fails: skip synthesis, return package as-is

U9 synthesizer seam
  → calls provider (OpenRouter / Apple Foundation / local)
  → logs L contribution
  → returns enriched package with LLM claims tagged

output carries L score
```

## Input contract

The synthesizer receives exactly:
```json
{
  "schema": "lgwks.synth.input.v1",
  "package_id": "...",
  "ranked_findings": [...],
  "clusters": [...],
  "contradictions": [...],
  "recommended_reads": [...],
  "repo": "...",
  "l_budget": 0.15
}
```

`l_budget` is the max fraction of output claims allowed to be LLM-invented.
Exceeding it causes the synthesizer to return a degraded response flagged `l_exceeded: true`.

## Output contract

```json
{
  "schema": "lgwks.synth.output.v1",
  "package_id": "...",
  "reasoning": [...],
  "next_actions": [...],
  "l_score": 0.08,
  "l_exceeded": false,
  "claims": [
    {
      "text": "...",
      "origin_type": "invented | grounded | inferred",
      "basis": ["finding_id:...", "cluster:..."]
    }
  ],
  "provider": "openrouter | apple_foundation | local",
  "model": "..."
}
```

Every claim the LLM produces is individually tagged with `origin_type` and a `basis`
list of grounded finding IDs it drew from. Ungrounded claims set `basis: []` and
`origin_type: invented` — these are what L counts.

## Provider fallback order

1. Apple Foundation (on-device, no egress, lowest L risk)
2. OpenRouter remote model (if Foundation unavailable)
3. Skip synthesis, return package with `synth_status: skipped`

Never fail hard — synthesis is optional. The package must stand without it (U11 enforces this).

## Usage metering

Every call logs:
- provider + model
- input token count
- output token count
- l_score of the response
- wall time

Metering record schema: `lgwks.synth.meter.v1`
Written to: `store/synth-meter.jsonl`

## Degraded mode

If U11 gate fails, synthesis is skipped. The response is:
```json
{
  "synth_status": "skipped",
  "reason": "artifact_strength_gate_failed",
  "checks": {...}
}
```

If provider is unavailable:
```json
{
  "synth_status": "unavailable",
  "reason": "no_provider_reachable"
}
```

Both degraded states are valid pipeline outcomes — downstream must handle them.

## Design constraints

1. no synthesis call without U11 gate passing
2. every LLM claim is tagged with origin_type and basis
3. l_score is computed and logged on every call
4. l_budget enforcement: if exceeded, flag and return degraded rather than silently over-generate
5. provider selection is policy-driven, not hardcoded

## Likely file targets

- `lgwks_synthesizer.py`
- `tests/test_synthesizer.py`

## Acceptance

1. Input with failing U11 gate returns `synth_status: skipped` without calling provider.
2. Every output claim carries `origin_type` and `basis`.
3. `l_score` is computed correctly against seeded fixtures.
4. `l_budget` exceeded triggers `l_exceeded: true` in response.
5. Provider unavailable returns `synth_status: unavailable`, not a crash.
6. Metering record written to store on every call attempt.
