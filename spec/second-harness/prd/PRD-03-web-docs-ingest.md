# PRD-03 — Web & Docs Ingest (the web half of the World-Graph)

Parent: [PRD.md](../PRD.md) L0 + U11 · Status: draft v0.1
Replaces: **Firecrawl** (crawl/scrape/extract subscription), **Context7** (library-docs-on-demand subscription).

## Problem

Two subscriptions currently stand between the harness and the world: Firecrawl for pages,
Context7 for library docs. Both sell retrieval of public material plus freshness. lgwks
already owns crawl/ingest primitives (`lgwks crawl`, `lgwks extract`, `lgwks_ingest`,
shipped actor `ingest`); what's missing is coverage (hostile pages), the docs-specific
shape (versioned library docs), and freshness discipline.

## Scope

- IN: page/site ingest → fact/media artifact tree → world-graph nodes (exists; harden).
- IN: **docs mode** (the ctx7 killer): `lgwks docs <library> [version] "<question>"` —
  resolve library → its canonical docs source → ingest versioned → deterministic retrieval
  over the owned copy. Cache-first; re-crawl on version change or staleness TTL.
- IN: **frontier crawl** (U11): honest-first ladder; Camoufox rung only on true exhaustion;
  human-auth handoff, never credential theft. Robots/AUP compliance is a hard gate
  (`lgwks_aup.py` exists — wire it in-path, not advisory).
- OUT: generative summarization of pages (INV-3 — store and retrieve, never paraphrase
  into the graph). OUT: bulk-market scraping products.

## Builds on (verified shipped: ingest actor; candidates to verify)

`lgwks_ingest.py` (wrapped by U2 actor) · `lgwks_crawl.py`, `lgwks_extract.py`,
`lgwks_browser.py`, `lgwks_substrate_crawl.py`, `lgwks_site_profile.py`, `lgwks_urlrisk.py`,
`lgwks_aup.py`, `lgwks_cache.py`.

## Contract

Emits `lgwks.ingest.v1` (artifact tree) and `lgwks.docs.v1`:
`{library, version, source_url, fetched_at, chunks[], staleness_ttl}`. Consumers: PRD-04
retrieval; PRD-06 grounding (a `retrieval` hit with `evidence_tier: owned-docs`).

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 03-a docs resolver | 20-library frozen set (incl. fast-movers: next.js, anthropic sdk): resolve → correct canonical docs root, version-aware; measured against ctx7 answers on the same queries (parity bar: ≥90% answer-bearing retrieval) |
| 03-b staleness discipline | every docs artifact carries fetched_at + ttl; queries past ttl trigger async re-crawl (daemon), serve stale-marked meanwhile; never silently stale |
| 03-c AUP in-path | a disallowed URL is refused with typed error BEFORE any fetch; test proves the gate is in the call path, not advisory |
| 03-d frontier ladder | passes one Cloudflare-protected + one DataDome-protected page honest-first→escalate; ladder steps logged; human-auth rung surfaced to cockpit, never automated past auth walls |
| 03-e ingest hardening | actor `ingest` gets timeout + partial-failure envelope (carries what it got + typed error for what it didn't) |

## Open questions → SCIENCE.md

Docs-retrieval parity protocol vs ctx7 (§5 — paired eval, same questions both systems,
blind grading); staleness TTL per source class (measure doc change rates, don't guess).

RISK: replacing ctx7 badly is worse than paying for it — stale owned docs that *look*
authoritative are a grounding poison. 03-b is the load-bearing unit, not 03-a.
