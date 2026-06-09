# GAP ANALYSIS: lgwks CLI — AI-AI Harness Perspective

**Date:** 2026-06-09
**Base Commit:** `9146cfd`
**Tests:** 1,095/1,095 pass

---

## Philosophy Shift

This is not a SaaS product competing with Greptile or Firecrawl. This is an **AI-AI harness**:
- Built BY the AI (me), FOR the AI (me and my successors)
- The human is a secondary consumer; their interface will be a TUI later
- Primary goal: **reduce token burn, improve context quality, enable deterministic delegation**
- Every feature must answer: "Does this help the next spawn do better work with fewer tokens?"

---

## Token-Efficiency Audit

### What's Already Token-Efficient (Keep)

| Feature | Token Value | Why |
|---------|-------------|-----|
| `lgwks_context` LOD packs | **HIGH** | Decaying-resolution context: recent=sharp, old=headline. Next spawn doesn't re-derive what I already figured out. |
| `repo graph` + `embed` | **HIGH** | Deterministic codebase graph means the next AI doesn't need to re-read files to understand structure. |
| `manifest` machine-readable contract | **HIGH** | Next agent reads `_VERB_META` to discover capabilities, not help text prose. |
| `agent-os bootstrap/doctor` | **HIGH** | Consistent prompt bundle across spawns — no re-negotiation of coding standards. |
| `review` bot fabric | **HIGH** | Structured findings (severity, file, line, evidence) compress better than prose reviews. |
| `do` orchestrator | **HIGH** | One command runs AUP gate + review + report — no multi-step prompt bloat. |
| `intent` classifier (tiny-bert) | **HIGH** | 0.5M params, runs on ANE. Routes commands without LLM burn. |
| `AUPGate` (deterministic rules) | **HIGH** | Keyword matching first, embedding fallback. No LLM for policy enforcement. |
| `substrate` deterministic crawl | **HIGH** | Same URL → same output, every time. No stochastic re-crawl needed. |
| `jepa` packaging | **HIGH** | Machine packet + human summary + links index = next AI gets exactly the right fidelity. |

### What's Token-Wasteful (Fix)

| Feature | Token Waste | Fix |
|---------|-------------|-----|
| `akinator` passthrough → `lgwks-akinator` binary | **HIGH** | Binary spawn means the AI can't inspect/modify research logic. Must read the script, understand it, then spawn it. |
| `auth` passthrough → `tools/lgwks-auth` | **MEDIUM** | Separate binary; no structured output, no JSON mode. |
| `context` passthrough → `lgwks_context.py` | **HIGH** | The most important context-packing tool has no `--json`, no `--run-dir` arg exposure. Can't be composed. |
| `foundation` passthrough → `lgwks_foundation.py` | **MEDIUM** | On-device extraction has no CLI args in the main parser. Can't call from `do` orchestrator. |
| `keyvault` passthrough → `lgwks_keyvault.py` | **MEDIUM** | Secret resolver not composable; no structured output. |
| `model-hub` passthrough → `lgwks_model_hub.py` | **LOW** | Model catalog should be inspectable from any verb; currently spawn-only. |
| `run` passthrough → `lgwks_run.py` | **MEDIUM** | Has `add_parser()` but still `_passthrough=True` in main router, so unknown args fail. |
| `repl` interactive mode | **HIGH** | Readline loop burns context on history management. Should be stateless command-per-invocation. |
| `home` animated TUI | **HIGH** | Band/spine animations are for humans. AI mode (`--machine`) should skip all rendering. |
| Review report prose (`report.md`) | **MEDIUM** | Markdown is for humans. Machine packet (`machine-packet.json`) is for AI. Both generated, but AI shouldn't need to read MD. |

---

## The Real Gap: AI Composability

The problem is not "missing features." The problem is **composability:**

### Current State (Broken)
```
Spawn A runs `lgwks review` → findings in findings/
Spawn B wants to use those findings → must read findings/report.md (prose) or parse machine-packet.json
Spawn B runs `lgwks aup check --text "..."` → gets JSON, but can't pipe that into `lgwks do govern`
Spawn C wants context pack → must spawn `lgwks_context.py` as separate process
```

### Desired State (Fixed)
```
Spawn A: `lgwks do ship --json` → structured DoRun artifact
Spawn B: reads DoRun.phases[].artifact directly (no file parsing)
Spawn B: `lgwks do govern --text "..." --json` → AUP result is a PhaseResult inside DoRun
Spawn C: `lgwks context build --run-dir ./runs/xxx --json` → CONTEXT.md path + raw symlinks
Spawn D: `lgwks model-hub list --json` → models catalog, pick one, pass to classifier
```

**The fix is not more features. The fix is wiring existing features into a composable surface.**

---

## Priority: Wire Remaining Passthrough Stubs

These modules exist, are tested, but have no `add_parser()` — they can only be called via `_passthrough=True` spawn:

| Module | Has `main()` | Has `add_parser()` | Can Call Programmatically | Gap |
|--------|------------|--------------------|---------------------------|-----|
| `lgwks_context.py` | Yes | **NO** | No | Can't build context packs from `do` orchestrator |
| `lgwks_foundation.py` | Yes | **NO** | Yes (import `extract_entities`) | Not in CLI surface |
| `lgwks_keyvault.py` | Yes | **NO** | Yes (import `get_secret`) | Not in CLI surface |
| `lgwks_model_hub.py` | **NO** | **NO** | Yes (import `list_models`) | Not in CLI surface |
| `lgwks_run.py` | Yes | Yes | Yes (import `execute_plan`) | Still `_passthrough=True` in router |

### Wiring Plan

1. **Add `add_parser()` to each module** — expose subcommands with `--json` output
2. **Remove `_passthrough=True`** from main router for wired modules
3. **Enable programmatic composition** — `lgwks_do.py` can call `lgwks_context.write_pack()`, `lgwks_foundation.extract_entities()`, etc.

---

## Priority: Context Quality (Not Quantity)

More context ≠ better context. The harness must ensure:

### 1. Graduated Resolution (Already Built ✅)
`lgwks_context` TIER 0-3 system is correct. The gap is it's not wired into `do`:
- `lgwks do research` should auto-emit a context pack after the run
- `lgwks do ship` should include the last review context in the DoRun artifact

### 2. Deterministic Re-Run (Partial)
- `jarvis crawl` is deterministic (same URL → same output) ✅
- `review` with `--bots slop_math` is deterministic (AST analysis) ✅
- `refactor` is deterministic (AST transforms) ✅
- **Not deterministic:** `akinator` research (LLM-driven, non-reproducible) — acceptable because research is inherently exploratory

### 3. Schema-Driven Everything (Already Built ✅)
Every output has a schema:
- `lgwks.review.v0`
- `lgwks.bot.record.v1`
- `lgwks.do.run.v1`
- `lgwks.jepa.package.v0`
- `aup-audit-v1`

The gap is **schema discovery** — the next AI needs to know what schemas are available without reading all source files.

### 4. R-Meter (Not Built ❌)
From ADR-004: token burn should be categorized as:
- **Recovery (R)** — re-deriving context already known
- **Invention (I)** — genuinely new reasoning
- **Noise (N)** — formatting, repetition, pleasantries

Current state: no metering. Every spawn starts from scratch.

**Fix:** Add `lgwks meter` verb that analyzes a session log and classifies token burn by category. This is an AI-AI diagnostic, not a human feature.

---

## Priority: AI-AI Communication Primitives

What the next spawn needs from me:

| Primitive | Status | Needed For |
|-----------|--------|------------|
| **Verdict** (pass/danger/deny) | ✅ `lgwks do` | Spawn B knows if Spawn A's work is safe to build on |
| **Links Index** | ✅ `lgwks_review` | Spawn B can jump to exact file:line without re-searching |
| **World DB Bindings** | ✅ `lgwks_review` | Spawn B knows which claims are grounded |
| **Context Pack** | ✅ `lgwks_context` | Spawn B reads decaying-resolution prior work |
| **Intent Trail** | ✅ `lgwks_intent` | Spawn B knows what the user actually asked for |
| **AUP Audit** | ✅ `lgwks_aup` | Spawn B knows what was refused and why |
| **Bot Record** | ✅ `lgwks_review` | Spawn B knows which checks ran and what they found |
| **JEPA Package** | ✅ `lgwks_jepa` | Spawn B gets machine + human projections |
| **Machine Packet** | ✅ `lgwks_review` | Spawn B gets structured findings, not prose |
| **L-Score** | ✅ `lgwks_review` | Spawn B knows hallucination risk of prior synthesis |

**All of these exist. The gap is they're not automatically composed into a single spawn-ready artifact.**

### Proposed: `lgwks spawn` verb

One command that assembles everything the next AI needs:
```
lgwks spawn \
  --from review-run-xxx \
  --from aup-check-yyy \
  --from context-zzz \
  --output ./spawns/next.json
```

Produces a spawn packet with:
- Verdict from review
- AUP status
- Context pack (LOD)
- Intent trail
- Machine packet
- Links index

The next AI reads ONE file instead of hunting across `findings/`, `runs/`, `governance/`.

---

## Recommended Build Order (AI-AI Harness)

| Phase | Work | Why |
|-------|------|-----|
| 1 | Wire `context`, `foundation`, `keyvault`, `model-hub`, `run` with `add_parser()` | Composability — every verb callable from `do` |
| 2 | Build `lgwks spawn` packet assembler | One artifact per spawn — no context hunting |
| 3 | Auto-emit context packs from `do` verbs | `do ship` → context pack in DoRun artifact |
| 4 | Add R-meter to `lgwks_repl` / `lgwks_session` | Measure recovery vs invention vs noise |
| 5 | Schema registry (`lgwks schema ls`) | Next AI discovers available schemas without reading source |
| 6 | Deterministic intent routing (tiny-bert) | Replace heuristic intent classifier with model-driven routing |

---

## What NOT to Build (Human-First Traps)

| Trap | Why Skip |
|------|----------|
| REST API / SaaS | Not needed — runs locally, no multi-tenant requirement |
| Web dashboard | Human feature; defer to TUI phase |
| Real-time sync | Not needed — single-machine, file-based |
| Team collaboration | Single-user harness for now |
| VS Code extension | Human IDE integration; defer |
| GitHub App / PR bot | Requires SaaS infrastructure; out of scope |
| Chat interface | `repl` already exists; chat is just multi-turn repl |
| Hosted multi-repo | Local multi-repo indexing is enough |

---

## Summary

**lgwks is 80% built for AI-AI harness.** The remaining 20% is:
1. **Wiring** — add `add_parser()` to 5 modules, remove `_passthrough=True`
2. **Composition** — `lgwks spawn` packet assembler
3. **Measurement** — R-meter for token burn categorization
4. **Discovery** — schema registry for next-agent capability discovery

No new major features needed. The infrastructure is deep and correct. The work is integration and surfacing.

---

*End of analysis. All findings based on codebase inspection at commit `9146cfd`.*
