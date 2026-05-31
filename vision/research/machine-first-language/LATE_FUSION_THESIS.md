# Jarvis Crawl Late-Fusion Thesis

Status: implementation thesis for `./lgwks jarvis crawl`

## Source Grounding

The temporal-GNN survey at `https://arxiv.org/html/2302.01018` is the useful anchor because it separates temporal graph representation into two machine-useful views:

- Snapshot-based temporal graphs represent the whole graph as a sequence of time-stamped static graphs.
- Event-based temporal graphs represent node and edge additions/deletions as a sequence of events.

The paper also frames GNNs around message passing, where node vectors are iteratively updated from neighboring features. For this crawler, every page, chunk, term, question, and understanding is a graph object, and every crawl step is a temporal event.

The important design pressure comes from the survey's category comparison and open challenges: temporal-neighborhood methods need mailbox/memory design, dense graphs can make mailboxes large, and standardized evaluation/explainability remain open problems. Jarvis should therefore keep the mailbox deterministic and auditable instead of hiding it inside an LLM trace.

## Thesis

Jarvis Crawl is a step up from a Firecrawl-style bot when it treats crawling as temporal graph construction rather than page extraction.

Firecrawl-like extraction answers: "What did this URL contain?"

Jarvis Crawl answers: "What changed in the machine-state map after each bounded crawl event, what concepts became linked, what remains underdetermined, and which question would most reduce uncertainty?"

The technical step is not "use an LLM more." The step is late fusion over multiple deterministic traces:

- Lexical signal: exact terms and n-grams.
- Structural signal: same-site links, documents, chunks, and concept mentions.
- Embedding signal: deterministic feature-hash vectors now, transformer embeddings later.
- Temporal signal: before/after snapshots and crawl events.
- Metacognitive signal: question traces with `what_were_you_thinking`, vectorized separately from research understanding.

Late fusion matters because each signal is weak alone. Lexical search misses paraphrase. Embeddings blur source accountability. Link graphs find roads but not meaning. Question traces reveal uncertainty but can pollute the research graph if stored as fact. The crawler keeps those surfaces separate until a deterministic fusion edge is emitted.

## Architecture Claim

The core model should be:

```text
crawl event -> document -> chunk -> typed concept nodes
             -> deterministic vectors
             -> late-fusion edges
             -> before/after understanding snapshot
             -> three frontier questions
```

The LLM boundary is deliberately outside the core:

- Allowed: propose better queries, summarize accepted graph state, critique unresolved edges.
- Not allowed: decide source identity, mutate crawled records, promote speculative nodes into OS intel, or overwrite deterministic edge weights.

This supports the director's "guarded LLM" goal: transformers can improve representation, but the crawler's laws stay inspectable.

## Why This Is Not A Ripoff

1. It stores understanding and questioning as separate schemas.

   Research understanding is the crawler's current map. Question traces are the crawler's uncertainty and intent. Most crawler/RAG tools collapse these into one chat transcript or summary; Jarvis keeps them independently vectorized so we can ask "what do we know?" separately from "why did the bot look there?"

2. It uses temporal graph memory instead of a flat document cache.

   A run has crawl events, snapshots, drills, documents, chunks, nodes, edges, compressed nodes, and embeddings. That makes the crawl replayable and measurable.

3. It can degrade gracefully under compute limits.

   When node count exceeds the compute budget, low-weight concepts are compressed into `compressed_nodes` with a reason. This is closer to a machine topology map than a one-shot summary.

4. It is transformer-ready without transformer dependency.

   The default embedding is deterministic 256-d feature hashing. Qwen or another local transformer can replace that provider later, but schema and graph math do not depend on provider behavior.

5. It has an explicit "next three questions" interface.

   Each keyword drill emits three questions plus expected information gain. That gives the system an Akinator-like research loop while preserving auditability.

## Defense

The survey's snapshot/event split maps directly onto the crawler:

- Snapshot: `snapshots` table records before/after graph state.
- Event: `crawl_events` records each page attempt and result.
- Temporal neighborhood/mailbox: `question_events` stores the current uncertainty mailbox for each keyword drill.
- Message passing: `late_fusion_similarity` and `mentions` edges pass evidence between chunks and concepts.

The reason this can become stronger than a page crawler is that the unit of progress is not "more pages scraped"; it is "more constrained topology." The crawler can estimate compute, ingest bounded pages, identify unresolved edges, and ask the next narrowing questions. That is the beginning of an objective machine map rather than a prettier scraper transcript.
