# PRD-02 — Code Intelligence (the code half of the World-Graph)

Parent: [PRD.md](../PRD.md) L0/U3 · Status: draft v0.1 · absorbs [inputs/gemini-code-graph-rag.yaml](inputs/gemini-code-graph-rag.yaml)
Replaces: **Greptile** (code graph context), **Serena** (LSP semantic toolkit), Cursor/Copilot-class code context.

## Problem

Code questions ("who calls this", "what breaks if I change this signature", "where is the
trust boundary") are graph traversals, not text search. Today the harness answers them by
burning Opus tokens on Grep/Read fan-outs, or by renting a vendor graph (Greptile) /
running a third-party MCP (Serena). Both violate own-don't-subscribe; the fan-out violates
token economy.

## Thesis

One owned code graph, built by incremental AST parsing, queried deterministically,
embedded for ranking only. Greptile's value is the graph; Serena's value is LSP precision;
both are reproducible locally over repos we already have on disk.

## Absorbed from the input YAML — with deviations (//why each)

| YAML proposal | Verdict | //why |
|---|---|---|
| tree-sitter incremental parsing (mutated subtrees only) | ADOPT | right tool; local; incremental matches daemon FileChanged tap |
| LSP indexing alongside AST | ADOPT (phase 2) | LSPs already installed per global tooling (gopls, rust-analyzer, ts); precision for types/refs AST can't give |
| node types File/Dir/Class/Interface/Function/Commit/Contributor | ADOPT, + `Verb`,`Skill`,`Hook` | our graph also maps the harness itself |
| edges CALLS/INHERITS/IMPLEMENTS/IMPORTS/DEFINES_VARIABLE | ADOPT | standard; deterministic edges per INV-4 |
| Kafka / AWS Kinesis event broker | **REJECT** | single-machine, single-director system; a broker is cosplay scale. FileChanged hook + daemon queue (PRD-08) is the event stream |
| GitHub/GitLab App webhooks | REJECT (defer) | local-first; git hooks + FileChanged cover the loop; webhook ingestion is a later remote mode |
| cloud embedders (text-embedding-3, voyage-code) | **REJECT** | INV-5: repo-resident models only; PRD-05 supplies on-device embedders |
| AST-guided chunking (structural boundaries, never token counts) | ADOPT | this is the load-bearing retrieval idea; chunk = function/class body |
| dedicated graph database engine | MODIFY | start sqlite (lgwks_sqlite/substrate_db exist); in-memory adjacency for traversal; a graph engine only if measured traversal latency demands it |

## Scope

- IN: parse → graph → query for repos on this machine; incremental update via daemon.
- IN: deterministic queries: full neighborhood (not top-k — parent U3 acceptance), callers,
  callees, importers, def-use, blame-to-contributor.
- IN: AST-guided chunk table feeding PRD-04 retrieval and PRD-05 embedding.
- OUT: review logic (PRD-09). OUT: ranking models (PRD-05). OUT: remote repos (defer).

## Builds on (candidates — verify surface at unit start)

`lgwks_codebase.py`, `lgwks_entity_graph.py`, `lgwks_graph.py`, `lgwks_repo.py`,
`lgwks_diff.py`, `lgwks_substrate_db.py`, `lgwks_sqlite.py` · tests/fixtures/crate (rust fixture exists).

## Contract

Emits `lgwks.codegraph.v1`: `{nodes[], edges[], chunks[]}` with stable node ids
(`<repo>:<path>:<kind>:<qualified_name>`). Query API: `neighborhood(node_id, depth)`,
`callers(fn)`, `chunk(node_id)`. Consumers: PRD-04, PRD-06, PRD-09.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 02-a parser slice | tree-sitter over THIS repo (python): File/Function/Class nodes + IMPORTS/CALLS edges; graph row-count + spot-check against grep ground truth on 20 known call sites; <60s full parse |
| 02-b incremental | edit one function → only its subtree re-parsed; graph diff is exactly that node's edges; proven by before/after dump |
| 02-c query surface | `neighborhood()` returns complete deterministic neighborhood (U3 acceptance); 0 false-missing on the 20-site ground truth |
| 02-d AST chunking | chunk table where every chunk is a complete structural unit; no chunk splits a function |
| 02-e LSP enrichment | type/reference edges from installed LSPs reconciled into graph; conflicts logged, AST wins on disagreement until measured otherwise |
| 02-f multi-language | rust (fixture crate) + ts; per-language conformance fixtures |

## Open questions → SCIENCE.md

Retrieval quality of AST chunks vs naive chunks (§4); when graph traversal needs an engine
beyond sqlite (measure, don't assume); CALLS edge precision in dynamic python (accept known
recall ceiling — document it, never fake it).
