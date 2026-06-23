# Logical Works Core (`lgwks`)

> [!IMPORTANT]
> **Source of Truth Declaration:** This repository (`logicalworks-`) serves as the official, canonical source of truth for all core Logical Works modules, parser engines, utility functions, site profiles, and CLI configurations. All sister repositories, including private work environments like `cl-ideas`, import or symlink directly from this codebase to consume its engines.

> [!IMPORTANT]
> **Repo map:** the canonical repo map is [docs/navmap/README.md](/Users/srinji/logicalworks-/docs/navmap/README.md). If someone says "review the map" or "check the navmap", this is the file they mean unless another map is explicitly named. Queryable form: [docs/navmap/index.json](/Users/srinji/logicalworks-/docs/navmap/index.json).

> [!IMPORTANT]
> **System shape:** the best current explanation of how the whole repo fits together is [docs/OPERATING-MODEL.md](/Users/srinji/logicalworks-/docs/OPERATING-MODEL.md). Read this after the navmap if you need the full request-path + daemon-path + security picture.

> [!IMPORTANT]
> **Execution plan:** the current plan for finishing the daemon core and the first website-research experience is [docs/DAEMON-CORE-PLAN.md](/Users/srinji/logicalworks-/docs/DAEMON-CORE-PLAN.md).

`lgwks` is a local-first, privacy-respecting developer research and code refactoring toolchain. It runs entirely offline under Enterprise Privilege Management (EPM) restrictions, using local CoreML/ANE models and containerized local LLM options to process documents and code without external cloud calls.

---

## 1. System Architecture

```mermaid
graph TD
    subgraph logicalworks- [Source of Truth Codebase]
        CLI[lgwks CLI] --> html[lgwks_html.py]
        CLI --> site_profile[lgwks_site_profile.py]
        CLI --> diff[lgwks_diff.py]
        CLI --> refactor[lgwks_refactor.py]
        CLI --> local_llm[lgwks_local_llm.py]
    end

    subgraph cl-ideas [Private / Gated Sandbox]
        fundserv[fundserv module] -.-> |Imports symlinked core| html
        fundserv -.-> |Imports symlinked core| site_profile
        fundserv -.-> |Imports symlinked core| diff
    end
```

---

## 2. Core Capabilities

### A. Global HTML-to-Markdown Scraper (`lgwks_html.py`)
Provides deterministic, boilerplate-free document extraction modeled after Crawl4AI and Firecrawl:
- Strips headers, footers, navigation, styles, scripts, and cookie consent banners.
- Reconstructs complex HTML tables with `rowspan` and `colspan` grid layout carrying.
- Automatically differentiates between ordered (`ol` -> `1. `) and unordered (`ul` -> `- `) list syntax by walking the parent tag stack.

### B. Semantic Diff Engine (`lgwks_diff.py`)
Extracts structural modifications, insertions, and deletions across two sets of parsed document chunks or Markdown files:
- Exact matches identified via SHA-256 hashes.
- Partial matches identified using Difflib sequence matching ratios.

### C. AST-Based Code Refactoring Engine (`lgwks_refactor.py`)
Provides safe, deterministic transformations on Python source files without using LLM generation:
- Renaming symbols (variable names, arguments, functions, classes).
- Extracting blocks into new functions/methods.
- Inserting type annotations dynamically based on a target parameter mapping.
- Removing unused imports based on name reference collection.

### D. Local LLM Bridge (`lgwks_local_llm.py`)
Thin, local-only bridge to a containerized Ollama instance running in Docker Desktop on Mac:
- Integrates small models like `qwen2.5-coder:1.5b` for offline coding assistant tasks.
- Degrades gracefully (no errors or locks) if the Docker container is stopped.

---

## 3. CLI Reference

`lgwks` is the canonical entrypoint. Sidecar tools like the research driver, auth vault, agent-os
bootstrap, context packer, execution spine, and model hub are available as subcommands under the
same binary:

```bash
./lgwks agent-os doctor
./lgwks auth ls
./lgwks akinator --demo
./lgwks run --demo
./lgwks context path/to/run
./lgwks model-hub list
```

Run the self-tests to verify your install health:
```bash
./lgwks doctor
```

### Research Crawl
To run the research crawler:
```bash
./lgwks jarvis crawl <url>
```

### Single-Page Fetch
To render and extract one page in a browser:
```bash
./lgwks fetch <url>
```

### Refactoring
Deterministic AST modifications:
```bash
# Preview modifications first
./lgwks refactor --file path/to/code.py --preview rename --old old_func --new new_func

# Apply modifications directly
./lgwks refactor --file path/to/code.py rename --old old_func --new new_func
```

---

## 4. Symlink Configuration in `cl-ideas`

To consume core changes inside `cl-ideas/fundserv/`, symlinks are established in the root of `cl-ideas` pointing back to `logicalworks-`:
```bash
cd cl-ideas
ln -sf /Users/srinji/logicalworks-/lgwks_html.py .
ln -sf /Users/srinji/logicalworks-/lgwks_site_profile.py .
ln -sf /Users/srinji/logicalworks-/lgwks_diff.py .
ln -sf /Users/srinji/logicalworks-/lgwks_refactor.py .
ln -sf /Users/srinji/logicalworks-/lgwks_local_llm.py .
```
This guarantees that all improvements to the core parser, diff utility, or CLI immediately benefit the private authenticated standard crawler pipeline.

---

## Planning Maps

High-level planning work that is intentionally structured for cheaper follow-on agents lives in flat doc sets under `docs/`.

Current planning entrypoints:

- [docs/bot-fabric/README.md](/Users/srinji/logicalworks-/docs/bot-fabric/README.md) — non-AI bot fabric + JEPA + synthesis plan
- [docs/archive/jepa-program-map-2026-06-06.md](/Users/srinji/logicalworks-/docs/archive/jepa-program-map-2026-06-06.md) — JEPA product/program map
- [docs/archive/spec-jepa-visual-workbench-2026-06-06.md](/Users/srinji/logicalworks-/docs/archive/spec-jepa-visual-workbench-2026-06-06.md) — human visual workbench direction

Local ML direction in this repo is Apple-native first:

- [lgwks_foundation.py](/Users/srinji/logicalworks-/lgwks_foundation.py) — Foundation-backed on-device structured extraction seam
- [lgwks_coreml.py](/Users/srinji/logicalworks-/lgwks_coreml.py) — CoreML classifier seam
- [docs/ml-001-intent-classifier-sizing.md](/Users/srinji/logicalworks-/docs/ml-001-intent-classifier-sizing.md) — ANE-friendly membrane sizing
