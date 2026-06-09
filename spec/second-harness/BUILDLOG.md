# Second Harness — Build Log (researcher's notebook)

Append-only. One entry per unit/experiment. PRD (`PRD.md`) is the frozen end-state;
this log is the *path* to it — decisions, experiments, results, open questions.
Discipline: Karpathy guidelines (think-first · simplicity · surgical · goal-driven).

---

## 2026-06-09 · Karpathy repo scan (requested, not forced)

Scanned github.com/karpathy. Candidates for reuse: `minbpe` (BPE tokenizer, MIT),
`llama2.c`/`llm.c` (single-file decoder inference, MIT), `micrograd` (autograd, edu).
**Verdict: no clean fork.** Our cortex is BERT-class *encoders* (distilbert/neobert/
tiny-bert/codebert) shipping their own tokenizers; the decoder-LLM repos and minbpe
don't fit the encoder path. The transferable asset is the *philosophy* — minimal,
single-file, readable — already followed by `lgwks_ingest.py` / `lgwks_map.py`.
Logged so a future reader doesn't re-litigate.

---

## 2026-06-09 · U1 Capability Map (done — `lgwks_map.py`, commit 65a1a59)

Goal: on any intent, "what is the scale of what exists?" → ranked lgwks verbs.
Method: deterministic token-overlap over the `lgwks manifest` contract (175 verbs);
name-hit weighted 3×, intent-hit 1×, query-normalized. No model runtime.
Result: sensible top-k, 139ms. Verified live (crawl-intent → crawl/extract verbs;
code-review-intent → do code/review). Ceiling: lexical, not semantic (U4/U6 upgrade).

---

## 2026-06-09 · U7 Inbound Hook — SPEC

### Goal (verifiable)
On a Director prompt, a `UserPromptSubmit` hook computes the subconscious inbound
pass and **injects a non-generative read into Opus's context** — closing the first
real subconscious loop (prompt → daemon → in-context), zero extra Opus action.

First slice = deterministic: inject the **U1 capability map** for the prompt. No
scores/retrieval yet (those need U3/U6) — per Karpathy simplicity, emit only what is
real; declare nothing speculative.

### Convergence target (end state, PRD §5)
The existing global `~/.claude/hooks/verify-before-assert.sh` (static operating-loop
prose, fires on UserPromptSubmit to fight the premature-conclusion defect) is the
subconscious's ancestor. End state: it *becomes* the BERT-backed dynamic grounding
check ("check with bert"), not a static block. U7 is step 1 of that evolution.

### Why not just edit verify-before-assert now (surface the tradeoff — Karpathy #1)
- It is GLOBAL (all projects); wiring lgwks-specific logic there would run lgwks in
  every unrelated session. Wrong scope.
- The BERT runtime is not built (U4). A dynamic check today can only be deterministic.
- A bad UserPromptSubmit hook can disrupt every prompt (30s cap). Must be fail-silent
  and standalone-proven before it goes live.
→ Decision: build a **project-scoped** inbound hook for THIS session, deterministic,
  coexisting with the global static floor. Fold them together when U4 lands.

### Design (minimal, surgical)
- `hooks/subconscious_inbound.py`: read UserPromptSubmit JSON on stdin → `prompt` →
  `lgwks_map.map_intent` → emit `hookSpecificOutput.additionalContext` = a compact,
  non-generative capability-map block. **Fail-silent**: ANY error → exit 0, no output
  (INV-6 never-block; a subconscious must never block consciousness).
- `lgwks_map`: make the `lgwks` binary path resolve via `__file__` (cwd-independent) —
  required because the hook runs from the session cwd, not the repo. Surgical fix.
- Register as a project `UserPromptSubmit` hook in the active session settings,
  additive — global `verify-before-assert.sh` untouched.

### Success criteria (goal-driven — loop until all pass)
1. `echo '{"prompt":"crawl a site"}' | python3 hooks/subconscious_inbound.py` → valid
   hook JSON with a capability-map `additionalContext`. 
2. Empty / malformed / huge stdin → exit 0, no crash, no output (fail-silent).
3. Runtime < 1s.
4. Registered additively; existing global hook intact; settings valid JSON.
5. Live: a subsequent prompt shows the injected block in Opus's context (activates on
   session reload — noted, not asserted).

### Open questions
- Hot-reload: does editing project settings.json activate mid-session, or only on
  reload? Unknown — will state honestly, not assert.
- Latency: hook spawns `lgwks manifest` (~150ms). Acceptable now; cache verbs later.

### U7 RESULTS (done)
Built `hooks/subconscious_inbound.py` + cwd-independent fix to `lgwks_map` (lgwks
binary resolved via `__file__`). Registered as a project `UserPromptSubmit` hook in
`/Applications/Logical Works/.claude/settings.local.json` (additive; the 134-entry
permissions block and the global `verify-before-assert.sh` are untouched).

Success criteria — all pass:
1. valid prompt → valid hook JSON with capability-map `additionalContext`. ✓
   ("crawl a website…" → jarvis crawl/run crawl/crawl/extract)
2. empty / garbage / blank / 50k-token prompt → exit 0, no output, no crash. ✓
3. 180ms (<1s). ✓
4. settings valid JSON; permissions preserved; global hook intact. ✓
5. LIVE activation: pending session reload (hooks load at session start). The script
   is standalone-proven; the in-context injection will show on the next prompt after
   reload. NOT asserting it fires mid-session — unverified, flagged.

Revert: delete the `hooks` key from that settings.local.json.
Convergence (later, U4+): fold this into the BERT-backed check that supersedes the
static verify-before-assert floor.

Next (sequential, per Director): U2 Actor contract → U3 → U4 …
