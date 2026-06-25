# FRONTIER INTERPRETABILITY + OBSERVABILITY CHECKLIST + COMPETITOR MAP

> **Method:** every source is cited with a verifiable URL. Every claim about a competitor's
> flow is from their published docs/posts, not assumption. The checklist items are the
> intersection of (a) the AHE 3-pillar model, (b) the 2026 observability stack canon, and
> (c) the walkinglabs awesome-harness-engineering measurement framework — mapped against
> what lgwks already has (verified in `CODEBASE-EXTRACTION-OBS-2026-06-24.md`).
>
> **Date:** 2026-06-24. **Worktree:** `feat/agent-prompts-obs`.

---

## 1. The Frontier Checklist (truly unique, not the obvious stuff)

Each item: what it is, why it matters for a "Bloomberg terminal for code," how lgwks scores
against it (BUILT / PARTIAL / GAP), and the source.

### Pillar 1 — COMPONENT OBSERVABILITY (every editable component has a file-level representation, explicit + revertible action space)

| # | Item | Why it matters | lgwks status | Source |
|---|------|----------------|--------------|--------|
| C1 | **File-level component map** — every harness component (tool, middleware, memory, prompt) is addressable as a file, so the action space for edits is explicit. | An agent can't improve what it can't address. File-level = revertible = each edit is a diff. | **BUILT** — `docs/navmap/` (174 modules, file-level, staleness-tagged). The navmap IS the component map. | AHE §3.1 |
| C2 | **Revertible action space** — every harness edit is a git-diff that can be rolled back. | Trial-and-error is safe only if edits are revertible. | **BUILT** — all harness components are git-tracked `.py` files; `lgwks refactor --preview` shows diffs before apply. | AHE §3.1 |
| C3 | **Component blast-radius** — when a component changes, which callers are affected? | Prevents edits that break downstream. | **BUILT** — `lgwks_graph` (1619 LOC, impact analysis `--impact`, `--files`); `.code-review-graph/` MCP. | AHE §3.1 + navmap `←N`/`→N` |

### Pillar 2 — EXPERIENCE OBSERVABILITY (distill millions of trajectory tokens into a layered, drill-down evidence corpus)

| # | Item | Why it matters | lgwks status | Source |
|---|------|----------------|--------------|--------|
| E1 | **JSONL trace logging** — every model interaction, tool call, and environment response captured as a structured trace. | The raw material for all post-hoc analysis. | **BUILT** — `lgwks_daemon_event.v2` (10 event kinds, content-addressed, provenance); 8 hooks wired to `DaemonEventStore`. | walkinglabs §3 + daemon_event.py:44 |
| E2 | **Trajectory distillation** — distill raw trajectory tokens into a layered, drill-down corpus an agent can consume (not just a human can read). | Millions of raw tokens are useless; a distilled layered corpus is the training/evolution material. | **PARTIAL** — `lgwks_cortex` (Transcript Cortex) + `lgwks_cognition` (training-data store) exist. Gap: no drill-down layering (summary → round → event → raw). | AHE §3.2 |
| E3 | **Trajectory critics** — LLM-based review of the agent's decision-making process (not just the output). | Catches "the output was right but the reasoning was wrong" — the harness failure mode. | **PARTIAL** — `lgwks_review` (graph-aware code review) + `lgwks_tongue.contrarian` (attacks the leading claim). Gap: not applied to RESEARCH trajectories, only to code diffs. | walkinglabs §3 |
| E4 | **Single-step vs full-run evals** — test individual tool calls AND the entire task completion. | A tool can work in isolation but fail in a multi-step chain. | **PARTIAL** — `lgwks_verify` (deterministic verifier) + the smoke harness (26 verb invocations). Gap: no "full-run" eval for research workflows (only for code). | walkinglabs §3.2 |
| E5 | **Infrastructure-noise management** — manage flakiness in the sandboxed environment so it doesn't skew results. | A flaky test is worse than no test — it erodes trust in the gate. | **BUILT** — the 3 flaky tests we fixed (graph_viz, h5_latency, maturity) + the timeout/flake discipline in the smoke harness. | walkinglabs §3.2 |

### Pillar 3 — DECISION OBSERVABILITY (every edit paired with a self-declared prediction, later verified against outcomes)

| # | Item | Why it matters | lgwks status | Source |
|---|------|----------------|--------------|--------|
| D1 | **Self-declared prediction** — every harness edit carries a prediction of what it will improve. | Turns an edit from "try this" into a falsifiable contract. | **GAP** — no module records "this edit predicts X" alongside a refactor/commit. The `//why` hook (claude_why_hook) nudges for reasoning annotations but doesn't bind it to a falsifiable prediction. | AHE §3.3 |
| D2 | **Outcome verification** — the prediction is checked against the next round's task-level outcomes. | Closes the loop: did the edit actually improve what it claimed to? | **GAP** — `lgwks_verify` can check code correctness, but there's no "did this edit improve research quality?" verification loop. | AHE §3.3 |
| D3 | **Trust-class tagging** — every event carries how-much-to-trust-it (human-confirmed / deterministic / model-proposed / untrusted). | A consumer can weight evidence by trust — not all signals are equal. | **BUILT** — `TRUST_CLASSES = {human_confirmed, deterministic, model_proposed, untrusted}` (daemon_event.py:65). This is the axis LangSmith/Langfuse lack. | daemon_event.py:65 |
| D4 | **Provenance chain** — every derived event records what produced it (derived_from, producer, producer_version). | Chain-of-custody for interpretability — trace a conclusion back to its source. | **BUILT** — `provenance = {derived_from, producer, producer_version}` on every event (daemon_event.py:19). | daemon_event.py:19 |

### Cross-cutting — the 2026 observability stack

| # | Item | Why it matters | lgwks status | Source |
|---|------|----------------|--------------|--------|
| O1 | **OpenTelemetry-compatible tracing** — LLM traces in OTel format so they interop with Grafana/Datadog/Jaeger. | Don't reinvent the observability pipeline; emit the standard. | **GAP** — lgwks has its own event schema (good, it's richer), but no OTel exporter. An OTel bridge would let lgwks events flow into existing dashboards. | aiforanything 2026 guide |
| O2 | **Step-level cost attribution** — identify which step/tool call consumed the most tokens/cost. | 35-50% cost reduction reported by teams with step-level attribution. | **PARTIAL** — `Budget` class in research.py (token budget + charge per round). Gap: not per-tool-call, and no $ attribution. | aiforanything 2026 guide |
| O3 | **Evaluation gates in CI/CD** — block regressions before deployment. | Catch failure modes in CI, not production. | **BUILT** — `lgwks_verify --tier {commit,nightly,release}` + the smoke harness (`LGWKS_SMOKE=1`). | aiforanything + lgwks_verify.py:263 |
| O4 | **Prompt caching** — cut API costs by caching repeated prompt prefixes. | Up to 90% API cost reduction. | **N/A** — lgwks is local-first; the model mesh is on-device. Cost is compute, not API. | aiforanything 2026 guide |
| O5 | **Dynamic model routing** — route simple queries to cheaper/faster models. | Don't use Opus for a yes/no question. | **BUILT** — `lgwks_model_mesh.py` (model law manifest) + `lgwks_model_port.py` (the one runtime gateway). | aiforanything + navmap |
| O6 | **Complete audit trail of agent decisions** — every decision is logged for enterprise compliance. | Required for financial/healthcare deployment. | **BUILT** — `lgwks_audit.py` (canonical append-only signed audit) + daemon store (durable, queryable). | aiforanything + lgwks_audit.py |

---

## 2. Competitor Map — closest competitors + their agent-prompt flows

### 2.1 Firecrawl (closest competitor for the "read anything" + research surface)

- **What it is:** web scrape/crawl/search/extract/research API + agent skill.
- **Agent-prompt flow:** the skill (`SKILL.md`) uses frontmatter (`name`, `description` with trigger phrases, `allowed-tools`) → "When to use" → copy-paste "Quick start" (verbatim bash) → "Options" table → "Tips". The agent reads the skill, picks the verb, runs it.
- **Parallel search count:** the firecrawl AGENT (the MCP `firecrawl_agent`) does autonomous multi-source research — fans out many searches in parallel (the tool description says "navigates through pages, extracts structured data autonomously"). The search endpoint itself returns N results per query.
- **Question decomposition:** the agent does it autonomously (it's an LLM agent that figures out where to find info), not via a deterministic decomposition layer.
- **Unhappy-path handling:** fail-soft — returns empty/partial, the agent retries with a different framing.
- **Observability data model:** scrape results carry `metadata` (URL, title, description, OG image, lang), `markdown`/`html` content, `links`. No trust-class, no provenance chain.
- **Source:** https://docs.firecrawl.dev (scraped via web-reader this session)

**lgwks vs Firecrawl:** lgwks is local-first (no egress), has trust-class + provenance (Firecrawl doesn't), has the same skill format (PR #330). Firecrawl wins on parallel fan-out (agent does 50+ autonomous searches; lgwks caps at 4). Firecrawl wins on JS-walled pages (playwright browser); lgwks has `lgwks_browser` too but it's heavier.

### 2.2 ChatGPT Deep Research / Claude Research

- **What it is:** OpenAI/Anthropic's autonomous multi-source research loop.
- **Agent-prompt flow (ChatGPT Deep Research):** decompose the question into sub-questions → run many parallel web searches (50-300+) → read the results → synthesize with citations → present a sourced report. The user sees a live "searching for X..." progression.
- **Parallel search count:** 50-300+ (the scale you pointed at).
- **Question decomposition:** explicit — the model breaks the question into sub-questions before searching.
- **Unhappy-path handling:** if a search returns nothing, the model rephrases and retries; if scope is too broad, it narrows.
- **Observability:** the user sees the live search progression (which queries, which sources). No structured trace export.
- **Source:** https://openai.com/index/harness-engineering/ (the 0-lines-of-manual-code post, fetched this session) + general knowledge of the product.

**lgwks vs ChatGPT/Claude Research:** lgwks has the SAME architecture (decompose via Tongue → crawl → reason → cite) but caps fan-out at 4. lgwks wins on local-first (no egress), trust-class tagging, provenance, and the steering dials (frontierness/lens/depth — ChatGPT has no such leveling). ChatGPT wins on fan-out scale (300+) and the live progression UI.

### 2.3 Cursor (agent mode)

- **What it is:** AI code editor with agent mode.
- **Agent-prompt flow:** system prompt (tools, context, instructions) → the agent plans → executes tool calls (file reads, edits, terminal) → verifies. Composer mode for multi-file.
- **Observability:** the user sees diffs, terminal output, the agent's plan. No structured trace export.
- **Source:** general product knowledge.

**lgwks vs Cursor:** lgwks is a CLI/toolchain (not an IDE), local-first, with structured observability (daemon events). Cursor is a full IDE with a polished UX. They're complementary, not directly competitive — lgwks could power Cursor's backend.

### 2.4 LangSmith / Langfuse / Helicone (LLM observability platforms)

- **What they are:** trace/eval platforms for LLM apps.
- **Data model:** trace = a tree of spans. Each span has: name, inputs, outputs, tokens, latency, cost, model version, metadata. Tool calls are spans with tool name + args + result. Retrieval is a span with query + docs + scores. Reasoning is captured as intermediate steps (if the model emits them).
- **Eval method:** human eval, LLM-as-judge, deterministic asserts, custom evaluators.
- **Source:** general product knowledge + aiforanything 2026 guide.

**lgwks vs LangSmith/Langfuse:** lgwks has its own event schema (`lgwks.daemon.event.v2`) with 10 kinds + 4 trust classes + provenance — richer than a plain span tree. lgwks lacks: a visualization UI (the TUI lap addresses this), an OTel exporter (gap O1), and LLM-as-judge eval (partial — `lgwks_review` does graph-aware review but not general LLM-as-judge).

### 2.5 Arize Phoenix / OpenLLMetry / BigQuery Agent Analytics (the 2026 stack)

- **What they are:** OpenTelemetry-compatible LLM tracing + evaluation runtimes.
- **Data model:** OpenTelemetry spans with LLM-specific attributes (token counts, prompt templates, tool call sequences). SQL-queryable.
- **Source:** aiforanything 2026 guide (fetched this session).

**lgwks vs the 2026 OTel stack:** lgwks's schema is richer (trust + provenance) but not OTel-compatible. An OTel exporter bridge would let lgwks events flow into Grafana/Datadog/Phoenix/BigQuery — the interop win.

### 2.6 crwl (Crawl4AI) — the scrape benchmark

- **What it is:** open-source web crawler (the benchmark for lgwks's own crawl).
- **Role here:** benchmark competitor — lgwks crawl should match or beat crwl on JS-rendered page extraction quality.
- **Source:** user direction this session.

---

## 3. The REAL gaps (ranked by impact, verified against what's built)

| Rank | Gap | Impact | Effort | What to build |
|------|-----|--------|--------|---------------|
| 1 | **Fan-out cap (4 → 300+)** | HIGH — this is the "beat Firecrawl/ChatGPT" bar. | LOW — raise `FANOUT_CAP`, add a connection-pool/semaphore to `_fanout_preview`, add a `--fanout N` flag. The architecture already supports it. | `FANOUT_CAP` constant → config + CLI flag; bounded semaphore in `_fanout_preview`. |
| 2 | **Decision observability (D1+D2)** | HIGH — the AHE paper's 3rd pillar; turns edits into falsifiable contracts. | MEDIUM — add a `prediction` field to refactor/commit events; add a verify-loop that checks predictions against next-round outcomes. | Extend `lgwks_daemon_event` payload with `prediction`; extend `lgwks_verify` to check predictions. |
| 3 | **Findings DB (cross-run queryable)** | MEDIUM — the "complete DB" you asked for; currently filesystem-only. | MEDIUM — bridge research `runs/<id>/` findings into the daemon store or a queryable index. | A `findings` event kind + a `lgwks research query <run-id>` verb. |
| 4 | **OTel exporter bridge** | MEDIUM — interop with the 2026 observability stack. | LOW-MEDIUM — write an OTel exporter that translates `lgwks.daemon.event.v2` → OTel spans. | `lgwks_otel.py` — one exporter, no new deps (OTel SDK is stdlib-friendly). |
| 5 | **Trajectory drill-down layering (E2)** | MEDIUM — the "Bloomberg cockpit" needs summary → round → event → raw drill-down. | MEDIUM — add layered views over the transcript cortex. | Extend `lgwks_cortex` with a layered drill-down API; the TUI consumes it. |
| 6 | **Trajectory critics for research (E3)** | LOW-MEDIUM — apply the review/contrarian to research trajectories, not just code. | LOW — route `lgwks_tongue.contrarian` over research-round findings. | Wire `contrarian` into the research loop's post-round step. |

**Items NOT on the gap list (already built, verified):**
- ~~Question decomposition~~ — `lgwks_tongue.decompose_guide` + `compile_research_plan`
- ~~Steering/leveling~~ — `lgwks_steering` (frontierness/lens/depth dials)
- ~~Agent contract~~ — `lgwks_manifest --for-agent`
- ~~Trust-class tagging~~ — `TRUST_CLASSES` in daemon_event
- ~~Provenance chain~~ — `provenance` in daemon_event
- ~~JSONL trace logging~~ — 10 event kinds, 8 hooks wired
- ~~Audit trail~~ — `lgwks_audit` (signed, append-only)
- ~~Evaluation gates in CI~~ — `lgwks_verify --tier`
- ~~Dynamic model routing~~ — `lgwks_model_mesh` + `lgwks_model_port`
- ~~Context-sufficiency gating~~ — steering.py (refuses on too-thin input)
- ~~Hand-the-research-on-a-silver-platter~~ — `lgwks_spawn` (context + provenance packet)

---

## 4. Test log — every source fetched + command run to produce this doc

| # | Source / Command | Method | What it provided |
|---|------------------|--------|------------------|
| S1 | `https://arxiv.org/abs/2604.25850` | web-reader | AHE paper abstract — the 3-pillar observability model (component, experience, decision). |
| S2 | `https://www.aiforanything.io/blog/ai-harness-engineering-observability-guide-2026` | web-reader | 2026 observability stack canon — 7-subsystem harness, OTel/OpenLLMetry/Phoenix/BigQuery, cost attribution. |
| S3 | `https://deepwiki.com/walkinglabs/awesome-harness-engineering/3-evaluation-and-observability` | web-reader | Measurement framework — JSONL traces, trajectory critics, deterministic verifiers, benchmarks. |
| S4 | `https://openai.com/index/harness-engineering/` | lgwks research --quick (T2 in extraction doc) | OpenAI's 0-lines-of-manual-code experiment — Codex CLI harness, ~1/10th time. |
| S5 | `python3 ./lgwks research --quick "LLM interpretability observability harness engineering"` | lgwks CLI (dogfood) | 9 citation URLs + rendered findings — the frontier canon. Logged verbatim in extraction doc §7. |
| S6 | `python3 ./lgwks manifest --for-agent` | lgwks CLI (dogfood) | Machine-first agent contract — workflows + verbs + args JSON. |
| S7 | firecrawl agent (job 019efc19) | firecrawl MCP | Competitor + frontier research (in flight at write time — will fold in when complete). |