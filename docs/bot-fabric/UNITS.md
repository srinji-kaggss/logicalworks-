# Build Units

## Goal

Break the bot fabric into self-contained implementation chunks for cheaper coding agents.

## U1 — Bot record schema

Deliver:

- canonical JSON schema for bot findings
- severity/confidence enums
- drill-down link fields

## U2 — Bot plan schema

Deliver:

- declarative run plan
- bot selection
- target repo
- runtime policy
- output roots

## U3 — Deterministic reducer

Deliver:

- dedupe
- clustering
- confidence merge
- anomaly card generation

## U4 — JEPA package contract

Deliver:

- package object
- machine packet
- human projection
- contradiction bundle
- historical binding hooks

## U5 — Code hacker bot

Deliver:

- deterministic security finding pass
- auth/shell/file/network heuristics

## U6 — Slop math bot set

Deliver:

- graph anomaly bot
- naming/binning bot
- proof gap bot
- spec drift bot

## U7 — Optimizer bot

Deliver:

- hub/god-module analysis
- split suggestions
- token waste indicators

## U8 — Concurrent stress bot

Deliver:

- concurrent workflow simulation harness
- degraded dependency tests
- recovery/replay checks

## U9 — Synthesizer seam

Deliver:

- final package input contract
- OpenRouter/local seam policy
- usage metering
- artifact-strength-before-synthesis gate

## U9A — Apple-native small-model seam

Deliver:

- Foundation/CoreML-first local helper policy
- runtime selection rules
- fallback order:
  - Foundation
  - CoreML membrane
  - optional small local coder helper
  - remote synthesizer

## U10 — Human sitemap report

Deliver:

- Markdown report
- anomaly cards
- drill-down index
- next actions

## U11 — Artifact strength gate

Deliver:

- checks that the machine packet is actionable without the synthesizer
- checks that required fields and evidence links exist before any LLM pass
- explicit degraded mode when synthesis is skipped or unavailable
