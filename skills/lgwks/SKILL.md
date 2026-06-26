---
name: lgwks
description: |
  Local-first, offline research, document ingestion, AST refactoring, code review, and
  semantic search for agents — no cloud, no per-call subscription. Use when you need to
  turn ANY local file or URL (PDF incl. image-only/scans, docx/xlsx/pptx, epub, images,
  HTML, code) into bounded text an agent can reason over; do deterministic AST
  refactors (rename / add types / remove unused imports); run graph-aware code review;
  or fetch/ground research offline. Beats Firecrawl on local/private docs and
  Sourcegraph/Cursor on a no-egress, no-subscription footing.
allowed-tools:
  - Bash(lgwks *)
  - Bash(./lgwks *)
---

# lgwks

Local-first developer toolchain for agents: read anything, refactor, review, research —
offline, no SaaS bills, no egress of document bytes. Runs on the host (serious hardware,
not a potato); deterministic tiers first, model tiers last.

## When to use

- **Read anything → text**: a PDF spec (even a scanned/image-only one), docx/xlsx/pptx,
  an epub, an image, a JS-walled page, a local code file. → `lgwks extract`
- **Materialise as a file**: same sources written to txt/markdown/json. → `lgwks convert`
- **AST refactor**: rename a symbol, strip unused imports, add type annotations — preview
  or apply. → `lgwks refactor`
- **Code review**: graph-aware findings on a diff/ref, structured JSON. → `lgwks review`
- **Research**: autonomous deep loop, or a fast local repo world-view (`--probe`), or
  single-shot grounding (`--quick`). → `lgwks research`
- **Scrape one page**: clean markdown from a URL (WebKit). → `lgwks fetch`
- **Capability/health check** before any of the above. → `lgwks doctor`

## Quick start

```bash
# 0. Pre-flight (run once before any task)
./lgwks doctor

# 1. Read anything → text (image-only PDFs OCR'd locally; office/epub via stdlib zipfile)
./lgwks extract ./spec.pdf                 # → text to stdout
./lgwks extract ./spec.pdf --json          # → {ok,kind,text,truncated,chars,total_pages}
./lgwks extract https://arxiv.org/pdf/1706.03762 --json
./lgwks extract ./scanned.pdf --pages 4-12 --max-chars 20000   # resume a truncated extract

# 2. Materialise
./lgwks convert ./notes.docx --to md --out notes.md
./lgwks convert ./data.xlsx --to json

# 3. AST refactor (preview first)
./lgwks refactor --file ./route.py --preview rename --old get_user --new fetch_user
./lgwks refactor --file ./route.py rename --old get_user --new new_fn
./lgwks refactor --file ./route.py remove_unused_imports
./lgwks refactor --file ./route.py add_types --type-map '{"x":"int","y":"str"}'

# 4. Review (structured)
./lgwks review --ref HEAD~1 --json --bots code_hacker,optimizer

# 5. Research (offline-friendly)
./lgwks research "compare auth schemas" --probe          # repo world-view, no network
./lgwks research "summarise the spec" --quick             # single-shot grounding

# 6. Scrape one page
./lgwks fetch https://example.com --json
```

## Commands

| Command      | Purpose                                                          |
| ------------ | ---------------------------------------------------------------- |
| `extract`    | Any URL/local file → bounded text; `--json` envelope, `--pages`, `--max-chars` |
| `convert`    | Same → txt/md/json artifact (`--out`)                            |
| `refactor`   | Deterministic AST: `rename`, `add_types`, `remove_unused_imports` (`--preview`) |
| `review`     | Graph-aware review on `--ref`/`--changed`; `--json` structured findings |
| `research`   | `--deep` (loop) / `--probe` (repo world-view) / `--quick` (single-shot) |
| `crawl`      | Site-wide crawl                                                  |
| `fetch`      | One URL → clean markdown (WebKit; `--json`, `--chromium`)        |
| `repo`       | Repo-level operations                                            |
| `graph`      | Code graph (`--impact`, `--files`)                               |
| `solve`      | Deterministic causal/explanative solve                          |
| `agent`      | The unified autonomous door (orchestration)                      |
| `ops`        | daemon / batch / agent-os / workflow                             |
| `state`      | run / context / spawn / crdt / cortex / fabric                  |
| `doctor`     | Capability + daemon health pre-flight                           |
| `model-hub`  | list / load / convert / train / doctor (local models)            |
| `manifest`   | Manifest render/inspect (`--for-agent`)                          |
| `verify`     | Tiered verification (`--profile`, `--tier`)                      |
| `human`      | login / tui / repl / initialize                                  |
| `auth`       | Capability auth vault                                            |
| `gate`       | Gate framework                                                   |

## Tips

- **Local-first by design.** No document bytes leave the host — OCR is poppler +
  macOS Vision (on-device), office/epub is stdlib `zipfile`. No `brew install`, no keys.
- **Truncation is honest.** `extract` flags `truncated:true` + `total_pages`; the
  non-JSON path prints a stderr marker with the `--pages` continuation. Never mistake a
  slice for the whole — pipe `--json` if you want the envelope, or read the stderr marker.
- **`extract` is content-sniff, not URL-pattern.** arxiv `/pdf/<id>`, doi redirects,
  scholar links, publisher `/article/<doi>` are routed by the bytes' magic, not the URL.
- **Preview refactors.** `--preview` shows the planned changes; apply without it.
- **Pre-flight once.** `lgwks doctor` before a research/daemon/review task.
- **Find modules by the navmap**, not memory: `docs/navmap/README.md` (+ `index.json`) is
  the canonical module atlas; re-run `python3 scripts/gen_navmap.py` if stale.

## See also

- `docs/navmap/README.md` — the canonical repo module atlas (query before grepping the surface)
- `docs/AUTHORITY.md` — the unified architectural rulebook (15-layer model mesh)
- `governance/` — refusal/egress policy (why nothing phones home)