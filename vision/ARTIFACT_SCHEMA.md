# RAC — Research Artifact Contract

Two output types. **The machine ingestion unit is the lightweight World-Map Note (§A)** — many
small append-only JSON records the ingestion agent (RAC) merges into the world-map graph and the
OS-plug-in diagram. The heavy markdown RAC (§B, below) is the optional *Opus-tier synthesis*
deliverable for a human — only written when judgment work justifies the cost.

---

## Entry Standards — LW-RS/1 (governs every §A/§B/§C entry)

**Canonical standard: `~/logicalworks-/vision/LW-RS-1.md`** (the source of truth; this is a working
mirror). Use real ISO standards wherever one exists; for inherently subjective fields, apply the
fixed internal scales below so judgment is applied *consistently, like a standard*.
**Outcome-priority clause:** codes are the default discipline, not a straitjacket — if forcing a
standard would drop a real finding, record the value, add `"nonstd":true`, and proceed. Never lose
signal to formatting.

Declare conformance once: the **first line** of each `notes/*.jsonl` is `{"std":"LW-RS/1"}`; each
`claims/*.json` carries top-level `"std":"LW-RS/1"`.

**ISO-coded fields:**
| field | standard | form |
|--|--|--|
| time (`ts`, source dates) | **ISO 8601** | UTC, `Z` suffix — `2026-05-26T18:00:00Z` |
| country / jurisdiction | **ISO 3166-1 alpha-2** (subdiv: 3166-2) | `US`, `CA-ON`, `EU` |
| currency | **ISO 4217** | `{"cur":"USD","val":1.2e9}` — value in SI, no "1.2B" |
| quantities / units | **ISO 80000 / SI** | explicit unit; magnitudes as numbers (`1.2e9`), never abbreviations |
| language | **ISO 639-1** | `en`, `zh`, `ko` |
| identifiers (when promoted to an envelope) | **RFC 4122 / ISO·IEC 9834-8** UUID | short `i` in-stream; mint UUID at ingestion |
| schema validation | JSON Schema **draft-07** | matches canvas-protocol |

**Subjective scales (LW-RS/1 controlled vocabularies + rules):**
- `c` confidence — number 0.00–1.00 (2 dp). Bands: ≤0.39 weak · 0.40–0.69 moderate · 0.70–0.89
  strong · ≥0.90 near-certain. **Hard caps:** tertiary-only ≤0.50, secondary-only ≤0.75,
  `provenance:E` ≤0.80 unless purely deductive. (GUM spirit: confidence must state its basis.)
- `st` source_tier — `P` primary (filings, law text, peer-reviewed, official statistics) · `S`
  secondary (reputable press/analyst) · `T` tertiary (blog/vendor/marketing) · `N` none/unverified.
- `p` provenance — `M` measured (≥1 live source in `s`) · `E` elicited (judgment).
- `hr` hallucination_risk — `n·l·m·h`; `h` = asserted strongly on `N` tier or single-case/pre-launch
  extrapolation.
- `pri` priority (arch_directive) — `P0` high decision-weight, blocks/enables core, do now · `P1`
  material, soon · `P2` useful, later. Derived from decision-weight × reversibility.
- `stance` (human_input) — `agree·refine·reject·extend·nuance`.

---

## §A — World-Map Note (lightweight · multiple · iterative) — PRIMARY

Format = **minified JSONL**: one note per line, short fixed keys, **omit any empty/default field**,
no pretty-print, no markdown fences inside the `.jsonl`. One research pass appends many lines to
`~/logicalworks-/vision/notes/<topic>.jsonl`. The ingestion agent reconciles by `i` + `sup`, and **diffs
rather than re-emits** — never re-send the whole map; emit only new/changed notes. One fact per
line so a reader greps a line instead of loading the file.

**Key dictionary (shared base — present on every note):**
| key | field | values |
|--|--|--|
| `i` | id | `wm-<short>` (stable) |
| `k` | kind | `node·edge·claim·os_hook·lesson·gap·discovery·arch_directive·blindspot` |
| `t` | topic | slug |
| `m` | model | emitter |
| `ts` | emitted_at | ISO8601 |
| `c` | confidence | 0-1 (capped by `st`; tertiary-only ≤ 0.5) |
| `p` | provenance | `M`=measured `E`=elicited |
| `st` | source_tier | `P`·`S`·`T`·`N` |
| `s` | sources | array of `[url,date,figure]` tuples — only when `p=M` |
| `sup` | supersedes | id (omit if none) |
| `op` | needs_opus | `1` (omit when false) |

**Per-kind payload keys** (discriminated by `k`; omit empties):
- `node` → `l`=label `ly`=layer(`stack·distribution·identity·cloud·ecosystem·regulation`) `sm`=summary
- `edge` → `f`=from `to`=to `r`=relation(`controls·depends_on·competes·gates·plugs_into`)
- `claim` → `stmt`=statement `ab`=about(node/edge id) `fx`=falsifier `hr`=hallucination_risk(`n·l·m·h`)
- `os_hook` → `wr`=world_ref `tp`=touchpoint `mech`=mechanism `lev`=leverage `rk`=risk
- `lesson` → `b`=before `a`=after `tg`=trigger `ty`=`myth_dispelled·belief_revised·belief_confirmed`
- `gap` → `q`=question `w`=why_it_matters  (→ seeds the next pass)
- **`discovery`** → `ld`=what the AI learned `rf`=[refs ids] `pr`=prior→now shift `im`=implication
- **`arch_directive`** → `rec`=what the OS should DO `tgt`=os_target(`protocol·gate·tape·widget·ml·sovereignty·distribution`) `wy`=[evidence ref ids] `pri`=`P0·P1·P2` `rv`=reversibility `fx`=falsifier(what would reverse it)
- **`blindspot`** → `bs`=what the map cannot currently see / is uncertain about `qr`=[queries run — the extra-context search trail] `fnd`=what surfaced (brief) `cav`=caveat (why it's a blindspot: source-tier limit, source disagreement, modeled-not-measured, no primary, drift, honest-unresolved) `sev`=severity(`l·m·h`) `ab`=(opt) the node/claim/gap it qualifies. Set `"nonstd":true`. A blindspot is the honesty companion to confidence — log it whenever a fact is single-sourced, sources disagree, a figure is modeled rather than measured, or a claim rests on an ungrounded premise. Mirror high-value blindspots into the §D register.

**Feedback discovery layer** (the point of the whole system): every Opus pass MUST close the loop —
emit `discovery` notes (what we learned that we didn't know going in) AND `arch_directive` notes
(what our OS should therefore do, aimed at a real surface: the envelope `protocol`, the handoff
`gate`, the append-only `tape`, `widget` zones, the `ml` layer, `sovereignty`, or `distribution`
strategy). Directives carry a falsifier so a later pass can reverse them. Unresolved threads exit
as `gap` notes that seed the next wave.

**Example line (minified, empties omitted):**
`{"i":"wm-a1","k":"arch_directive","t":"distribution","m":"opus","ts":"2026-05-26T18:00:00Z","c":0.7,"p":"E","rec":"ship a browser-extension install path so we don't depend on app-store review","tgt":"distribution","wy":["wm-d3","wm-c7"],"pri":"P0","rv":"high","fx":"app stores grant AI-layer entitlements within 12mo"}`

---

## §B — RAC synthesis markdown (Opus-tier, optional)

Written only for synthesis/judgment that earns Opus pricing. ONE file in
`~/logicalworks-/vision/artifacts/<id>.md`. Skims fast for a human, reassembles cold for Claude.

## Format

```
---
id: <track>.<slug>            # e.g. stack.distribution-chokepoints
track: ecosystems | stack | ai-layer | wedge | strategy
title: <short>
model: claude | gemini | chatgpt | codex | kimi | copilot
confidence: 0.0-1.0
provenance: measured | elicited   # measured = sourced fact; elicited = model judgment
grounding: [urls / specs / primary sources]   # REQUIRED for non-wedge tracks
maps_to_vision: [layer|gate|tape|sovereignty|anti-hack|ml|scale]
feeds: [ml | decision | build]
expand_axes: [child topics worth their own prompt]   # THIS is how the map grows
---

## TL;DR            (5 bullets max — for the human)
## MAP              (grounded facts WITH numbers; cite every claim)
## SCALE & CONSTRAINTS  (real limits, costs, adoption/hackability physics)
## TOUCHES US       (how it informs an AI-native OS-layer; 3-5 bullets)
## BUILD-NOW        (concrete small things buildable immediately)
## SKEPTICISM       (who does this better, where it fails, what we can't afford)
## ML-FEED          (one JSON block: {"entities":[],"relations":[],"metrics":[]})
```

## Rules
- One topic per artifact. If it sprawls, split and add to `expand_axes`.
- `provenance: elicited` numbers are ordinal hints, never cited as fact.
- Non-Claude models: fill `grounding` from primary sources / current docs — never training memory.
- Claude (wedge track): grounding = our skills + reasoning; mark `provenance: elicited`.

---

## EXTENSION — Dialectic fields (added by `PROTOCOL.md`)

Claims that clear triage and run the adversarial engine append these blocks to the artifact.
Additive — existing artifacts stay valid.

### Front-matter additions
```
grounding_tool: firecrawl | "firecrawl UNAVAILABLE — fell back to WebSearch"
source_tiers: {primary: n, secondary: n, tertiary: n}   # count of sources by tier
adjudicated_by: <model/agent that scored — MUST differ from authors>
convergence: synthesis | stable-disagreement | unresolved-at-budget
```

### Body additions
```
## DIALECTIC
  thesis:        <strongest true version + self-confidence>
  antithesis:    <strongest attack + self-confidence>
  synthesis:     <what survives both>
  residual_disagreement: <where they still differ + the matched-comparison that would settle it>
## FALSIFICATION
  <for each surviving claim: the observation that would overturn it>
## DELTA_LOG
  <belief before → after → the specific evidence that flipped it; or "no change because…">
## HALLUCINATION_RISK
  <claims asserted above their source strength: claim → tier → risk(none/low/med/high) → why>
```

## Lessons — `<id>.lessons.json` (variable-N, min 1)

One file per artifact. Array of lesson objects. A lesson exists only if a belief changed or a myth
was killed (or a prior was attacked and held). No fixed count.
```json
[{
  "lesson_id": "L01",
  "claim_ref": "C01",
  "type": "myth_dispelled | belief_revised | belief_confirmed | open_question",
  "before": "what we believed going in",
  "after": "what survives the dialectic",
  "evidence_span": "the specific sourced fact that did the work",
  "sources": [{"url": "", "tier": "primary|secondary|tertiary", "figure": ""}],
  "confidence": 0.0,
  "confidence_basis": "source tier × adversarial survival × base-rate support",
  "falsifier": "observation that would overturn this lesson",
  "residual_disagreement": "where thesis/antithesis still differ, or null",
  "hallucination_risk": "none|low|med|high — why",
  "decision_weight": "low|med|high — does it change what we build?",
  "maps_to_vision": []
}]
```

---

## §C — Distinctive Claims (the N+1 pass) — `claims/<topic>.json`

Made **after** the factual pass, in a **separate file** so fact and opinion never blur. These are
the AI's own non-obvious assertions — interpretation, prediction, contrarian read, synthesis,
implication — that go *beyond* the sourced facts. Sparse and high-value (≥2 per topic, not
hundreds). Each carries a `verify` handle so a human can fact-check it, and a `human_input` slot
that captures the director's nuance as a first-class signal.

```json
[{
  "id": "dc-1", "topic": "<slug>", "model": "<who>",
  "claim": "the distinctive assertion (beyond the facts)",
  "type": "interpretation|prediction|contrarian|synthesis|implication",
  "basis": ["wm-<ping ids it rests on>"],
  "sources": [{"url":"","date":""}],
  "confidence": 0.0, "provenance": "elicited",
  "why_distinctive": "what makes this non-obvious / a stake in the ground",
  "falsifier": "the observation that would overturn it",
  "verify": "exactly how a human checks this — the query, dataset, doc, or test",
  "human_input": [
    {"by": "ai_drafted", "stance": "nuance",
     "note": "how the director would likely frame/qualify this claim",
     "ts": ""}
  ]
}]
```

**Rules:** every distinctive claim seeds exactly ONE `ai_drafted` `human_input` entry — the AI's
best model of how the director would phrase or qualify the claim ("how I would have made that
claim") — flagged for confirmation. The human edits it or appends more (`by:"human"`, many allowed;
`stance` ∈ agree|refine|reject|extend|nuance). Distinctive claims are always `provenance: elicited`
and never cited back as fact. This is the verification + reasoning-capture layer.

---

## §D — Blindspots Register (the honesty layer) — `artifacts/blindspots.register.json`

The map as-it-is must also record **where it cannot see**. Two surfaces, kept in sync:
1. **Stream** — `notes/blindspots.jsonl` (first line `{"std":"LW-RS/1"}`), append-only `blindspot`
   notes (kind defined in §A) logging the extra-context **search trail** (`qr`) and each weak spot.
2. **Register** — this single structured JSON artifact, grouping high-value blindspots by world-map
   layer so a human (or T8–T13 synthesis) can read confidence *with* its caveat in one place.

A blindspot is logged whenever any of these are true: a fact is **single-sourced**, **sources
disagree**, a figure is **modeled rather than measured**, a claim rests on an **ungrounded
premise**, a source is **below the tier its claim implies**, or an unknown is **honestly
unresolvable by research** (only time/external action closes it). This is not failure-logging — it
is the calibration record that keeps `c` honest (PROTOCOL §0–§1: confidence must state its basis;
principle 7 base-rates/triangulation; principle 11 calibration honesty).

```json
{
  "std": "LW-RS/1",
  "artifact": "blindspots.register",
  "generated": "<ISO8601>", "by": "<model>",
  "severity_scale": {"l":"minor / not load-bearing","m":"could mislead a claim or non-critical decision","h":"threatens a core decision or a P0/P1 directive if wrong"},
  "status_scale": ["open","mitigated","closed","unresolvable-by-research"],
  "blindspots": [{
    "id": "wm-bs-<short>",            // same id as the notes/blindspots.jsonl line
    "layer": "<stack|distribution|identity|cloud|ecosystem|regulation|meta>",
    "blindspot": "what the map cannot currently see / is uncertain about",
    "queries_run": ["the extra-context searches tried"],
    "surfaced": "what was found (or that it was deferred)",
    "caveat": "why it's a blindspot — tier limit, disagreement, modeled, ungrounded premise, honest-unresolved",
    "severity": "l|m|h",
    "threatens": ["claim/directive/decision ids this would undermine if wrong"],
    "verify_to_close": "the exact search / scrape / benchmark / external event that closes it",
    "status": "open|mitigated|closed|unresolvable-by-research"
  }]
}
```

**Rules:** register ids match their `notes/blindspots.jsonl` line ids (one source of truth per
blindspot). `severity:"h"` blindspots threatening a `P0`/`P1` `arch_directive` MUST be surfaced in
any T10 world-map / T13 OS-Spec output, never silently dropped. Closing a blindspot updates
`status` and, where it changes a belief, emits a `lesson`.
