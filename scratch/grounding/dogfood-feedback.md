# lgwks CLI — honest dogfood (2026-06-01)

Working dir: `~/logical-works/Logical Claude Works - jarvis`. Ran every command, observed, fixed nothing.

## TL;DR verdict
- `solve git` is the strongest surface: legible, trustworthy, correct stdout/stderr split, JSON is clean CSL-JSON. Ship-grade.
- `jarvis crawl` works and is honest about its boundary, but flag help is bare and concept extraction is raw n-gram noise.
- **Research via the akinator is NOT easy today.** A real (non-demo) run hangs for minutes with zero output because the Tongue model call blocks on a 300s timeout with no progress signal. Only `--demo` (offline skeleton) is reliably usable.

---

## 1. `solve git --thought "did I lose work?"` — human experience
- **Works:** Genuinely legible. Phase glyphs (sleuthing reflog / reading HEAD / reconstructing / proving) narrate the work. Plain-English story ("you rewrote history, 19 dangling commits, recoverable") then a finding with concrete recovery commands (`git show`, `git branch rescue/…`) and the `∵ proof:` line citing the exact git command. "Reversible-first" reassurance lands. Signature footer with integrity hash.
- **Painful:** The `--thought` I passed ("did I lose work?") never appears in the human output — it's silently ignored in rendering (JSON shows `"thought": ""` even when I'd expect it echoed). User can't tell their worry was heard/addressed.
- **Human-friction:** Minor — "integrity:unanchored" is jargon with no hint what anchoring would mean.
- **AI-friction:** None for reading; an agent would use --json anyway.

## 2. `solve git --json` — machine surface
- **Works:** Clean. Glyphs correctly go to **stderr** (confirmed: `2>/dev/null` leaves pure JSON on stdout — by design, `lgwks_solve.py:45-46`). Schema `lgwks.solve.v0`, real CSL-JSON references (`type/title/author/source/issued.date-parts`), findings carry `severity` + `next_step` + `evidence` IDs that resolve into `references`. Directly machine-usable.
- **Exit codes:** success=0, not-a-repo=1 (clean JSON `{"error": …}`), argparse error=2, unbuilt target=2. Sane and parseable.
- **Painful / AI-friction:**
  - Exit code is **always 0 on success regardless of finding severity** (`lgwks_solve.py:288`). A `danger`-severity finding ("you may have lost work") still exits 0. An agent cannot branch on outcome via `$?`; it MUST parse JSON severity. Defensible, but undocumented — worth stating in help.
  - `--thought` is dropped into the payload as `""` rather than echoing the caller's string. If an agent passes a claim to "prove this," it can't confirm from the output which claim was evaluated.

## 3. `--help` discoverability (fresh-agent zero-knowledge test)
- **Works (top + solve):** `lgwks --help` and `lgwks solve --help` give flag names, the `--thought` help string is good ("your worry/claim — 'prove this for me'"), `--json` documents CSL-JSON.
- **Painful / AI-friction:**
  - `target` is described only as "currently: git" — no statement of what `solve git` actually inspects (reflog, fsck, dangling commits). A fresh agent learns the flag exists but not the semantics or when to call it.
  - **No example invocation anywhere.** No `--json` schema name in help. No note that exit code ≠ severity.
  - `jarvis crawl --help`: **most flags have NO help text** — `--max-pages`, `--max-depth`, `--workers`, `--chunk-words`, `--chunk-overlap`, `--max-terms`, `--compress-limit`, `--similarity-threshold` are all bare. No defaults shown, no units. Three overlapping ways to pass keywords (`source` positional, `keyword_terms` variadic, `--keywords`) with zero guidance on the difference. A fresh agent cannot configure a sane run without reading source.

## 4. Actually doing research (`jarvis crawl` + akinator)
- **`jarvis crawl` real run (example.com, --max-pages 2):** WORKS. Printed compute estimate, per-page progress with timing, then run-name + REPORT.md path + sqlite db path. REPORT.md is honest ("deterministic map, not a claim verifier; promotion requires validator/human"). 
  - **Painful:** "Top Concepts" are raw n-grams with trailing punctuation and junk — `operations.`, `permission. avoid`, `domain domain use`, `example domain example domain`. On a real corpus this is low-signal noise, not concepts. No stopword/punctuation cleaning.
  - `--estimate-only` emits JSON **without** requiring `--json` (inconsistent with solve). Estimate is opaque: `{"estimated_seconds": 9.2}` — no page count, token, or cost basis shown.
- **akinator `--demo`:** the research UX is genuinely good when it runs — falsifiable causal chains, confidence bars (`C=0.723`), explicit nulls/falsifiers ("falsifier we dive toward — strip bias"), constitution/law gate, path-map export. This is the compelling surface.
- **akinator real run (objective + --purpose + --pick 1, no offline flag): HUNG.** Produced zero output for 4+ minutes at ~0% CPU; I had to TaskStop it.
  - **Root cause (confirmed in source):** non-demo path calls `tongue_enrich` → `lgwks_tongue.compile_hypotheses` → `lgwks_ollama.generate_json` with **`timeout=300`** (`lgwks_ollama.py:103`). If Ollama is up but the Tongue model is missing/slow/loading, it blocks up to 5 min **per call** with no progress line and no CPU. Looks identical to a hang.
  - `--demo --pick 1` (offline skeleton, skips Tongue) eventually returned exit 0 but took ~3 min and produced almost nothing past the dive trail line — still far slower than an "offline deterministic" pass should be.
- **AI-friction (big):** an agent calling the akinator for real research gets silence, no heartbeat, no "waiting on model…" line, no fail-fast. It cannot distinguish "thinking" from "dead." This makes autonomous/background use unsafe.

## 5. Break-it tests
- `solve git --repo /tmp --json` → `{"error": "/private/tmp is not inside a git work tree …"}`, exit 1. **Clean.**
- `solve git --bogus-flag` → argparse usage + error, exit 2. Good.
- `solve banana` → "target 'banana' not built yet — only `git` so far", exit 2. Good (message on stderr).
- `jarvis crawl` (no args) → "needs a website URL or at least one keyword", exit 1. Good.
- `jarvis crawl not-a-url-at-all --estimate-only` → **silently accepted** as a keyword seed, exit 0. No warning it isn't a URL — ambiguous source/keyword handling, no validation.
- `jarvis crawl … --max-pages abc` → argparse invalid-int, exit 2. Good.
- `jarvis crawl … --max-pages 0 --estimate-only` → accepted, `estimated_seconds: 0.0`, exit 0. **No lower-bound validation** — a 0-page run is meaningless but allowed.

---

## The one fix that would help most (per surface)
- **akinator / research path:** fail fast + heartbeat. Drop the Tongue call timeout from 300s to ~15-20s, and print a stderr progress line ("compiling hypotheses via Tongue… / Tongue unreachable, using deterministic skeleton") so a real run is never a silent multi-minute hang. **This is the single biggest blocker to research being "easy" today.**
- **crawl:** add help text + defaults to every flag, and clean concept extraction (strip punctuation/stopwords).
- **solve:** echo `--thought` back in the payload, and document in --help that exit code is success/failure only (severity lives in JSON).

## Is research actually easy with this today? — Blunt answer
**No, not for a real run.** The `solve git` tool is production-quality and a delight. But the research engine (akinator live path) hangs silently for minutes on the model call with no feedback or fast-fail, and the only reliable mode is the offline `--demo` skeleton that doesn't do real research. `jarvis crawl` works mechanically but its flags are undocumented and its output concepts are n-gram noise. So: the *scaffolding and epistemics are excellent* (falsifiers, provenance, honest boundaries), but the *live research loop is not yet usable hands-off* — it needs fail-fast timeouts, progress signal, and flag documentation before an agent (or impatient human) can actually DO research with it.
