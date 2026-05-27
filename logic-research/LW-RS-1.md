# LW-RS/1 — Logical Works Research Standard, version 1

Canonical standard for every research entry (`ARTIFACT_SCHEMA.md` §A/§B/§C). Use real **ISO**
standards where one exists; for inherently subjective fields, apply the fixed internal scales below
so judgment is applied *consistently, like a standard*. Versioned: breaking changes mint `LW-RS/2`.

## Prime clause — outcome-priority
Standards are the default discipline, not a straitjacket. If conforming to a code would force you to
**drop or distort a real finding**, record the finding, add `"nonstd": true` (+ a one-word reason),
and proceed. Signal first, format second. Never lose a fact to a format rule.

## Conformance declaration
- `notes/*.jsonl` — **first line** is `{"std":"LW-RS/1"}`.
- `claims/*.json` — top-level `"std":"LW-RS/1"`.
- Validators may assume LW-RS/1 fields and ISO codes once the declaration is present.

## ISO-coded fields (objective)
| field | ISO / spec | form / example |
|--|--|--|
| time — `ts`, source `date` | **ISO 8601** | UTC, `Z` suffix: `2026-05-26T18:00:00Z` |
| country / jurisdiction | **ISO 3166-1 alpha-2** (subdivision **3166-2**) | `US`, `CA-ON`, `JP`; supranational `EU` allowed |
| currency | **ISO 4217** | `{"cur":"USD","val":1.2e9}` — value in SI numerals |
| quantity / unit | **ISO 80000 / SI** | explicit unit; magnitudes as numbers (`1.2e9`), never `1.2B`/`$1.2bn` |
| language | **ISO 639-1** | `en`, `zh`, `ko` |
| identifier (on promotion to an envelope) | **RFC 4122 / ISO·IEC 9834-8** UUID | short `i` in-stream; mint UUID at ingestion |
| schema validation | JSON Schema **draft-07** | matches `packages/canvas-protocol` |
| (roadmap) measurement uncertainty | **ISO·IEC Guide 98-3 (GUM)** | when a figure has a stated error band |

## Subjective scales (LW-RS/1 controlled vocabularies + decision rules)
These have no ISO equivalent; the rules below ARE the standard. Apply them deterministically.

**`c` — confidence** · number 0.00–1.00, 2 dp.
Bands: `≤0.39` weak · `0.40–0.69` moderate · `0.70–0.89` strong · `≥0.90` near-certain.
Hard caps (a claim may not exceed): tertiary-only ≤ **0.50** · secondary-only ≤ **0.75** ·
`provenance:E` ≤ **0.80** unless purely deductive · only `P`-tier evidence may reach `≥0.90`.
(GUM spirit: a confidence is invalid unless its basis — tier + survival — is stated.)

**`st` — source_tier** · `P` primary (filings, statutes/law text, peer-reviewed, official
statistics, standards bodies) · `S` secondary (reputable press, named analyst reports) · `T`
tertiary (blogs, vendor marketing, unattributed) · `N` none / unverified.

**`p` — provenance** · `M` measured (≥1 live source present in `s`) · `E` elicited (model judgment).
Distinctive claims (§C) are always `E`.

**`hr` — hallucination_risk** (claims) · `n` none · `l` low · `m` medium · `h` high.
`h` ⇐ asserted strongly on `N`/`T` tier, or extrapolated from a single case / pre-launch signal.

**`pri` — priority** (arch_directive) · `P0` high decision-weight, blocks or enables the core, act
now · `P1` material, act soon · `P2` useful, later. = f(decision-weight × reversibility).

**`stance`** (human_input) · `agree · refine · reject · extend · nuance`.

**`by`** (human_input authorship) · `ai_drafted` (seeded model of director's view, awaiting confirm)
· `human` (the director's own entry; many allowed).

## Change policy
Additive field changes keep `LW-RS/1`. Any change to a cap, an enum value, or a required field is
breaking → `LW-RS/2`, and entries keep declaring the version they were written under.
