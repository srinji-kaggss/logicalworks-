# Research Protocol — the map as it is, not as we wish

> Cold-start doc. An agent reads this first and knows how to run a claim through the engine.
> Sister files: `ARTIFACT_SCHEMA.md` (output format), `REFERENCES.md`, `artifacts/` (outputs).
> Governing intent: **produce the world map as AI sees it, not the map AI wants AI to see.**
> Every mechanism below exists to fight motivated reasoning, confirmation, and false precision.

---

## 0. The one rule everything serves

A claim earns confidence only by **surviving a genuine attempt to kill it on live evidence**.
Agreement that was never tested is worth ~0. A myth that three winners happen to share is worth
less than one clean counterexample. We optimize for *calibration*, not for being impressive.

---

## 1. Eleven enforced principles

1. **Grounding-first, memory-banned.** Every fact comes from a source pulled *live this session*
   (Firecrawl → see §5), carrying `url` + `retrieved` date + a **source tier**. No training-memory
   facts. If you can't pull it, you can't assert it — say "unverified."
2. **Source tiers, and confidence bounded by them.** `primary` (filings, law, peer-reviewed,
   regulator data) > `secondary` (reputable press, analyst reports) > `tertiary` (blogs, vendor
   marketing). A claim's confidence is *capped* by its best tier. Tertiary-only ⇒ confidence ≤ 0.5.
3. **Provenance separation.** Tag every number `measured` (sourced) or `elicited` (model judgment).
   Elicited numbers are ordinal hints, never cited as fact. Never blur the two.
4. **Adversarial by construction.** A claim is researched by two agents spawned *together and blind
   to each other*: a THESIS (applies steel-manning — strongest true version) and an ANTITHESIS
   (applies red-team + inversion — assume false, hunt the kill shot). Neither may strawman.
5. **The author never scores their own work.** Confidence is set by a *separate* ADJUDICATOR agent
   that did not write either side. The CLI/orchestrator **reports** that score and flags where it
   disagrees — it does not invent its own. (Kills self-serving scoring.)
6. **Convergence is the exit, not a number.** Stop when the two sides stop moving each other —
   either they agree (synthesis) or they isolate a clean, stable disagreement neither can break.
   **There is no 98% gate.** A confidence target is an invitation to rationalize toward it.
   Record `residual_disagreement` honestly; unresolved is a valid, valuable end state.
7. **Base rates over anecdotes.** Demand denominators. Run the survivorship check: "what's the
   base rate among everything that tried this, not just the survivors that did?" The C01 myth died
   here — reasoning from 3 winners ignored Alipay/Grab/Gojek (no messaging) and WhatsApp (messaging,
   no super-app).
8. **Falsification mandate.** Every surviving claim must state the observation that would overturn
   it. Unfalsifiable claims are downgraded and flagged, never accepted at face value.
9. **Hallucination register.** Any claim asserted *above* its source strength — confident tone,
   thin/absent grounding, extrapolation from pre-launch or single cases — is logged with a risk
   level. This is mandatory output, not optional.
10. **Delta log.** Record belief *before* → *after* → the specific evidence that flipped it. If
    nothing changed, say so and why (genuine confirmation vs. failure to look). The map must be
    seen changing under evidence.
11. **Calibration honesty.** Confidence reflects source tier × adversarial survival × base-rate
    support — not eloquence. A well-argued claim with weak sources scores low. Penalize fluency.

---

## 2. Triage gate (this is how we stay accurate AND quick)

Not every claim earns the full engine. A cheap first pass scores each claim on two axes:

- **decision-weight** — does being wrong change what we build / decide? (low / med / high)
- **contestedness** — do sources or the two agents actually disagree? (low / med / high)

| | low contest | high contest |
|---|---|---|
| **low weight** | single grounded pass, log & move on | single pass + note the dispute |
| **high weight** | grounded pass + falsifier | **FULL dialectic + recursion (§3)** |

Only **high-weight × high-contest** claims get the expensive recursion. Everything else gets one
honest grounded pass. This is the lever — depth where being wrong is costly, speed everywhere else.

---

## 3. The loop (per claim that clears triage)

```
Pass 0  TRIAGE      cheap classify → route per §2 table
Pass 1  DIALECTIC   spawn THESIS ‖ ANTITHESIS, blind, grounded (§5). Each returns: strongest
                    position, sourced evidence, load-bearing assumption, self-confidence + why.
Pass 2  ADJUDICATE  independent ADJUDICATOR reads both → convergence read, calibrated confidence,
                    residual_disagreement, hallucination flags. (Author ≠ scorer, §1.5)
Pass 3  RECURSE     ONLY if still contested AND high-weight: the unresolved crux spawns up to 3
                    focused sub-probes (each a narrow, falsifiable sub-question). Re-adjudicate.
                    Exit on convergence OR budget cap — NOT on hitting a confidence number.
EMIT    artifact (extended RAC) + lessons.json (variable-N) + delta_log + hallucination_register
```

Budget cap replaces the 98% gate: e.g. max 2 recursion rounds. If unresolved at the cap, ship it
as `residual_disagreement` with both positions and the matched-comparison that *would* settle it.
Unsettled-but-honest beats settled-but-fabricated.

---

## 4. Lessons — variable-N, not fixed

A "lesson" is persisted only if it **changed a belief or killed a myth**, with an evidence span.
Keep as many as survive the dialectic; **minimum 1, no fixed count** (fixed-5 forces padding or
truncation). Each lesson is one JSON entry per `ARTIFACT_SCHEMA.md §Lessons`. A confirmed prior is
a valid lesson (`type: belief_confirmed`) — but only if it was genuinely attacked and held.

---

## 5. Firecrawl — verified grounding (NOT optional, NOT silent)

Firecrawl is the grounding engine. But it must be **verified before trusted**, and degradation
must be **logged, never hidden** (silent fallback is the map-AI-wants-to-see).

**Step 1 — verify auth, loudly:**
```bash
firecrawl --status            # must show authenticated + credits
```
If it shows **Not authenticated** or `FIRECRAWL_API_KEY` is unset, the agent MUST (a) record
`grounding_tool: "firecrawl UNAVAILABLE — fell back to WebSearch"` in the artifact, and (b) NOT
pretend Firecrawl-grade coverage. Falling back is allowed; hiding it is not.

**Step 2 — use it (non-interactive):**
```bash
firecrawl search "<query>" --limit 5      # discover primary sources
firecrawl scrape <url>                     # pull to clean markdown in .firecrawl/
firecrawl map <site>                       # enumerate a site's URLs
firecrawl crawl <site>                     # multi-page pull
firecrawl parse <local-file>               # PDF/DOCX/XLSX → markdown
firecrawl agent "<extraction prompt>"      # agentic multi-step extraction
```
Auth for non-interactive use is via `FIRECRAWL_API_KEY` env var or `firecrawl --api-key <key>`.
The local Skill-tool equivalents (`firecrawl:firecrawl-search/-scrape/-map/-crawl/-agent`) are
acceptable substitutes when running inside Claude Code.

**Prefer Firecrawl over a model's built-in browse** for structured/clean pulls and for
login-gated, JS-heavy, or non-English sources (where training memory is least reliable).

---

## 6. Anti-self-deception checklist (run before EMIT)

- [ ] Every `measured` fact has a live URL + tier. No memory facts smuggled in as fact.
- [ ] The antithesis produced a *real* attack, not a token one. If it couldn't, say why.
- [ ] Base rate / survivorship checked — did we reason only from winners?
- [ ] Confidence set by adjudicator (not author), bounded by source tier.
- [ ] Every surviving claim has a falsifier.
- [ ] Hallucination register populated (or explicitly "none, and here's why").
- [ ] Delta log shows what changed — or honestly states nothing did.
- [ ] Residual disagreement recorded, not papered over.

If any box can't be ticked, the artifact is `provenance: elicited` and confidence is capped low.
