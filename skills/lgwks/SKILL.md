---
name: lgwks
description: "Local-first developer research, AST refactoring, code review, HTML scraping, and offline agent runtime command-line utility. Use when you need deterministic AST modifications, local semantic diffs, offline browser scraping, or agent OS diagnostics."
risk: low
source: community
date_added: "2026-06-21"
---

# lgwks

## Overview
`lgwks` is a local-first, privacy-respecting developer research and code refactoring toolchain. It runs entirely offline under Enterprise Privilege Management (EPM) restrictions, using local CoreML/ANE models and containerized local LLM options to process documents and code without external cloud calls.

This skill equips AI agents with direct operational guidelines on how to orchestrate the `lgwks` command-line utility and its submodules to perform scraping, research crawling, refactoring, and code review.

## When to Use
- When executing local, boilerplate-free document scraping or browser rendering.
- When performing deterministic Python AST modifications (renames, function extractions, type annotations, unused import removal).
- When executing deep, autonomous research crawls and website evidence extraction.
- When analyzing semantic diffs across documents or code blocks offline.
- When verifying local capability, daemon, and model mesh health.

## Installation
The `lgwks` command-line utility is pre-installed in the repository root. Before execution, run the doctor pre-flight check to verify capability health:
```bash
./lgwks doctor
```

## Step-by-Step Guide

### 1. Perform Mandatory Pre-flight
Before running any analysis, code refactoring, crawling, or daemon task, you **MUST** run the diagnostic doctor check:
```bash
./lgwks doctor
```
Ensure all required capabilities report status `ok`.

### 2. Locate Modules and Executables
Always refer to the canonical codebase module map under [docs/navmap/README.md](../../docs/navmap/README.md) to locate python script commands. 
All CLI calls **MUST** invoke the `lgwks` entrypoint script using the relative path from the repository root: `./lgwks`.

### 3. Choose the Correct CLI Command
- **HTML Scraping & Fetching**: Use `fetch <url>` or [lgwks_html.py](../../lgwks_html.py) / [lgwks_browser.py](../../lgwks_browser.py) to get boilerplate-free markdown content.
- **Deep Research / Crawling**: Use `research` (with options `--deep` and `--live`) or `crawl` for site-wide crawls.
- **AST Refactoring**: Use `refactor` for deterministic renames, unused import removal, and type mapping.
- **Code & Security Review**: Use `review` to invoke specialized analysis bots (such as `code_hacker`, `slop_math`, `optimizer`, and `stress`).
- **Semantic Diff**: Use [lgwks_diff.py](../../lgwks_diff.py) to compare Markdown files or document chunks.

---

## Examples

### Fetching a Single Page
Extract clean Markdown content from a specific URL using WebKit/Chromium:
```bash
./lgwks fetch https://example.com --json
```

### Performing an AST Refactoring Symbol Rename
Preview a symbol rename before applying:
```bash
./lgwks refactor --file ./lgwks_route.py --preview rename --old old_function_name --new new_function_name
```
Apply the rename directly:
```bash
./lgwks refactor --file ./lgwks_route.py rename --old old_function_name --new new_function_name
```

### Running AST Unused Import Stripping
Remove any unused import statements:
```bash
./lgwks refactor --file ./lgwks_route.py remove_unused_imports
```

### Initiating Deep Research
Start an autonomous, live research crawl targeting an objective:
```bash
./lgwks research "analyze Fundserv integration schemas" --deep --live --sources 5
```

### Graph-Aware Code Review
Run all security and optimization review bots against a specific git reference:
```bash
./lgwks review --ref HEAD~1 --bots code_hacker,optimizer
```

---

## Best Practices
- **Relative Path Executions**: Always execute commands using `./lgwks` from the repository root, or reference scripts relative to the workspace.
- **Preview Refactors**: Use `--preview` on `refactor` commands to evaluate modifications before committing changes to source files.
- **Model Law Integrity**: Do not hallucinate model capabilities or options. Refer only to the model configurations defined in [lgwks_model_mesh.py](../../lgwks_model_mesh.py).
- **Log Interactions**: Ensure all daemon-level interactions are stored in `CognitionLog` and `daemon-events.db` to protect data ingestion integrity.

## Troubleshooting

### Connection to Ollama Fails or Container Down
If local containerized model requests time out or fail:
- Check if Docker Desktop is running.
- The system bridge degrades gracefully; verify local model status by listing model hub options:
  ```bash
  ./lgwks model-hub list
  ```

### Doctor Diagnostic Reports Not OK
If the pre-flight check fails:
- Check the JSON diagnostic report output to find which capability (e.g., SQLite, browser engine, model mesh, local vault) failed.
- Run first-time setup or reinitialization:
  ```bash
  ./lgwks human initialize
  ```

## Related Skills
- [context7-auto-research](../../.gemini/config/skills/context7-auto-research/SKILL.md)
- [firecrawl-scraper](../../.gemini/config/skills/firecrawl-scraper/SKILL.md)
- [tavily-web](../../.gemini/config/skills/tavily-web/SKILL.md)
- [code-reviewer](../../.gemini/config/skills/code-reviewer/SKILL.md)
