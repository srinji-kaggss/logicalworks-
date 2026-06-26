# CLAUDE — runtime entry & agent contract (lgwks)

Canonical agent contract for this repo. `AGENTS.md` is a symlink to this file.
This file exists because the repo's truth is distributed; read this before
concluding anything from a partial search.

## What this repo is
`lgwks` — local-first, privacy-respecting developer research and refactoring
toolchain. Python CLI (`lgwks` dispatcher at root) + Rust frontier crawler
(`crawler/`) + stdlib-only byte framework (`axiom/`).

## Structural invariant — do not "clean up" the root
The ~100 `lgwks_*.py` files at root are **load-bearing**. The `lgwks` dispatcher
imports them by module name (`__import__("lgwks_<cmd>")` + `SourceFileLoader`,
see `lgwks` ~lines 1834–1901). Moving them into a package breaks the CLI and the
`cl-ideas` overlay symlinks. Root sprawl here is a contract, not a mess.

## Authority ladder (who wins on conflict)
1. **Data/ingestion layer** → `spec/second-harness/INGESTION-LAYER.md` +
   `INGESTION-PLAN.md` (v1.0, final). Supersedes anything older that disagrees,
   including `docs/archive/SPEC-tier-e-machine-model-v1.md` (historical draft).
2. **Runtime lanes / nervous system** → `docs/machine-nervous-system.md`.
3. **Byte framework** → `axiom/` module docs + `docs/axiom-end-to-end-framework-2026-06-06.md`.
4. **Governance & refusal policy** → `governance/` (see `governance/README.md`).
5. **Doctrine (cross-fleet)** → `vision/prompts/_doctrine.md`.
6. **Schemas/contracts** → `docs/schemas/REGISTRY.md` — check it BEFORE minting any
   cross-module payload; repurpose > extend > mint.
Build-state truth lives in `spec/second-harness/BUILDLOG*.md`, not in spec prose.

## Startup read order
1. This file.
2. `docs/index.md` — **the OKF Knowledge Bundle map.** `docs/` is an Open Knowledge Format
   bundle (Google-OKF-inspired): every doc is a typed concept with frontmatter, cross-linked,
   with per-directory `index.md` for **progressive disclosure** — read the index, then open only
   the concepts you need. Start here: [`docs/concepts/knowledge-format.md`](docs/concepts/knowledge-format.md)
   explains the format + lineage. Generated/validated by `scripts/gen_okf.py` (`--verify` is a CI gate).
3. `docs/navmap/README.md` — **the canonical code map / "navmap"**: generated module atlas
   (deps/used_by/subsystem/staleness). If the Director says "review the map", they mean this unless
   another is named. Read/query BEFORE grepping. Machine-readable: `docs/navmap/index.json`
   (`lgwks.navmap.v1`). Refresh: `python3 scripts/gen_navmap.py`. (navmap = code graph; OKF = docs graph.)
4. `docs/OPERATING-MODEL.md` — request lane, daemon lane, shared substrate, security membrane.
5. `docs/concepts/model-layer.md` — the two-plane model layer (one port, locality axis).
6. `docs/DAEMON-CORE-PLAN.md` — plan to finish the daemon core + first website-research experience.
7. `governance/README.md` — governance map.
8. `spec/second-harness/HANDOFF.md` + `INGESTION-PLAN.md` — current work packets.
9. `docs/AUTHORITY.md` — unified architectural rulebook: model mesh, escalation ladder, ingestion.
10. `docs/ARCHITECTURE.md` — older system-shape doctrine; useful, not the best entrypoint for the whole.
11. Assigned issue(s) — GitHub Issues are the work tracker.

## Reserved load-bearing doc nouns
- `navmap` = the repo-wide module atlas only. It lives under `docs/navmap/`.
- `README` = the entrypoint for a directory/package, not a generic synonym for any overview.
- `HANDOFF` = active transfer/state docs only. Historical one-offs should use a narrower term.
- `PRD` = product-requirements authority docs only.
- If a load-bearing noun already has a canonical home, extend that surface, version it (`vN`), or pick a new noun. Do not mint a second peer artifact with the same noun.

## Search discipline (verify before assert)
Partial search is the dominant agent failure mode. Before claiming a file,
module, or spec does not exist: `git ls-files | grep -i <term>` and
`git log --all --oneline -- '*<term>*'`. Before trusting a doc's status claims
(e.g. "X is stale"), check the file's own header and `spec/second-harness/BUILDLOG.md`.
Cite the path you verified, not the path you remember.

## Code Review Graph
- **Graph Source**: `.code-review-graph/`
- **Regenerate**: Run `./scripts/generate-graph.sh`
- **AI Context**: Use the `code-review-graph` MCP server (config in `.mcp.json`) to query the graph for blast radius analysis and architectural mapping.

## Repo constellation (cross-repo map)
- `~/logicalworks-` — this repo (lgwks toolchain).
- `~/logic-os-kernel` — Logic OS kernel (Rust, three pillars, ADR-004);
  governance in `laws/governance/`; entry doc `CLAUDE.md` there.
- `~/cl-ideas` — **private overlay of this repo**: its `lgwks_*.py` are symlinks
  into `../logicalworks-` (managed by `cl-ideas/scripts/link-logicalworks-core.sh`);
  only business/client material is local to it. Changes to engine code happen
  HERE, never in cl-ideas.
Entry doc in each repo is `CLAUDE.md` (`AGENTS.md` symlinks to it).

## Standalone Foundation Strategy (2026-06-14)
- **The North Star**: We are building the **Standalone Aetherius Model**. This is a proprietary foundation model that will eventually handle ALL tasks (embedding, reasoning, vision, research, code) natively.
- **The Workaround (Today)**: The current "Model Mesh" (Qwen3-VL, OLMo-3, WhisperKit) is a temporary **Borrowed Cognition** layer. It exists solely to provide high-fidelity "scaffolding" for current operations.
- **The Goal**: The `lgwks` daemon's primary purpose today is **Training Data Ingestion**. Every event, thought, and commitment captured in our JSONL/DB streams is a future training trajectory for the Standalone Model.

## Agent Mandates
- **Data Integrity First**: Every interaction must be recorded in the `CognitionLog` and `daemon-events.db`. This is the training material for the Standalone Model.
- **Mandatory Pre-flight**: Run `lgwks doctor` before ANY research, code analysis, or daemon task.
- **Absolute Paths**: All command executions must use absolute paths to the `lgwks` script.
- **No Hallucination**: Refer ONLY to `lgwks_model_mesh.py` for model law.

## CONTEXT STREAMING MANDATE
**If a user asks you to "review the codebase", "stream context", or "what are the rules", you MUST read the `docs/AUTHORITY.md` file and base your entire architectural understanding upon it.**
