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
   including `docs/SPEC-tier-e-machine-model-v1.md` (historical draft).
2. **Runtime lanes / nervous system** → `docs/machine-nervous-system.md`.
3. **Byte framework** → `axiom/` module docs + `docs/axiom-end-to-end-framework-2026-06-06.md`.
4. **Governance & refusal policy** → `governance/` (see `governance/README.md`).
5. **Doctrine (cross-fleet)** → `vision/prompts/_doctrine.md`.
6. **Schemas/contracts** → `docs/schemas/REGISTRY.md` — check it BEFORE minting any
   cross-module payload; repurpose > extend > mint.
Build-state truth lives in `spec/second-harness/BUILDLOG*.md`, not in spec prose.

## Startup read order
1. This file.
2. `docs/navmap/README.md` — **the canonical "map" / "navmap" for this repo**: generated module atlas
   (~46k LOC) showing what every file is, its subsystem, who calls it, and its staleness.
   If the Director says "review the map", they mean this file unless they explicitly name a different one.
   Read/query this BEFORE grepping the code surface.
   Machine-readable + queryable: `docs/navmap/index.json` (`lgwks.navmap.v1`). Refresh: `python3 scripts/gen_navmap.py`.
3. `docs/OPERATING-MODEL.md` — the comprehensive graph of the request lane, daemon lane, shared substrate, and security membrane.
4. `docs/DAEMON-CORE-PLAN.md` — the current cohesive plan to finish the daemon core and the first website-research experience.
5. `governance/README.md` — governance map.
6. `spec/second-harness/HANDOFF.md` + `INGESTION-PLAN.md` — current work packets.
7. `docs/ARCHITECTURE.md` — older system-shape doctrine; useful, but not the best entrypoint for the current whole.
8. Assigned issue(s) — GitHub Issues are the work tracker.

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

## Agent Mandates (2026-06-14)
- **Mandatory Pre-flight**: Run `lgwks doctor` before ANY research, code analysis, or daemon task.
- **Local-First Models**: Use `lgwks_model_hub` for repo-resident weights. Never assume `~/.cache`.
- **Absolute Paths**: All command executions (via `subprocess`) must use absolute paths to the `lgwks` script.
- **Telemetry v2**: Use `lgwks_daemon_event.emit()` for all audit logs. No raw `print()` for telemetry.
- **CognitionLog**: Persist all reasoning to the HMAC-chained log in `store/cognition/`.
