---
type: Reference
title: jarvis crawl - substrate bridge
description: As of commit on branch issue-34-jarvis-substrate-bridge, lgwks jarvis crawl <url routes
tags: [reference]
timestamp: 2026-06-07T09:17:50-04:00
---

# jarvis crawl -> substrate bridge

## Summary

As of commit on branch `issue-34-jarvis-substrate-bridge`, `lgwks jarvis crawl <url>` routes
through the **substrate auth-aware mapping runtime** (`lgwks_substrate.build_run`) by default
for URL sources.

Keyword-only crawls (`lgwks jarvis crawl --keywords "RRSP retirement"`) continue to use the
**legacy Jarvis threaded-fetch path**, as before.

---

## Engine selector

```
lgwks jarvis crawl <url> [--engine substrate|legacy]
```

| `--engine` | Trigger condition | What runs |
|---|---|---|
| `substrate` (default) | Source is an `http://` or `https://` URL | `lgwks_substrate.build_run()` |
| `legacy` | Any crawl when explicitly requested | Original Jarvis threaded-fetch path |
| *(implicit legacy)* | No URL source (keyword-only) | Original Jarvis threaded-fetch path |

---

## Output schema

When the substrate engine is active, `lgwks jarvis crawl <url>` emits:

```json
{
  "schema": "lgwks.jarvis.substrate_crawl.v0",
  "engine": "substrate",
  "run_id": "example-com-20260607-120000",
  "target": "https://example.com",
  "substrate_manifest": "/abs/path/to/run/manifest.json",
  "crawl_map":         "/abs/path/to/run/crawl_map.json",
  "substrate_db":      "/abs/path/to/run/substrate.db",
  "graph_json":        "/abs/path/to/run/graph.json",
  "counts":    {"sources": 12, "documents": 10, "chunks": 48, ...},
  "embedding": {"provider_requested": "auto", "total_vectors": 48, ...},
  "auth":      {"login_if_needed": true, "browser_engine": "webkit", ...}
}
```

The legacy path output format is unchanged (human-readable, writes to runs/).

---

## New flags (passthrough to substrate engine)

| Flag | Default | Purpose |
|---|---|---|
| `--login-if-needed` / `--no-login-if-needed` | `True` | Detect auth walls and prompt for browser session |
| `--login-url` | `""` | Explicit login URL (defaults to target when auth is detected) |
| `--auth-selector` | `None` | CSS selector for post-auth SPA success confirmation |
| `--chromium` | `False` (WebKit) | Use Chromium instead of WebKit for browser sessions |
| `--embed-provider` | `deterministic` | Embedding provider for URL crawls; use `auto`, `ollama`, or `apple-local` to opt into semantic local embeddings |
| `--embed-model` | `""` | Optional explicit embedding model id |

---

## What remains on the legacy path

- `--workers` (parallel fetch workers) - legacy only, ignored by substrate
- `--include-external` (follow off-site links) - legacy only
- `--search-expansion` (googler site: expansion) - legacy only
- `--similarity-threshold`, `--compress-limit`, `--max-terms` - legacy only

These flags are still accepted by the parser so that callers do not break, but
they are silently ignored when `--engine substrate` is active.

---

## Arg mapping

| Jarvis crawl arg | Substrate `build_run` arg |
|---|---|
| `source` | `target` |
| `--name` / slugify(source) | `project` |
| `--max-pages` | `max_pages` |
| `--max-depth` | `max_depth` |
| `--chunk-words` | `chunk_words` |
| `--chunk-overlap` | `chunk_overlap` |
| `--login-if-needed` | `login_if_needed` |
| `--login-url` | `login_url` |
| `--auth-selector` | `success_selector` |
| `--chromium` -> `"chromium"` / `"webkit"` | `browser_engine` |
| `--embed-provider` | `embed_provider` |
| `--embed-model` | `embed_model` |

---

## Transition timeline

| Phase | Status |
|---|---|
| URL crawls -> substrate (default) | This PR |
| Keyword-only -> substrate (search expansion) | Future (needs substrate search-expansion seam) |
| Legacy path removal | Future (after all workflows migrated) |
| Apple-local embedding provider seam (#35) | Future (separate PR) |
| Fundserv authenticated baseline (#36) | Future (needs live auth) |
