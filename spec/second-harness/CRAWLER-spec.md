# lgwks-crawler — Frontier Non-LLM Crawler (spec + status)

Status: **v0 · core BUILT, TESTED, LIVE-VERIFIED** · 2026-06-09
Crate: [`crawler/`](../../crawler) · binary `lgwks-crawler` · lib `lgwks_crawler` · contract `lgwks.crawl.v1`

## What it is

A standalone Rust web crawler with **zero LLM in the loop**. Noisy/overlapping bot
output is cleaned deterministically (content-id + simhash) before any model sees it.
One contract, three surfaces — the AI calls the same API the end-product frontend calls:

- **library** — `lgwks_crawler::crawl(config, seed) -> CrawlResult`
- **CLI** — `lgwks-crawler crawl <url>` (JSON to stdout) · `lgwks-crawler serve`
- **HTTP API** — `POST /crawl {CrawlRequest} -> CrawlResult` · `GET /healthz`

Ethic (carried from the Python crawler + PRD): **honest-first**. Identify truthfully,
respect robots, stay polite by default. Stealth is an explicit escalation ladder, never
the default.

## The stealth ladder (escalation, opt-in)

| Level | Behaviour | robots |
|---|---|---|
| `honest` (default) | identifies as `lgwks-crawler/0.1 (+url)` | strict |
| `browserlike` | real desktop browser UA + full header set | strict |
| `rotating` | deterministic UA/locale rotation per (host, attempt) | strict |
| `aggressive` | rotation + retry-past-soft-blocks; for authorized targets only | override required |

## Competitive coverage (googlebot · crawlee · firecrawl · wget)

| Capability | Source of art | Status |
|---|---|---|
| robots.txt + Crawl-delay | googlebot, wget | **BUILT** (`robots.rs`, `texting_robots`) |
| conditional GET / freshness (304) | googlebot | **BUILT** (`fetch.rs` etag/if-modified-since) |
| politeness + adaptive backoff + jitter | googlebot, crawlee | **BUILT** (`politeness.rs`, deterministic) |
| frontier queue (BFS / best-first), dedup, host-scope | crawlee, wget | **BUILT** (`frontier.rs`) |
| fingerprint rotation (deterministic) | crawlee | **BUILT** (`fingerprint.rs`) |
| HTML → markdown + links + canonical | firecrawl | **BUILT** (`extract.rs`, `scraper`) |
| content dedup (exact) + near-dup (simhash) | (noise control) | **BUILT** (`dedup.rs`) |
| recursion + host scoping | wget | **BUILT** |
| sitemap.xml → frontier seeding | googlebot | **DESIGNED** (dep present, parser not wired) |
| JS rendering (headless browser) | firecrawl, crawlee | **DESIGNED** (HTML-only today; render-provider port; Python has playwright) |
| proxy pool / rotation | crawlee | **DESIGNED** |
| TLS/JA3 fingerprint shaping | (advanced anti-detect) | **DESIGNED** |
| auth handoff ladder + click discovery | (Python `_crawl_site`) | **DESIGNED** (carry forward) |
| per-host concurrency + autoscaling | crawlee | **DESIGNED** (engine is sequential today) |
| persistent/resumable frontier, mirroring | wget | **DESIGNED** |
| non-HTML content (PDF, feeds) | firecrawl | **DESIGNED** |

## Deterministic noise minimization (the non-LLM clean-up)

- **exact dedup** — `cid = blake2(normalize(text))`; normalization = lowercase + whitespace-collapse.
- **near-dup** — 64-bit simhash over tokens; Hamming distance ≤ `near_dup_distance` (default 3) drops it.
- **link hygiene** — non-http(s) schemes (mailto:, js:) dropped; fragments stripped; URLs canonicalized (default ports, case, fragment).
- **frontier as audit log** — every URL ends with an explicit terminal status (`fetched·blocked·robots_disallowed·duplicate·near_duplicate·error·http_error·depth_exceeded·not_modified`); nothing silently dropped.

All of the above is a pure function of input — replayable, zero RNG, zero model.

## API contract (`lgwks.crawl.v1`)

`CrawlRequest`: `{ url, max_pages?, max_depth?, stealth?, allow_offsite?, respect_robots?, min_host_delay_ms?, best_first? }`
`CrawlResult`: `{ schema, run_id, seed, pages[], frontier[], stats }`
`Page`: `{ cid, url, canonical_url, title, text, markdown, links[], depth, discovered_by, http{...}, simhash, word_count, fetched_at }`

## Verification (evidence)

- `cargo test` → **22 passed, 0 failed**, 0 warnings, clean build (cargo 1.95, edition 2024).
- live: `lgwks-crawler crawl https://example.com --max-pages 1 --max-depth 0` → HTTP 200 over rustls (18ms), title/text/markdown/links extracted, robots fetched, frontier `fetched`, valid `lgwks.crawl.v1`.

## Module map

`config` (knobs + ladder) · `schema` (wire contract) · `error` (typed) · `fingerprint` (rotation) ·
`dedup` (cid + simhash) · `robots` · `politeness` · `extract` · `frontier` · `fetch` (async) ·
`engine` (orchestrator) · `api` (axum) · `main` (clap CLI).

## v0.2 additions (built + tested this pass)

- **One upstream entry** — `gather(GatherRequest{ url, mode })` with modes `scrape | map | crawl` (firecrawl's separate endpoints collapsed to one call). `POST /gather` + `lgwks-crawler gather <url> --mode`. A `search` mode (web-search → gather) is the next mode; it needs a search provider and is intentionally NOT faked.
- **Asset capture (wget-style)** — `extract.rs` now captures external JS/CSS/img URLs (resolved absolute) and fingerprints inline JS/CSS (byte count + cid) instead of stripping them. `Page.assets`.
- **Cleanup/synthesis = chunks + hashes** — `chunk.rs` windows each page's text (320-word / 48 overlap, matching the Python substrate) into content-addressed `Chunk{ cid, simhash, position, ... }`. `Page.chunks`.
- 30 tests pass, 0 warnings.

## Firecrawl-class bypass — where we stand (honest)

What lets firecrawl-class services bypass Cloudflare/DataDome/PerimeterX:
1. **real headless browser** (JS execution + a genuine DOM) with stealth patches (hide `navigator.webdriver`, spoof canvas/WebGL/audio fingerprints);
2. **residential/rotating proxy pools** (IP reputation + geo);
3. **TLS/JA3 + HTTP/2 fingerprint matching** so the handshake looks like a real Chrome, not a library;
4. **CAPTCHA handling** (solver services or human handoff).

**Our Rust bot has NONE of these yet** — it is honest HTTP/2 via reqwest+rustls, HTML-only. So against a hard anti-bot wall it will be blocked. We are *not* hardened to bypass that class today. The Python side has playwright (real browser) + an auth-handoff ladder + fingerprint pools — partial, and the honest-first escalation lives there. Path to parity (designed, provider ports): `RenderProvider` (chromiumoxide or reuse Python playwright over IPC) → `ProxyProvider` (pool + rotation) → TLS-fingerprint transport. Sequenced after the core, called only on the `aggressive` rung, for authorized targets.

## Hashing — what was done, and the decision you must make

- **What I did:** exact dedup + audit anchor = `blake2b(normalize(text))` → `cid-…`; near-dup = 64-bit simhash (FNV-1a tokens); each chunk carries both.
- **The conflict:** axiom's Rust CID island uses **blake2**; the Python substrate uses **sha256** (`io._sha`). We now have two content-address schemes. The crawler feeds the substrate, so the keys must agree.
- **Recommendation:** make **blake2b the one canonical CID** (axiom is the designated content-addressing authority per the nervous-system doc) and migrate the substrate's `_sha`, OR — if churn is unacceptable — switch the crawler to sha256 to match the substrate today. Your call; flagged, not silently chosen.

## Open / next (honest)

1. JS rendering is the biggest gap vs firecrawl/crawlee — needs a headless-browser provider port (Python side already has playwright; decide reuse vs native Rust `chromiumoxide`).
2. Sitemap parsing is one module from done (dep present).
3. Concurrency: engine is sequential per run; per-host-concurrent + global autoscale is the throughput unlock.
4. Where this lands in the larger rebuild: it is the `Crawl` seam from [REBUILD-v0-draft.md](REBUILD-v0-draft.md) — the substrate spine calls it; the `embed`/graph stages (out of scope here) consume its `CrawlResult`.
