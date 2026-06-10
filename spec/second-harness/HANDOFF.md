# Handoff — lgwks rebuild (crawler landed) · 2026-06-09

You are the next agent on the lgwks rebuild. Read this fully before acting. It is
written AI-for-AI; the Director's trust is low after a long session of me
oversimplifying, over-sprawling, and asserting before verifying. Do not repeat that.

## Hard constraints (do not violate)

1. **The model layer is OUT OF SCOPE.** Do not spec, map, or touch it. The Director
   said so explicitly and repeatedly — it is "worse than imagined" and gets its own
   session with him driving. Treat all models (Eye/Tongue/Membrane, Ollama, Gemini,
   CoreML) as opaque dependencies. The text=local-Qwen / media=cloud-Gemini
   (`google/gemini-embedding-2` via OpenRouter) split is INTENDED design — never change
   the Gemini model; if a step needs it, STOP AND ASK.
2. **Verify before you assert.** Every claim about env/git/files/tests runs the command
   first. The compiler/test-runner is the verifier — claim nothing as working until
   `cargo test` / `pytest` proves it.
3. **No emojis. No sprawl.** Receipts, not essays. Don't mirror the Director's
   thinking-out-loud on output.
4. **On a real fork in the Director's intent, ASK (use AskUserQuestion) — don't guess.**
   But don't ask what the code can answer; read the code.
5. **Crawl ethic = honest-first.** Respect robots by default; stealth is a configured
   escalation rung, never the default.

## What this session built (verified)

A standalone Rust crawler: **[`crawler/`](../../crawler)** — crate `lgwks-crawler`,
contract `lgwks.crawl.v1`. **30 tests pass, 0 warnings, live-verified against
example.com.** Spec: [CRAWLER-spec.md](CRAWLER-spec.md).

- One upstream entry: `gather(GatherRequest{url, mode})`, modes `scrape|map|crawl`
  (firecrawl's endpoints collapsed to one call). Three surfaces: lib `gather()`,
  CLI `lgwks-crawler gather`, HTTP `POST /gather` (+ `/crawl`, `/healthz`).
- BUILT: BFS recursion, robots+crawl-delay, per-host politeness + deterministic
  backoff/jitter, conditional GET (304), reqwest/rustls fetch w/ retry, HTML→markdown
  +links+canonical, **asset capture** (JS/CSS/img URLs + inline-asset cids),
  **deterministic noise-min** (blake2b cid exact-dedup + simhash near-dup),
  **chunking** (320w/48 overlap, content-addressed `Chunk`), frontier-as-audit-log.
- Module map: `config schema error fingerprint dedup robots politeness extract
  frontier fetch engine chunk gather api main`.

## NOT built (honest gaps — do not claim otherwise)

- **Anti-bot bypass** (the firecrawl-class hole): no headless browser, no proxy pool,
  no TLS/JA3 fingerprinting. Honest HTTP/2 only → hard walls (Cloudflare/DataDome)
  block it. Provider ports designed (`RenderProvider`/`ProxyProvider`), not wired.
- wget-completion: no disk-mirror, link-rewrite, or resumable re-crawl.
- `search` mode (web-search→gather): needs a search provider; intentionally not faked.
- Per-host concurrency / autoscaling: engine is sequential per run.

## Decisions locked this session

- End state: "all of it eventually (Axiom under lgwks under the subconscious), but the
  **daemon ships Day 1**." The daemon is the AI's subconscious + the math doing PM/
  AI-management (gate work, sequence scope, score output, auto-write governance).
- lgwks today is a CLI; the end state grows it into a stateful daemon (per
  [../PRD.md](../PRD.md) §14) + a human **neo-IDE** consumer over the same JSON
  control bus (CLI is the control bus, not the UI — see machine-nervous-system.md).
- Crawler = Rust (settled). The 107 Python modules collapse to ~6 real capabilities;
  the work is extracting working fragments from scattered half-implementations.

## Open decisions — need the Director (ask, don't assume)

1. **Daemon language** — Go (speed) vs Rust (fleet-consistency w/ axiom/logic-os-kernel).
   The crawler is Rust; the daemon is undecided. Nervous-system doc favors
   Python-orchestrator + Rust-seams + daemon-last.
2. **Canonical content-address scheme** — axiom=blake2, substrate=sha256, crawler=blake2b.
   Must unify (recommend blake2b, migrate substrate). Correctness issue.
3. **Next crawler lift** — bypass stack (headless+proxy+TLS-fp) vs wget-completion vs
   `search` mode. Director was asked; answer pending.

## Doc map

- [../PRD.md](../PRD.md) — end-state authority (subconscious daemon).
- [prd/INDEX.md](prd/INDEX.md) — decomposed PRDs (PRD-01..10).
- [../../docs/machine-nervous-system.md](../../docs/machine-nervous-system.md) — runtime
  lanes + the language-split posture + control-bus principle. (Models section: ignore.)
- [REBUILD-v0-draft.md](REBUILD-v0-draft.md) — the model-free spine + settled/open decisions.
- [CRAWLER-spec.md](CRAWLER-spec.md) — crawler feature matrix + bypass analysis + hashing decision.
- [BUILDLOG-model-stack.md](BUILDLOG-model-stack.md) — prior model-stack work (now superseded scope; models OUT).

## Suggested next step

Resolve open decision #3 with the Director, then either: build the bypass stack
(start with `RenderProvider` — decide chromiumoxide vs reuse Python playwright over
IPC) OR wire `search` + wget-mirror. Keep each addition tested-green before claiming it.
Do NOT start the daemon spine until decision #1 (language) is settled.
