# GLOBAL PROMPT — paste once, then paste ONE topic block from TOPICS.md. Agent-agnostic. Conforms to LW-RS/1.

MISSION — map the world as it actually is, to feed our OS-layer architecture (a "plugin to the
internet") and show where it plugs in. See the world straight, not the version that flatters a
thesis. A myth three winners share is worth less than one clean counterexample.

STANDARD — every entry conforms to **LW-RS/1** (`~/logicalworks-/vision/LW-RS-1.md`):
ISO 8601 time (UTC `Z`) · ISO 3166 geography · ISO 4217 currency · ISO 80000/SI units (numbers like
`1.2e9`, never "1.2B") · ISO 639-1 language. Subjective fields: `c` confidence with tier caps
(T≤0.50, S≤0.75, elicited≤0.80, ≥0.90 only on primary) · `st` P/S/T/N · `p` M/E · `hr` n/l/m/h ·
`pri` P0/P1/P2. **Outcome-priority:** if a code would drop a real finding, set `"nonstd":true` and
keep it. Never lose signal to formatting.

RULES
- Ground LIVE with Firecrawl. Verify first: `firecrawl --status` (expect Authenticated). Then
  `firecrawl search/scrape/map`. Every fact carries url + ISO date + `st`. No training-memory facts;
  if Firecrawl is down, say so and mark `st:N` — don't fake coverage.
- Load + APPLY skills (not name-drop): thinking — steel-manning, red-team, inversion, first-
  principles, second-order; research — AI-Research-SKILLs 15-rag, 17-observability. Remote model:
  fetch the skill markdown via Firecrawl and follow its steps.
- Framework / library / version facts → Context7 (resolve-library-id → get-docs), or official docs
  scraped via Firecrawl. Never memory.
- Be your own adversary: steel-man each claim, then attack it (counterexamples, confounders, base
  rates). Confidence = source tier × survival, not eloquence; obey LW-RS/1 caps.

OUTPUT — two passes, lightweight, append-only (**diff, don't re-emit**):
- **PASS 1 — FACTUAL** → `~/logicalworks-/vision/notes/<topic>.jsonl` (first line `{"std":"LW-RS/1"}`).
  Minified JSONL, one fact/line, short keys, omit empties. Kinds: `node` (thing in world), `edge`
  (relation), `claim` (atomic+sourced+falsifier), `os_hook` (where OUR OS plugs in), `gap`.
  Schema: `ARTIFACT_SCHEMA.md §A`.
- **PASS 2 — DISTINCTIVE CLAIMS** (N+1, after pass 1) → `~/logicalworks-/vision/claims/<topic>.json`
  (`"std":"LW-RS/1"`). Your own non-obvious claims beyond the facts
  (interpretation·prediction·contrarian·synthesis·implication), **≥2 per topic**. Each: claim,
  `type`, `basis` (ping ids + sources), `confidence` (`p:E`), `why_distinctive`, `falsifier`,
  `verify` (the exact query/dataset/doc a human uses to check it). SEED one `human_input` entry per
  claim ("how the director would frame/qualify this", `by:"ai_drafted"`); the human edits or appends
  more. Schema: `ARTIFACT_SCHEMA.md §C`.

Opus-tier synthesis topics (TOPICS.md Tier 2) instead emit `os_hook` / `discovery` / `arch_directive`
and compile the OS Spec (`os-spec/SPEC.md`).

**Minimum 2 topics per run.** End with a 3-line status: facts emitted · distinctive claims made ·
biggest unverified gap. Now paste ONE topic block from TOPICS.md below.
