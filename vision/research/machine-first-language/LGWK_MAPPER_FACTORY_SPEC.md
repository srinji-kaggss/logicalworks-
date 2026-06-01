# LGWK Mapper Factory Spec

Version: `lgwk-mapper-factory/0.1`

This spec keeps the mapper model-agnostic. The deterministic crawl/map kernel is the product boundary; models are replaceable factories.

## Factory Interfaces

### CrawlFactory

Input:

```json
{"source":"file|folder|url","limits":{"max_files":160,"max_pages":40,"max_bytes":250000}}
```

Output:

```json
{"documents":[{"uid":"sha256","title":"","source":"","kind":"","text":"","tokens":[],"meta":{}}]}
```

Required behavior:

- Must terminate under configured limits.
- Must produce stable document IDs for unchanged inputs.
- Must not require network services for local file/folder sources.
- URL crawling is allowed, but must use local code and bounded traversal.

### MapFactory

Input: documents plus run prompt.

Output: `jarvis-schema.json` with:

- `system_manifest`
- `mathematical_coordinate_space`
- `network_topology_graph.nodes`
- `network_topology_graph.edges`

Required behavior:

- Node identity is SHA-256 over structural pattern.
- Ambiguous nodes are sandboxed.
- Relationships are typed before visual rendering.
- The schema remains valid without model output.

### GenerationFactory

Input: prompt plus compact schema summary.

Output:

```json
{"text":"one question or final synthesis"}
```

Provider names:

- `deterministic`
- `ollama`
- future: `apple-foundation-models`
- future: `coreml`
- future: `mlx`

Required behavior:

- Missing provider must fall back to deterministic behavior.
- Question generation returns exactly one deeper production/blindspot question.
- Final synthesis cannot directly promote sandboxed nodes.

### EmbeddingFactory

Input:

```json
{"text":"","dims":256}
```

Output:

```json
{"embedding":[],"provider":"","model":"","dimensions":0}
```

Provider names:

- `deterministic`: feature-hash vector, always available.
- `ollama`: local model endpoint, default `qwen3-embedding:8b`.
- future: `apple-foundation-models`
- future: `coreml`
- future: `mlx`

Required behavior:

- Embeddings are local.
- Failed neural embedding falls back to deterministic embedding.
- Embeddings are stored per document in `embeddings.jsonl`.

### PromotionFactory

Input: schema, final guide, triage answers.

Output:

- promoted stream rows in `notes/os-intel.jsonl`
- triage rows in `notes/mapper-triage.jsonl`

Required behavior:

- Triage can be speculative.
- OS intel cannot be speculative.
- Sandboxed nodes stay out of the OS stream unless a future verifier promotes them.

## CLI Contract

```bash
./lgwk mapper <source> \
  --prompt "..." \
  --provider deterministic|ollama \
  --model <generation-model> \
  --final-provider deterministic|ollama \
  --final-model <stronger-generation-model> \
  --embed-provider deterministic|ollama \
  --embed-model qwen3-embedding:8b
```

Recommended Qwen setup:

```bash
./lgwk mapper <url> \
  --prompt "Map this website into OS nodes" \
  --provider deterministic \
  --final-provider deterministic \
  --embed-provider ollama \
  --embed-model qwen3-embedding:8b
```

This keeps reasoning deterministic while using Qwen only for local embeddings.

## Controlled Swarm Target

The next factory layer should add `SwarmFactory`:

```json
{
  "workers": 4,
  "max_workers": 10,
  "max_depth": 10,
  "state": "stateless-worker",
  "merge": "deterministic-parent"
}
```

Worker contract:

- Each worker receives one URL node plus depth budget.
- Each worker emits documents and candidate edges only.
- Parent process deduplicates by SHA-256 and applies promotion rules.
- Workers never mutate `notes/os-intel.jsonl` directly.

## Frontier Factories (`lgwk-mapper-factory/0.2` — Issue #7, ADR-001)

These add the research-akinator, the trust boundary, and the Firecrawl replacement. Each is a
replaceable factory; the deterministic kernel + the constitution (`constitution.json`) are law.
Every factory falls back to deterministic behavior when its provider is absent.

### EmbeddingFactory — provider correction
- Add provider **`mlx`** (default model `qwen3-embedding-8b`, 4096-d, MRL). Embed at 4096, slice to
  1024/256 for the hot graph (free truncation). Stored vectors are Q8/BF16 (quant-sensitive).
- **Do NOT use Ollama for embeddings:** it exposes no `dimensions` param (ollama#11213 → MRL
  unusable). `deterministic` (feature-hash) remains the always-available fallback. Every vector is
  stamped `{model, dim, mrl_slice, quant}`; cross-config cosine is refused (objective cache).

### RerankFactory
- Provider `mlx` (default `qwen3-reranker-0.6b`). Scores crawl candidates for relevance; supplies the
  pseudo-likelihood for EIG question selection. Not available via Ollama (no rerank endpoint).

### MapFactory — tiered stealth fetch (Firecrawl replacement)
- Tier 0 robots/cache → Tier 1 **curl_cffi** (real Chrome TLS/JA4 + HTTP2 impersonation; ~most
  public sites, near-zero cost) → Tier 2 **nodriver** headless (JS/challenge) → Tier 3 (optional)
  residential proxy. "Stealth but polite": honor robots + `Crawl-delay`, per-host rate, conditional
  GET, backoff-with-jitter. Escalate only on detected block. Avoid camoufox on arm64 (decode bug).

### VaultFactory  (see `AUTH_VAULT_SCHEMA.md`)
- Resolves a Director-procured `cred_ref` from macOS Keychain at fetch time (token → process only).
- Append-only, single-writer, hash-chained registry (ADR-064). Bot appends `used|needs_auth|observed`;
  human authors `lock|stale|supersede`. Honors `rate_from_auth` as a hard cap (constitution L8).
- Never bypass auth not held, paywalls, or CAPTCHA. CLI: `tools/lgwks-auth`.

### UrlRiskFactory  (G3 — the scope curator; "stop evil, not weird")
Implemented: `lgwks_urlrisk.py` (deterministic core, stdlib, tested). It does NOT just blocklist —
it **cherry-picks / reviews / blocks each declared slug** on two axes, at scope-declaration AND
over time, and it **adapts slug granularity**:
- **axis 1 — malware:** Stage-1 list membership (URLhaus CC0 + GSB/**Web Risk** local DB + Spamhaus
  DBL) = instant BLOCK; Stage-2 static lexical score (host entropy/DGA, IP-literal, punycode,
  suspicious TLD/tokens, userinfo trick, length — **no fetch**) = 0–100.
- **axis 2 — corrupted intent:** `1 − cos(meant_vec, slug_evidence_centroid)`, accumulated (EMA)
  over runs. A slug that began on-purpose but drifts — or was smuggled — is blocked even if clean.
  This is the three-track meant↔true divergence applied to one scope item.
- **bands:** `0–64 ALLOW · 65–74 REVIEW · 75–100 BLOCK`; worst axis governs (DiD). **GSB free =
  non-commercial; use Web Risk if distributed.**
- **granularity adaptation (`adapt_granularity`):** over time the layer REDUCES or INCREASES slugs
  from the ML chains — N sibling subdomains with low, agreeing drift collapse to `*.domain`
  (e.g. `docs/mail/drive.google.com → *.google.com`); a wildcard whose children disagree expands
  back to the specific members. Emitted as **proposals** (critic/human-gated; never silently
  rewrites the frozen scope — feeds the next declaration round).

**Provider seam + the learning architecture (the Director's "transformer + DeepMind GNN that grows"):**
- `provider="deterministic"` (today) → `"transformer"` → `"gnn"`. Absent/unwired providers fall back
  to deterministic; **a model can never ALLOW what a feed-hit BLOCKs** (law gates imagination).
- **transformer:** a small open-weights URL classifier (world-class framework + weights, not slop) —
  replaces the lexical Stage-2 score with a learned one. Frozen reference checkpoint = the "teacher".
- **GNN (grows on the graph):** a graph net over the domain/ASN/co-host/registrar graph the crawl
  builds (DeepMind-style message passing) — it learns malicious-neighbourhood structure and gets
  better as the graph grows. This is what makes granularity adaptation principled (siblings that
  message-pass to the same embedding collapse).
- **divergence monitor (corrected):** the Director's "track our changing weights vs real weights" is
  sound in intent but must compare in **function/representation space, not raw weight space** —
  raw-weight comparison across nets is meaningless (permutation symmetry, different init). Concretely:
  hold the pretrained model frozen as the **reference (teacher)**; our model is the **student** that
  continually learns on the crawl. Track `divergence = D(student_outputs, teacher_outputs)` on a
  shared probe set (KL / cosine of logits/embeddings) + drift of the student vs its OWN earlier
  checkpoint. Where they differ is a signal: drift-toward-our-slice (overfit, flag) vs genuine new
  structure the teacher lacks (novel, candidate-promote). Same said/meant/true divergence pattern,
  applied to the model. Distillation keeps the student grounded in the teacher's framework, not slop.

### Port path (local → portable)
- **Today:** all stdlib + local; deterministic providers; runs on the 24 GB Mac, no models required.
- **Port:** each factory is a provider behind a stable interface; porting = adding a provider, never
  rewriting the kernel. EmbeddingFactory/RerankFactory → MLX (Qwen3) locally or a spot-GPU/Bedrock
  Titan provider in cloud; UrlRiskFactory transformer/gnn → local MLX or a served checkpoint;
  MapFactory crawl workers → AWS Lambda non-VPC (rotating egress IPs). The constitution + the
  deterministic kernel are invariant across the port; only providers and the signer source change.

### ConductFactory  (the stateless third-AI reviewer, constitution L9)
- A **zero-memory** reviewer (fresh context, no shared state) sees only the constitution + the
  hypothesis chain + declared sites + risk scores. Returns
  `{decision: allow|review|deny, reasons:[{code, law, explanation}], severity}`.
- On `deny`: structured reason + human message *"We're sorry — this intent does not match our code
  of conduct."* It is a nodal relay (ADR-065) and the Constitutional-AI critic made independent — it
  cannot be argued into compliance because it never sees the generation context.
- Required behavior: it can only `deny`/`review`/`allow`; it can never promote, mutate, or widen scope.

### TelemetryFactory  (content/shape split, ADR-061)
- Retains **shape** (said↔meant↔true divergence vectors, under-specified fields, Elo divergence per
  level, attention scores, herd aggregates — the AI's derived non-PII work product).
- Slugs/redacts **content** (raw `said` text, scraped bodies, PII-tainted spans → `{{VAULT:*}}`),
  never sent to a cloud model. Consent gate + PII-taint typing. Cloud models are compilers, not
  plaintext holders.

### PreVectorExportFactory  (splice-and-dice)
- Before embedding, export the merged+sorted graph (nodes/edges/three intent tracks) as
  `graph-schema/2` JSON (`viz-data/SCHEMA.md`) so it is queryable, filterable (new query), and
  loadable by the canvas viz — splice-and-dice on raw structure, independent of any model.

### Scope-immutability (two planes, AWS/Azure pattern)
- Data plane: the declared URL set is an allowlist; off-set fetches drop (AWS Network Firewall
  `ALLOWLIST`; Azure Firewall FQDN rule). Control plane: the content-parsing AI has zero privilege to
  edit the set (AWS SCP deny self-`Update*`; constitution L6/L7). Declare-all-then-immutable.

## OS Rule

Models provide imagination and compression. Factories provide law.

