# SPEC — lgwks: an AI-native compute engine (v0)

Status: SPEC for review (not built). Worktree `…- jarvis`, branch `claude/jarvis-frontier`.
Next reader is an AI; §0 is the exception — written for the human to understand a thing shaped
unlike normal software. Design owner: Logical Claude (rebuilding compute the way an AI wants it).

---

## §0 — Read this first (ground-up; why it's different)

Normal software was built around what a *human* finds scarce and natural: files, windows, prose,
re-reading everything each time. lgwks is built around what an *AI* finds scarce and natural. Four
primitives — each is a deliberate inversion of a habit you'd expect:

1. **The scarce resource is tokens, not CPU.** Every time an AI reads or writes, it spends tokens —
   its attention budget. So the whole I/O is designed to spend the *fewest* tokens that carry the
   most signal. (A human optimizes clicks; an AI optimizes tokens.)
2. **Memory is artifacts addressed by hash, not files by name.** Nothing is re-sent. You point at a
   thing by its content-hash (`art_7f3…`) and the other side already has it. (A human re-reads the
   doc; an AI references it.)
3. **The mind reasons in a sealed room; only proof leaves.** The generative AI thinks freely inside a
   *membrane* — wild, curious, heretical — but only an output that survives a deterministic gate
   crosses out. Free thought, gated action. (This is how a truth-cutting, dangerous-by-design AI
   stays safe without being neutered.)
4. **The surface is small and fixed; the power behind it grows.** You learn ~10 verbs once
   (`solve`, `ground`, `verify`, `review`…) like you learned `git`/`ls`/`cat`. New capability plugs
   in *behind* a verb as an **engine**, never as a new command to memorize.

That's the whole shift: **tokens as currency, artifacts as memory, a membrane for safety, a fixed
head over swappable engines.** Everything below is those four made concrete.

---

## §1 — The organizing law
`token = scarce · artifact = memory · membrane = safety · math does the work the LLM shouldn't.`
Maximize the deterministic perimeter; shrink the paid/generative step to a typed judgment kernel.

## §2 — The engine model (every engine is the SAME shape)
An **engine** is a capability behind a typed port. Swapping a provider never changes a verb.

```
Engine := {
  port:            verb it serves                      // stable surface
  input_schema:    typed slots (NOT free prose)        // token-frugal in
  output_schema:   typed result (NOT page dumps)       // token-frugal out
  providers:       [impl…]  (declared in a manifest)   // dynamic, forkable
  trust_class:     read_only | write_quarantine | effect
  cost_estimator:  (input) -> {tokens, time, $}        // gate before spend
  token_posture:   frugal | exempt(crawler/embedder)   // §6
}
```
Discovery is dynamic (manifest registry); the surface is static; the contract is typed. Stable AND
dynamic = porcelain over drivers. *Helps you code better:* one grammar to learn; capability grows
without re-learning.

## §3 — The engines

| # | Engine | Port (verb) | In → Out | Providers | Token | Trust |
|---|---|---|---|---|---|---|
| 1 | **Acquisition** (crawler) | `scrape`/`map`/`acquire` | url/target → raw artifacts | crwl · firecrawl · GH-Archive · Stack-v2 | **exempt** | read_only |
| 2 | **Grounding/Evidence** | `ground`/`docs` | claim → cited evidence + has_evidence | ctx7 · web · local-corpus | frugal | read_only |
| 3 | **Tongue** (Tier G, generative) | `reason`/`verify`/`solve` | typed intent + evidence refs → schema result | **FREE** OpenRouter-chain · Ollama | frugal | write_quarantine |
| 4 | **Eye** (embedder) | `embed`/`novelty` | artifact → vector; dedup/EIG | free local (Matryoshka int8) | exempt | read_only |
| 5 | **Evaluator** (Tier E) | `review`/`score` | candidate + criteria → calibrated score + attribution | PyTorch+MPS→safetensors→CoreML/ANE | frugal | write_quarantine |
| 6 | **Adversary** (Tier A) | `attack` (scoped) | scope+target → findings \| escape_violation | sandboxed (CyberStrikeAI plumbing, rebuilt safety) | n/a | effect (gated) |
| 7 | **Context packer** | `pack`/`ctx` | run+budget → LOD pack / delta packet | — | the frugality engine | read_only |
| 8 | **Substrate** (fact-log) | `show`/`log` | — | content-addressed hash-chained store | — | the memory |

Each engine's standalone `--json` + exit codes (0 ran / 2 policy-deny / 3 fail / 5 budget) make it
AI-scriptable; plain consequence-first text makes it human-usable (§7).

## §4 — The substrate (shared memory · moat · snapshot ledger)
One content-addressed, hash-chained store (ADR-068 State Fabric). Everything writes here: acquired
artifacts, grounded evidence, verdicts, **Tier-E weight snapshots (safetensors, SHA-256 = checkpoint
id)**, reasoning traces. It is simultaneously: the token-saver (reference don't resend), the
compounding data moat (every run adds objective-labeled examples), and the **turn-back ledger** (a
"defined turn-back date" = a pinned parent hash). *Helps you code better:* nothing you grounded once
is ever re-paid for; the tool gets sharper per repo.

## §5 — The membrane (the safety primitive shared by Tiers G/E/A)
`reason free INSIDE · act gated OUTSIDE.` One mechanism, three walls:
- **Tier G** thinks unbounded; only output surviving the objective hook (cited / non-obvious) leaves.
- **Tier E** evolves unbounded; calibration + Captum attribution are the wall — drift → freeze.
- **Tier A** explores unbounded *within a user-defined scope*; any out-of-scope contact → freeze.
Violation (blackbox line OR scope escape) → **snapshot-freeze**: revert to last-good hash, keep the
runaway frozen for study. The danger is preserved (it's the source of value); the action is contained.

## §6 — Token economy (both sides; crawler-exempt)
- **AI → lgwks** (input): typed intent + `##sigils##` + artifact-refs + delta-patches. Never re-state
  prose; never resend what has a hash.
- **lgwks → AI** (output): verdicts + cited evidence + LOD context packs. Never a page dump. Tier G
  obeys **insight-or-silence** — emits only what's non-obvious, or says it has nothing.
- **Exempt:** Acquisition (1) and Eye (4) deal in raw bytes/vectors, not reasoning tokens — gather
  freely; the Eye then *compresses* raw → vectors so the Tongue never reads raw pages.
- **Rule:** every capability that can be made deterministic moves OUT of the Tongue → cheaper, replayable.

## §7 — Human surface (ease for everyone)
Fixed, learnable verbs (no free-typing into a void; tab-completable). `lgwks solve git` → plain-language
"here is what happened and your safe next step." One recommended action, not a wall of options.
Effect-card output for humans (`what changes / what doesn't / rollback`), `--json` for AI. Same kernel
underneath both. *Helps you code better:* the painful, opaque tasks (git reflog forensics, "why did
CI break") become one verb + a legible answer.

## §8 — lgwks AS an engine (the plug-in future)
The whole system is itself an engine that plugs into a coding AI: **MCP** (expose verbs as tools),
**hook** (UserPromptSubmit repair + PreToolUse admission), or **wrapper** (`lgwks talk claude/codex`).
Enforcement lives in the lgwks-owned wrapper/hook, never in "the model will remember." So lgwks is
both a standalone instrument and a grounding co-processor dropped behind Claude Code / Codex.

## §9 — Build sequence (each node gated: *make sense? help me code better?*)
- **N0 · `lgwks solve git`** — engines 3+7+8 only, no heavy ML. *Sense:* yes — self-contained
  forensics. *Code better:* solves a universal real pain; proves the membrane (free reasoning → gated
  legible answer) end-to-end on a free model.
- **N1 · the harness** — verb→engine routing, the membrane, context-packer, `--json`/exit-codes.
  *Code better:* the spine every later verb reuses; where Tier G's character is built.
- **N2 · corpus v0** — engine 1+4+8: Stack-v2-dedup + GH-Archive signals → quality-vector JSON
  (the signals ARE the labels). *Code better:* the training set + a searchable "good code" memory.
- **N3 · Evaluator v0** — engine 5: PyTorch+MPS scorer on N2 labels; Captum + calibration; CoreML/ANE
  deploy. *Code better:* `lgwks review` runs a deep simulation, AI synthesizes it to docs.
- **N4 · Adversary sandbox** — engine 6: safety contract FIRST, then driver. *Code better:* finds the
  breakage a review misses, inside a wall.
N0+N2 independent (parallel). N3 needs N2. N4 needs N3's governance.

## §10 — Acceptance invariants (a node isn't done until)
1. The verb runs with `--json` and honest exit codes; no prose-as-proof.
2. No token re-spend: prior artifacts referenced by hash, not resent.
3. Tier G output is cited or silent — never confidently obvious.
4. Any effect crosses the membrane through a deterministic gate, never on model say-so.
5. Every run appends an auditable trace to the substrate; weight changes are hash-pinned + revertible.
6. It passes the human test (one legible answer + safe next step) AND the AI test (typed, frugal).
```
The one-liner: lgwks is compute re-cut around the AI's real scarcity — tokens and trust — with a
fixed human-simple head, swappable engines behind it, a membrane that lets a curious truth-seeking
model be dangerous safely, and a fact-log that makes it cheaper and sharper every run.
```
