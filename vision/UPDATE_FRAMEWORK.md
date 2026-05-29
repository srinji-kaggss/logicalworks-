# UPDATE_FRAMEWORK — keeping the living 3D world-map current

> How to refresh `artifacts/viz/jarvis-world-map.html` as **both** the research (`notes/*.jsonl`) and
> the **codebase** (`~/sales-landing-page`) evolve — using cheap diffs, never whole-repo re-reads.
>
> Two inputs, two independent paths, one regenerate step:
> **A. RESEARCH-UPDATE** (new pings) · **B. CODEBASE-UPDATE** (commits, schemas, issues, ADRs) ·
> **C. REGENERATE** (pure, ~0 LLM tokens). Run A alone, B alone, or A→B back-to-back, then always C.
>
> Sister contracts: `viz-data/SCHEMA.md` (graph + data-file contract), `PROTOCOL.md` / `HANDOFF.md`
> (the LW-RS/1 research system), `scripts/build_jarvis_viz.py` (the generator).

---

## 0. The sync-state ledger (makes every update a cheap delta)

One file, `viz-data/.sync-state.json`, records where we last synced from each source so the next
update only reads what changed. Create it once; bump it at the end of every successful update.

```json
{
  "schema": "viz-sync-state/1",
  "research": { "last_sync_ts": "2026-05-27T02:00:00Z", "line_counts": { "notes/cloud.jsonl": 42 } },
  "codebase": { "repo": "/Users/srinji/sales-landing-page", "last_sync_commit": "38c1d39" },
  "gh":       { "last_issue_sync_ts": "2026-05-27T02:00:00Z" },
  "generated": "2026-05-27T02:00:05Z"
}
```

`research` is git-tracked here in `logicalworks-/vision` (notes are append-only → diff by commit OR by line
count). `codebase` tracks the **app repo HEAD** we last reflected. Never trust memory for "what's new"
— always read this file first, diff against it, then write it back last.

### Watched-paths MANIFEST (what a codebase diff is even allowed to touch)
Only these paths in `~/sales-landing-page` can change the map. Ignore everything else in the diff.

| watched path | maps to data file | judgement |
|---|---|---|
| `packages/canvas-protocol/schema/*.json` | `implementation.jsonl` (+ `why-map.json`) | new/changed envelope schema → impl node |
| `governance/adr-*.md` | `implementation.jsonl` arch-strategy node + `why-map.json` | new ADR = new arch decision |
| `apps/mac/**`, `backend-rust/**` (broker/identity/tape code) | `implementation.jsonl` maturity/status | code shipped → bump `maturity`/`status` |
| GH issues (via `gh`, not files) | `gh-issues.jsonl` | new/closed/re-prioritised issues |
| `governance/security-posture.md`, `lessons-learned.json` | `implementation.jsonl` security/risk node | new risk or mitigation |

---

## A. RESEARCH-UPDATE path (new pings in `notes/*.jsonl`)

Append-only JSONL means **the diff is literally the new lines**. Never re-read a whole notes file.

```bash
cd /Users/srinji/logicalworks-/vision
LAST=$(python3 -c "import json;print(json.load(open('viz-data/.sync-state.json'))['research']['last_sync_ts'])")

# 1. New/changed note lines since last sync (git-tracked) — cheap, bounded:
git diff @{u}.. -- notes/ 2>/dev/null || git diff "$LAST_COMMIT".. -- notes/   # added '+' lines only
# Fallback if notes aren't committed between syncs — diff by recorded line count per file:
#   tail -n +$((PREV_COUNT+1)) notes/cloud.jsonl
```

**Judgement (researcher / Opus agent reads ONLY the new lines):** for each added ping decide where it
lands, per `SCHEMA.md` and `build_jarvis_viz.py`:
- `k:"node"` → world node (auto-attached to its `ly` layer hub by the generator). No file edit needed —
  it's already in `notes/`; the generator picks it up.
- `k:"os_hook"` / `k:"edge"` / `k:"arch_directive"` → also generator-native from `notes/`.
- `k:"claim"` (with `ab`) → grounds an existing node; generator attaches up to 5. No edit.
- `k:"blindspot"` → **excluded** by the generator on purpose; leave it.
- A ping that **shifts an incumbent's strength** (e.g. new cloud-share figure) → edit
  `viz-data/incumbents.jsonl` `feature_strength` (this moves `distance`).
- A ping that **changes a curated node's WHY/maturity** → edit `viz-data/why-map.json`.

So the research path is mostly **zero-edit**: new pings already live in `notes/` and the generator is
pure. You only touch `viz-data/*` when research changes an *incumbent benchmark* or a *curated why*.

---

## B. CODEBASE-UPDATE path (commits · schemas · ADRs · GH issues)

Never clone-read the repo. Diff HEAD against the recorded `last_sync_commit`, then read **only**
changed files that fall under the MANIFEST.

```bash
REPO=/Users/srinji/sales-landing-page
LAST=$(python3 -c "import json;print(json.load(open('/Users/srinji/logicalworks-/vision/viz-data/.sync-state.json'))['codebase']['last_sync_commit'])")

# 1. What commits landed? (one cheap line each)
git -C "$REPO" log --oneline "$LAST"..HEAD

# 2. Which watched files changed? (filter to the MANIFEST — ignore the rest)
git -C "$REPO" diff --name-only "$LAST"..HEAD -- \
  packages/canvas-protocol/schema governance 'apps/mac' backend-rust

# 3. New canvas-protocol schemas specifically (the high-signal trigger):
git -C "$REPO" diff --name-status "$LAST"..HEAD -- packages/canvas-protocol/schema

# 4. Markers in changed code only (don't grep the whole tree):
git -C "$REPO" diff "$LAST"..HEAD -- 'apps/mac' backend-rust | grep -E '^\+.*(TODO|FIXME)'

# 5. GH issues in ONE json call (open + priority labels), then diff against gh-issues.jsonl:
gh issue list --repo srinji-kaggss/sales-landing-page --state open \
  --json number,title,labels,state --limit 200
```

**Judgement (coder/reviewer agent reads ONLY the changed files):**
- **New schema** `packages/canvas-protocol/schema/Foo.json` → add an impl node to
  `viz-data/implementation.jsonl` with `id:"impl-<primitive>-framework"`, `band:"impl"`,
  `level:4`, the primitive's `feature`/`bin`, a `{"_link":true,"rel":"implements","dir":"uni"}` line
  to its `cv-*` primitive, and an authored `why`. Mirror its `why/tag/maturity` into `why-map.json`.
- **Changed schema** → bump the matching impl node's `maturity`/`status`/`summary` in place (keep `id`).
- **New ADR** `governance/adr-0NN-*.md` → add an `impl-<primitive>-arch-strategy` node + `why-map.json`
  entry (decision tag from the ADR's choice). Read just that one ADR file.
- **Code shipped** (e.g. broker tests added) → bump `maturity`/`status:"ships"` on the impl node.
- **GH issues** → regenerate `gh-issues.jsonl` from the single `gh` call: each open issue →
  `{id:"gh-<n>", band:"gh_issue", level:4, label:"#<n> <title>", priority:(p0→3,p1→2,p2→1,none→0),
  maturity:0}` + an `addresses` link to the `cv-*` primitive (or bin) it targets. Closed issues drop
  out. Collapse near-dup series into one node with a `count` note (existing convention).
- **New risk** (`security-posture.md` / `lessons-learned.json`) → impl `risk`/`security` node + why.

---

## C. REGENERATE (pure — run after A, B, or both; ~0 LLM tokens)

```bash
cd /Users/srinji/logicalworks-/vision
python3 scripts/build_jarvis_viz.py        # reads notes/*.jsonl + viz-data/* → writes the HTML
# → wrote artifacts/viz/jarvis-world-map.html  /  nodes: N links: M / by kind: {...}
```

The generator is deterministic and reads the data files directly — no tokens to run. It **escapes
`</` → `<\/`** and **inlines** `GRAPH`/`META` as JSON into the single HTML, so research text containing
`</script>` can never break the page and the artifact is fully self-contained (CDN only for the engine).

After a clean run, **write `viz-data/.sync-state.json` back** with the new `last_sync_ts`,
`last_sync_commit` (= app-repo HEAD), and refreshed line counts.

---

## Diff / append convention (keeps diffs clean)

- **Append-only, never rewrite history.** New facts are new lines (LW-RS/1). To correct a ping, emit a
  new line with `sup:"<old-id>"` (supersedes); the old id stays for audit. `viz-data/*.jsonl` follow the
  same rule — append a corrected object, don't mutate the historical one unless it's a simple in-place
  maturity bump on a node you own.
- **Stable ids.** `wm-*` (research), `cv-*` (primitives), `impl-*` (foundation), `inc-*` (incumbents),
  `gh-<n>` (issues). Stable ids → diffs show only true changes, and links never dangle.
- **First line of every JSONL stays `{"std":"LW-RS/1"}`** (notes) or the `# format:` comment header
  (`viz-data/*.jsonl`); the generator skips both.

---

## Definition of done / QA gate (every update must pass)

```bash
cd /Users/srinji/logicalworks-/vision
# 1. JSON validity — every data line parses:
for f in notes/*.jsonl viz-data/*.jsonl; do
  awk 'NR>1 && $0!~/^#/' "$f" | python3 -c 'import sys,json;[json.loads(l) for l in sys.stdin if l.strip()]' \
    && echo "OK $f" || echo "BAD $f"; done
python3 -c "import json;json.load(open('viz-data/why-map.json'))" && echo "OK why-map"

# 2. Generator runs clean (referential integrity is enforced: it drops links to missing nodes —
#    a shrinking link count vs last run flags a dangling ref to investigate):
python3 scripts/build_jarvis_viz.py
```

- [ ] All JSONL/JSON parse (loop above all `OK`).
- [ ] **Referential integrity:** every `refs`/`source`/`target`/`addresses`/`implements`/`benchmarks`
      points at a node that exists (generator silently drops dangling links — compare `links:` count to
      the prior run; an unexpected drop = a broken ref to fix, not to ignore).
- [ ] **Frontier distance recomputed:** if incumbents or primitive maturity changed, confirm
      `distance = clamp(incumbent_strength − maturity, 0, 1)` is reflected (HUD frontier number moved).
- [ ] Generator prints `wrote …jarvis-world-map.html` with sane `nodes/links/by kind` counts.
- [ ] `viz-data/.sync-state.json` bumped to the new commit/ts.
- [ ] Append-only respected: corrections used `sup`, no history rewritten, ids stable.

---

## TL;DR cheat sheet — three recipes

```bash
cd /Users/srinji/logicalworks-/vision
REPO=/Users/srinji/sales-landing-page
LASTC=$(python3 -c "import json;print(json.load(open('viz-data/.sync-state.json'))['codebase']['last_sync_commit'])")

# ── RESEARCH-ONLY ───────────────────────────────────────────────
git diff @{u}.. -- notes/                       # read ONLY new ping lines
#   → most pings are zero-edit (generator reads notes/ directly);
#     edit viz-data/incumbents.jsonl or why-map.json only if a ping moves a benchmark/curated why
python3 scripts/build_jarvis_viz.py             # regenerate

# ── CODEBASE-ONLY ───────────────────────────────────────────────
git -C "$REPO" log --oneline "$LASTC"..HEAD                                   # what landed
git -C "$REPO" diff --name-only "$LASTC"..HEAD -- packages/canvas-protocol/schema governance
gh issue list --repo srinji-kaggss/sales-landing-page --state open \
  --json number,title,labels,state --limit 200                               # one call
#   → edit implementation.jsonl (+why-map.json) for schemas/ADRs; rebuild gh-issues.jsonl from the json
python3 scripts/build_jarvis_viz.py             # regenerate

# ── COMBINED (back-to-back, then ONE regenerate) ────────────────
git diff @{u}.. -- notes/                                                     # A: research diff
git -C "$REPO" log --oneline "$LASTC"..HEAD                                   # B: codebase diff
gh issue list --repo srinji-kaggss/sales-landing-page --state open --json number,title,labels,state --limit 200
#   apply A edits + B edits to viz-data/*  →  run QA gate  →
python3 scripts/build_jarvis_viz.py             # C: single pure regenerate
#   then bump viz-data/.sync-state.json (last_sync_ts + last_sync_commit=$(git -C "$REPO" rev-parse HEAD))
```
