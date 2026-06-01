# PROPOSAL — CLI grammar (stable + dynamic), native grounding commands, growth & moats

Next reader is an AI. Dense by design. Status: PROPOSAL (not yet built). Worktree `…- jarvis`,
branch `claude/jarvis-frontier`. Written after two hardening commits (`2047e52` injection,
`df9d5d6` deep-grounding + guide verdict) proved the co-processor refutes a bad plan with cited
evidence and refuses to fabricate a verdict without it.

---

## 0. The question this answers
The Director's ask: *"How do we have a stable claude-code-like AND dynamic skillfish-type dynamic at
the same time? Make the CLI head bounded (user can't free-type, fixed length), like our OS. Wire
ctx7/firecrawl natively as quick commands. How much heavy-lifting can math do, so you get a chain of
real research and output instead of ramblings? Improve the name."*

The unifying answer is one idea borrowed from operating systems: **a fixed syscall ABI with
dynamically-loaded drivers behind it.** The command *surface* is small, fixed, and learnable; the
*capabilities* behind each verb grow dynamically through a manifest registry. Stable AND dynamic is
not a tension — it's the porcelain/plumbing split plus a driver model.

---

## 1. Stable + dynamic: the two-tier resolution

```
            HUMAN / CODING-AI
                  │  prose with ##anchors##  (bounded input, §3)
                  ▼
   ┌─────────────────────────────────────────────┐
   │  PORCELAIN  (stable, fixed verb set — the "head")          ← claude-code-like
   │  lgwks ground · docs · search · scrape · map · research    │
   │        · verify · cite · show · ctx                         │
   │  • verb-noun grammar, ONE order, never deviates             │
   │  • every verb has --json (machine) + --quiet + exit codes   │
   │  • no forced interactivity; fully scriptable; dry-run/cost  │
   └─────────────────────────────────────────────┘
                  │  dispatches to typed providers (by manifest)
                  ▼
   ┌─────────────────────────────────────────────┐
   │  PLUMBING  (dynamic, skillfish-style provider registry)     ← extensible
   │  grounding-providers: ctx7 · firecrawl · crwl · local-corpus│
   │  tongue-providers:    openrouter(free-chain) · ollama       │
   │  skills:              register a capability descriptor       │
   │  • a new provider does NOT add a new verb — it plugs in      │
   │    BEHIND an existing verb as a typed, trust-classed driver  │
   └─────────────────────────────────────────────┘
```

**Why this gives both at once.** The kernel ABI (`read/write/open`) doesn't grow when you plug in a
USB device — a driver registers. Likewise `lgwks ground <q>` is a fixed verb; adding firecrawl
doesn't change its grammar, it registers a grounding provider. The human learns ~9 verbs once
(fixed length, no free-typing into a void — tab-completable, discoverable); the capability set
behind them expands forever. **Surface bounded, power unbounded.**

**Manifest = the skillfish-dynamic part.** Each provider ships a descriptor:
`{name, verb_it_serves, input_schema, trust_class (read_only|write_quarantine), cost_estimator}`.
The CLI discovers providers at launch (same pattern as Claude-Code skills / this session's
deferred-tool registry), validates the schema, and gates by trust class + cost BEFORE dispatch
(the existing schema→capability→cost stack, T0). Dynamic discovery, static surface, typed contract.

---

## 2. Native quick commands (wire ctx7 + firecrawl as first-class)

Today grounding is buried inside the `--auto` loop. Expose the base capabilities as standalone verbs
so they're usable as quick tools AND composable in pipes (the #1 thing people love about CLIs):

| verb | does | provider(s) | notes |
|---|---|---|---|
| `lgwks docs <lib> "<q>"` | two-step ctx7 resolve→docs, prints docs + Source: URLs | ctx7 | already built in `lgwks_ground`; just surface it |
| `lgwks ground "<claim>"` | fused evidence for a claim (docs+web), prints `has_evidence` + sources | ctx7 (+web) | the EVIDENCE primitive |
| `lgwks search "<q>"` | web search → ranked results + URLs | firecrawl / crwl | honest-degraded when 402/blocked |
| `lgwks scrape <url>` | page → markdown | crwl / firecrawl | URL-in (crwl is a crawler, not search) |
| `lgwks verify "<claim>"` | ground + a single contradicted/supported/unverified verdict | ctx7 + tongue | the co-processor in one shot, no loop |
| `lgwks research --guide f` | the full autonomous agenda loop (today's `--auto`) | all | the deep mode |
| `lgwks show <run>` | print a run's CONTEXT.md / result.json | — | the poll surface |

All emit `--json`. `verify` is the killer quick-command: *"is this one assumption true?"* → a cited
verdict in one call, no full run. Composable: `cat plan.md | lgwks research --stdin --json | jq …`.

**Safety defaults (from the CLI research — what people hate):** destructive/expensive verbs print a
**token-cost estimate** and require `--yes` or default to `--dry-run`; nothing forces a TUI; every
verb scripts cleanly. This directly answers the top AI-tool complaints (silent over-spend, doing too
much unasked).

---

## 3. `##sigil##` — the machine-first input notation (the `##like##` idea)

The bounded-input answer to "user can't free-type." Humans/coding-AIs write natural prose; a
**deterministic parser (regex/grammar, ZERO LLM)** lifts typed inline anchors out and routes them:

```
##ground:requests.get is async##     → an agenda question (a claim to falsify)
##ctx7:fastapi##                     → a grounding target (resolve+docs)
##cite:10.1145/3290605##             → a citation to resolve+verify
##entity:Stripe##                    → a node in the fact-graph
##!assume:Session is thread-safe##   → a LOAD-BEARING assumption (high-priority falsify)
```

The parser emits a STRUCTURED intent object (the agenda seed) straight from prose — **math does the
lifting; the LLM never sees raw rambling, only typed slots + grounded findings.** This is the
`machine-first-language` thesis made concrete, and it doubles as a trust boundary: anchors are typed,
length-bounded, and injection-validated (extends `_agenda_node`/`_safe_node`). It's also how a coding
AI cheaply hands work over mid-stream: it drops `##ground:…##` markers in its plan and we lift them.

---

## 4. How much heavy-lifting math can do (chain, not ramble)

North star: **maximize the deterministic perimeter, shrink the LLM to a typed judgment kernel.**

```
DETERMINISTIC (math — cheap, reproducible, auditable)        LLM (constrained oracle — schema-gated)
  sigil parse → agenda construction                            hypothesis generation (H0..Hn)
  frontier scheduling (EIG ordering)                           evidence → guide_verdict judgment
  grounding I/O (ctx7/web subprocess) + citation extraction    contrarian (bias-strip)
  confidence formula  C = Tier_cap ⊗ σ(λW+(1-λ)B)              ─────────────────────────────────
  verdict aggregation · dedup · novelty (embeddings/Eye)       forced JSON + strict schema = fills
  hash-chained ledger · LOD context pack                       slots, does NOT free-generate prose
```

Every new deterministic capability moves work OUT of the LLM → lower cost, more reproducibility.
The OUTPUT is the **ledger**: a chain of `(question → grounded evidence → cited verdict)` — not a
chat reply. "Instead of ramblings" is an architectural property, not a prompt instruction. Concrete
next math-moves: (a) citation resolver (CrossRef/Semantic Scholar) to turn `doc_sources` URLs into
verified cites; (b) embedding-novelty (the local Eye) to schedule the frontier by real information
gain instead of model-estimated EIG; (c) deterministic verdict aggregation across rounds.

---

## 5. Rename (kill "akinator")

`lgwks-akinator` misfires: "akinator" = a guessing-game (implies vibes/entertainment, the opposite of
our truth-mandate); `lgwks` is unpronounceable. Keep **`lgwks` as the OS-like head/namespace** (the
fleet's tool), rename the *instrument* and drop "akinator". The thing tests a plan's claims against
evidence — so the name should evoke assaying/grounding/anti-drift:

- **`assay`** — to assay = metallurgically test purity/content. "lgwks assay <guide>". Precise: it
  assays claims. (recommend)
- **`plumb`** — depth + the plumbing tier pun + "plumb the docs". "lgwks plumb".
- **`ballast`** — keeps the coding AI from drifting into hallucination; anti-drift weight.
- **`litmus`** — a litmus test for plan assumptions.

Recommend `assay` (verb-shaped, unique, on-thesis). Decision is the Director's — see the question.

---

## 6. Comprehensive hardening plan (open items, ranked)

**P0 — correctness / trust (do next)**
1. **Citation resolver** — `doc_sources` URLs are captured but `citations_verified:false` everywhere
   (the standing SLOP RISK). Resolve `builds_on` + doc URLs against CrossRef/Semantic Scholar; only
   then may a verdict claim a verified citation. *Invariant: no "verified" without a resolved cite.*
2. **Web grounding seam** — Q2/Q3 went `unverified` because ctx7 docs lack the deciding fact; a real
   web provider (firecrawl when funded / crwl) behind `ground` closes the gap. Honest-degraded today.
3. **Verdict ⊕ falsifier reconciliation** — `falsifiers_hit` is now redundant/confusing in guide mode
   (`hit=—` while `GUIDE: CONTRADICTED`). Either drive falsifiers_hit FROM the verdict or retire it
   for guide runs; one signal, not two.

**P1 — adversarial / boundary**
4. Live-mode injection hardening + DNS-rebind window (handoff F5) before `live` crawl is provisioned.
5. Provision `lgwks:signing-key` in Keychain → ledgers become tamper-EVIDENT, not corruption-only.
6. Sigil-parser fuzzing once §3 lands (typed anchors are a new untrusted surface).

**P2 — robustness / ergonomics**
7. Stable run-id / `runs/latest` symlink so a background poller needn't guess `<id>`.
8. ctx7 docs caching (avoid re-fetching the same lib across rounds — cost + speed).
9. `--json` everywhere + non-zero exit on `contradicted` (so CI/agents can gate on it).

## 7. Growth plan (sequence)
- **Phase A (now→):** porcelain verbs (§2) + sigil parser (§3) + citation resolver (P0-1). Ship the
  quick commands; make `verify` the on-ramp.
- **Phase B:** provider manifest/registry (§1 plumbing) + web provider. Vendor-agnostic, forkable.
- **Phase C:** the compounding fact-log — every grounded run writes to a content-addressed, hash-
  chained store (the State Fabric); the citation graph + verdict history accrue. Background-while-
  coding becomes a standing daemon a coding AI subscribes to.
- **Phase D:** machine-first protocol — `##sigils##` + LOD context packs become the documented way
  any coding AI requests grounding. "A plugin to the internet" / OS grounding layer.

## 8. Moats (honest: current vs growth-bet)

**Real today**
- **Anti-hallucination BY CONSTRUCTION.** A verdict cannot exist without grounded evidence (the
  has_evidence gate forces `unverified`; proven live this session). Competitors bolt "please cite"
  onto a chat model; we make fabrication structurally unrepresentable. This is the #1 driver of AI
  abandonment (hallucination) — turned into our spine. Hard to copy without surrendering the chatty
  default.
- **Low-cost deterministic loop.** 3 grounded rounds ≈ 17k tokens; the LLM is a small typed kernel,
  not the engine. Answers the "21k tokens for a typo" complaint with a structurally cheaper design.
- **Auditability.** Hash-chained ledger, scope-frozen crawl, injection-hardened, SOC2-shaped audit
  trail — a skeptic-convincing bar most AI tools never clear.
- **Vendor-agnostic.** OpenRouter free-chain + provider seams; no lock-in; forkable OSS.

**Growth-bet (not yet real — label honestly)**
- **Compounding fact-log** (Phase C) — a content-addressed causal store that gets more valuable each
  run; the data moat. Aspirational until built.
- **Machine-first protocol** (Phase D) — if `##sigils##`/LOD packs become how AIs request grounding,
  it's a protocol/distribution moat.
- **Co-processor positioning** — complement (not competitor) to Cursor/Claude Code → distribution by
  integration. Concept real, distribution unproven.

**The one-liner:** *we own the grounding/trust layer beneath the coding AIs — the thing that makes
their output safe — and we make hallucinated confidence structurally impossible.*
