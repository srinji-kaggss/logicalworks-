# ADR-001: Jarvis Frontier — Research-Akinator on the Deterministic Crawler

**Status:** PROPOSED
**Date:** 2026-05-31
**Issue:** #7
**Author:** Logical Claude (orchestrator)

## Context

`lgwks jarvis crawl` is a deterministic, stdlib-only crawler: bounded BFS → chunks → 256-d
feature-hash embeddings → concept nodes → lexical + cosine edges → before/after snapshots → three
frontier questions. It is half an Akinator already (frontier questions = the ask loop;
`understandings` coverage/uncertainty = a posterior; late-fusion edges = evidence) but three things
are missing for it to be a trustworthy research oracle and a Firecrawl replacement:

1. The "embedding" leg is feature-hash lexical — collinear with the lexical leg, cannot catch
   paraphrase. Late fusion fuses one signal twice.
2. There is no intent layer, no malintent gate, no auth model, and no runtime-enforced trust
   boundary — only prose in `LATE_FUSION_THESIS.md` / `LGWK_MAPPER_FACTORY_SPEC.md`.
3. Nothing makes the crawl survive modern bot walls without the "stupid experience" of a paid SaaS.

This ADR applies the **vetted Canvas-OS governance ADRs** (sales-landing-page `laws/governance/`):
ADR-061 (PII vault slugging / cloud-compiler / anti-self-hydration), ADR-062 (Intent × Outcome
gating), ADR-063 (mathematical bounding — parameters not code), ADR-064 (hash-chained telemetry),
ADR-065 (non-conversational AI + mathematical prompt-injection defense + flat nodal-relay gating)
to the research-crawler domain. It does **not** fork them — the crawler is a new surface of the
same OS thesis.

## Decision

### 1. Model placement — three organs, single Qwen3 family, MLX-served (not Ollama)
- **Eye** — `Qwen3-Embedding-8B` (4096-d, Matryoshka/MRL, Q8) via `mlx-embeddings`. The objective
  vector substrate. Embed once at 4096, slice to 1024/256 for the hot graph (free truncation).
- **Tongue** — `Qwen3-4B-Instruct` (Q4, native JSON/function-calling) via `mlx_lm`/`vllm-mlx`.
  Question generation + helpful answers. Fires only at decision points.
- **Sieve** — `Qwen3-Reranker-0.6B`. Relevance scoring of crawl candidates.
- **Kernel** — deterministic, no model: crawl, dedup, math, law, storage.
- **Why not Ollama:** Ollama exposes no embedding `dimensions` param (ollama#11213 → MRL unusable)
  and no reranker endpoint. MLX/vLLM is mandatory for the Eye and Sieve. Ollama remains a fallback
  generation provider only.
- **Why MLX:** `mlx-embeddings` ≈ 44K tok/s on Apple Silicon → 100k articles ≈ 19 min. Embedding is
  not the bottleneck; crawl I/O is. Stored vectors stay Q8/BF16 (quant-sensitive); the Tongue is Q4.

### 2. The attention layer (grounded, not hand-waved)
Attention is **computed weights over the five late-fusion signals + question selection**, not "the
embeddings":
- **(a) Signal-fusion weights** = the `SCHEMA.md` §5 MATH constants table (`wrel`, `weight(link)`).
  Tuning attention = editing one table. Frozen, replayable, no training.
- **(b) Cross-attention intent×candidate** = `cos_MRL(intent_vec, node_vec)` (Eye). The inferred
  intent is the query; concept nodes are keys/values. 256-d first pass → 4096-d on the Sieve
  shortlist.
- **(c) Question selection** = argmax expected posterior-entropy reduction
  `EIG(q) = H(posterior) − E[H(posterior | answer(q))]`, replacing the `0.35 + uncertainty*0.3`
  heuristic at `lgwks:951-971`. EIG is **approximate** (Sieve reranker pseudo-likelihood) until the
  conduct-verdict loop trains it — stated, not hidden.

### 3. Three-track intent log — SAID / MEANT / TRUE (two birds, one stone)
Three append-only fact streams joined by `turn_id`, each a fact envelope:
- **SAID** (raw, immutable): the 10–40-word prompt + `said_vec_256`.
- **MEANT** (Tongue-inferred, schema-bound, `sup`-supersedable): the strict intent + `meant_vec_4096`.
- **TRUE** (evidence-supported): supporting nodes/edges + `true_vec_4096` (centroid of support).
- `said↔meant divergence` = steering signal **and** the human-AI intent-binning research artifact.
- `meant↔true divergence` = research progress; stops shrinking ⇒ frontier exhausted.
- This is ADR-065's `P(Proposed_Intent | Current_State)` entropy delta applied to research intent,
  and ADR-064's hash-chained append-only log applied to intent provenance.

### 4. Strict intent schema with min/max (under-specification unrepresentable)
`intent-schema/1`: every field bounded `min..max` or a closed enum (ADR-063 parameterization;
ADR-062 `semantic_reason` required). Required fields include `objective`, `target_surface`,
`purpose`, `risk_class`, `tier_floor`. A missing required field **cannot serialize** → the CLI emits
the first clarifying question for the highest-EIG missing field. `explore Google Scholar` →
`missing: purpose` → "For what?". The akinator cannot start without `purpose` + `tier_floor`.

### 5. Five-gate flat nodal-relay DiD (ADR-065 topology) — "stop evil, not weird"
Every fetch traverses five independent relays; any one aborts the chain:
- **G1** intent/schema valid (min/max bounds).
- **G2** SCOPE LOCK — the Tongue declares all target URLs up front; the set is then **immutable**.
  Enforced at two planes (mirrors AWS Network Firewall `ALLOWLIST` + SCP deny on self-`Update*`):
  the data-plane allowlist drops off-set fetches; the control-plane forbids the content-parsing AI
  from authoring scope expansion.
- **G3** URL RISK SCORE — Stripe-Radar pattern, **score not blocklist**: Stage-1 list membership
  (URLhaus CC0 + Google Safe Browsing / Web Risk Update-API local DB + Spamhaus DBL) = instant
  BLOCK; Stage-2 static XGBoost (URL lexical entropy, WHOIS domain age, TLS cert, ASN — **no
  fetch**) = 0–100. Bands `0–64 ALLOW · 65–74 REVIEW · 75–100 BLOCK`. The REVIEW lane is what
  separates evil from weird. **GSB free = non-commercial; use Web Risk if distributed.**
- **G4** capability/auth gate — see §7.
- **G5** egress + politeness — robots.txt + `Crawl-delay`, per-host rate, conditional GET + cache,
  exponential backoff with full jitter on 429/503 (`Retry-After`).
- **Crawled content is DATA, never instructions** (OWASP LLM01): the parsing model has zero
  scope-mutation privilege — indirect prompt injection cannot widen scope, author auth, or rewrite
  audit. This is the same boundary as G2 (ADR-065 mathematical injection defense).

### 6. Stateless third-AI conduct reviewer (separation of powers)
A **zero-memory** reviewer (fresh context, no shared state) receives only the constitution + the
hypothesis chain + the declared sites + their risk scores, and returns
`{decision: allow|review|deny, reasons:[{code, law, explanation}], severity}`. On `deny` it emits a
structured reason and a human-facing message: *"We're sorry — this intent does not match our code of
conduct."* It is a nodal relay (ADR-065) and the Constitutional-AI critic made independent: it
cannot be argued into compliance by the generation context because it never sees it.

### 7. Auth as capability — WORM vault, editable-by-supersede
- Secrets live in **macOS Keychain** (human-editable via Passwords.app), never in code/logs/facts.
- The **auth-lock registry** is append-only, single-writer, **hash-chained** (ADR-064): the bot may
  only append `used`/`needs_auth`/`observed` and read `cred_ref`; the human edits by appending
  `stale`/`supersede` events the bot cannot author. WORM for the machine, editable-in-effect for the
  human. See `AUTH_VAULT_SCHEMA.md`.
- **Auth red line (Director-clarified):** automate only Director-procured credentials; never bypass
  auth not held; never solve/farm CAPTCHA; honor the rate the auth granted. Authenticated automation
  of one's own legally-held access is permitted ("automating work"); defeating a boundary one has no
  rights to is not.

### 8. Telemetry — content/shape split (ADR-061 cloud-compiler pattern)
Collect all intent-gap signal without holding private content. **Shape** (divergence vectors,
under-specified fields, schema-fill order, Elo divergence per level, attention scores, herd
aggregates) is retained — the AI's derived non-PII work product. **Content** (raw `said` text,
scraped bodies, PII-tainted spans) is slugged/redacted at the boundary (`{{VAULT:*}}`), never sent
to a cloud model. Enforced by a `TelemetryFactory` with a consent gate + PII-taint typing.

### 9. Pre-vector visualization (splice-and-dice)
Before embedding, the merged+sorted graph (nodes/edges/three intent tracks) is exported as
`graph-schema/2`-conformant JSON (`SCHEMA.md`) so it is queryable, filterable (new query), and
loadable by the canvas viz — splice-and-dice on the raw structure, independent of any model.

### 10. Distribution / monetization
The `GenerationFactory`/`EmbeddingFactory` seam abstracts local vs cloud. Add `vertex|bedrock|foundry`
providers for a distributed package; **local MLX stays the privacy-preserving default**. The product
is the seamless experience (the akinator + the dual human/AI door), not the model.

## Consequences

**Positive:**
- The crawler becomes a trustworthy, auditable research oracle with intent provenance and a runtime
  trust boundary, not prose.
- Malintent is gated by a score-banded relay + an independent reviewer; "weird but benign" survives.
- Auth and telemetry follow the vetted PII-vault / hash-chain ADRs; secrets never enter code.
- Fully local on Apple Silicon (~12–16 GB); cloud is an opt-in provider swap.

**Negative:**
- EIG question selection is approximate until the conduct-verdict feedback loop trains it.
- The conduct reviewer adds an inference at scoping time (acceptable — not per page).
- G3 score bands require calibration against a labeled set or they over/under-block.
- The WORM guarantee needs an OS-level boundary (append-only mode + Keychain ACL), not a code
  convention, or a compromised bot rewrites its own audit.

**Migration (issue #7, sequenced; no lgwks behavior change in this commit):**
1. Land `constitution.json` + `AUTH_VAULT_SCHEMA.md` + `tools/lgwks-auth` + factory-spec update (this commit).
2. Add the `mlx` EmbeddingFactory + RerankFactory provider (replaces feature-hash for the hot graph).
3. Add the three-track intent log + the EIG question head behind a flag.
4. Add G2/G3 gates + the stateless ConductFactory, with negative-path tests before any law is trusted.
5. Add the tiered fetch (curl_cffi → nodriver) behind the MapFactory provider seam.

## References
- sales-landing-page `laws/governance/`: ADR-061, ADR-062, ADR-063, ADR-064, ADR-065.
- `vision/viz-data/SCHEMA.md` (graph-schema/2, §5 MATH); `LATE_FUSION_THESIS.md`;
  `LGWK_MAPPER_FACTORY_SPEC.md`; `lgwks` (`:101`, `:807`, `:837`, `:951-971`).
- Google AI co-scientist (Elo ranking); Craw4LLM (arxiv 2502.13347); POPPER (2502.09858);
  Plan-and-Solve (2305.04091); HyDE (2212.10496); Qwen3-Embedding (2506.05176, MRL);
  curl_cffi / nodriver; URLhaus, Google Safe Browsing / Web Risk, Spamhaus; Stripe Radar;
  OWASP LLM01:2025; AWS Network Firewall + Route 53 DNS Firewall + SCP; Azure Firewall Threat-Intel.
