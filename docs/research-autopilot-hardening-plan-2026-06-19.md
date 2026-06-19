# LGWKS Research Autopilot Hardening Plan - 2026-06-19

## Why This Exists

LGWKS is trying to formalize LLM development, not just wrap another search API.
Use the airplane analogy as the architecture boundary:

- Core model: the airplane. Powerful, non-deterministic, not sufficient by itself.
- Harness: controls, instruments, checklists, telemetry, and flight recorder.
- LGWKS: autopilot plus mayday alarm. It routes context, checks evidence, fails closed, and records what happened.
- Keel: assurance discipline. Requirements, design, code, tests, traceability, and regression evidence.

The immediate failure was concrete: `do research` could return a successful process
exit even when substrate produced zero documents/chunks, and research did not route
the unified cross-repo brain before searching.

## Fix Landed In This Pass

- Added `lgwks_research_memory.py`, a read-only adapter over
  `/Users/srinji/ingestion_results/unified_agent_brain_multimodal.db`.
- Added `lgwks state brain stats|recall` so prior context can be inspected directly.
- Added a `brain:recall` phase to `lgwks do research`, enabled by default.
- Added `--brain-db`, `--recall-limit`, and `--no-brain-recall` controls.
- Made `do research` fail closed when substrate returns no materialized documents or chunks.
- Added tests for unified-brain recall, integrated research recall, and empty-crawl fail-closed behavior.

Observed local brain state on 2026-06-19:

- `research`: 0 rows
- `chronicle`: 262 rows
- `timeline`: 365 rows
- `intelligence`: 102 rows
- `perception`: 1234 rows

That means recall must currently query non-research tables. A future writeback path
must populate `research` after each run.

## Firecrawl Hardening Notes To Preserve

Input artifact: `/Users/srinji/Downloads/extract-data-2026-06-19-2.json`.

Important design signals from that export:

- Search quality needs a provider broker, not a single provider.
- Use BM25/RRF/MMR-style ranking and diversity instead of raw provider order.
- Deep research systems use planner DAGs, search/research/write agents, reranking,
  and map/reduce summarization.
- Latency and throughput must be modeled with Little's Law and provider concurrency limits.
- Web crawl scope, source count, webhooks, and cost need explicit budgets.
- OpenAI/Gemini-style deep research reads hundreds of sources; LGWKS needs measurable
  source-depth modes instead of a hidden fixed crawl limit.

## Required Product Contract

For any serious `research` command, LGWKS must emit:

- Intent: original prompt, refined objective, assumptions, and unresolved questions.
- Prior context: unified brain hits, matched terms, missing terms, and provenance.
- Search plan: provider list, query DAG, source budget, diversity policy, and stop rule.
- Evidence ledger: every source considered, every source accepted, every source rejected, and why.
- Synthesis: claims tied to evidence ids, with abstentions where coverage is weak.
- Writeback: durable embeddings/summaries for future recall.
- Mayday alarms: explicit degraded verdicts for empty crawls, low source count, missing
  prior-context routing, no writeback, citation gaps, or provider collapse.

## Next Fix Sequence

1. Research writeback
   - After every substrate/research run, insert summaries into the `research` table with
     `filepath`, `type`, `dense_summary`, `content_hash`, `metadata`, and `timestamp`.
   - Acceptance: repeat the same metacognition prompt and verify the second run recalls
     prior research rows, not only generic `intelligence` rows.

2. Daemon routing
   - Ensure `lgwks do research` and `lgwks research --deep` emit daemon events and index
     runs through `ops daemon research` or the daemon store directly.
   - Acceptance: JSON output includes a daemon event id, run id, and store lookup path.

3. Search broker
   - Create a provider contract with normalized fields: `url`, `title`, `snippet`,
     `provider`, `rank`, `published_at`, `license`, `cost`, and `confidence`.
   - Fuse providers with RRF, rerank with BM25, diversify with MMR.
   - Keep DuckDuckGo/Mojeek as free fallbacks, but add clean seams for Google/Brave/SerpAPI,
     Firecrawl, OpenAI tools, and future local indexes.
   - Acceptance: provider collapse degrades the run but does not silently return shallow research.

4. Planner DAG
   - Convert refined research intent into a DAG of subquestions before crawling.
   - Use topological execution and map/reduce synthesis.
   - Acceptance: output shows subquestions, source allocation per subquestion, and uncovered nodes.

5. Clarification and `/grill-me`
   - Use the Human Assumption Decoder before expensive research when the prompt has missing
     scope, timeframe, source class, or output shape.
   - Acceptance: ambiguous prompts produce targeted questions; precise prompts execute directly.

6. Evaluation harness
   - Add regression prompts comparing LGWKS against the two Firecrawl exports and deep-research
     expectations: source count, coverage, novelty, evidence density, and future recall.
   - Acceptance: CI has deterministic offline fixtures and optional live-search tests.

7. Keel traceability
   - Write requirements, design notes, code links, tests, and review evidence for each research
     subsystem.
   - Acceptance: every behavior above maps to a test or a deliberate open risk.

## Continuation Protocol When Context Runs Out

Start with these commands:

```bash
cd /Users/srinji/logicalworks-
git status --short --branch
sed -n '1,220p' docs/navmap/README.md
./lgwks state brain stats --json
pytest -q tests/test_research_memory.py tests/test_daemon.py
```

Then inspect these files in order:

- `lgwks_research_memory.py`
- `lgwks_do.py`
- `lgwks_research.py`
- `lgwks_daemon.py`
- `lgwks_search.py`
- `docs/research-autopilot-hardening-plan-2026-06-19.md`

Do not start by refactoring. First preserve the fail-closed contract and the
prior-context routing. The next smallest high-leverage patch is research writeback.
