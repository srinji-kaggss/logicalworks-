# Targeted Gap Crawls

Use small crawls to answer specific missing pieces in the compiler research. Avoid giant crawls
that mostly produce vocabulary.

## JSON Extraction Mode

When a local LLM provider is configured for `crwl`, use:

```bash
/Users/srinji/.local/bin/crwl crawl "<url>" \
  --json-extract "Extract only gaps, executable anchors, and primitives relevant to the Logic 50-node compiler. Do not summarize the whole page." \
  --schema vision/research/machine-first-language/CRWL_GAP_SCHEMA.json \
  -o json \
  -O .crwl/gap-<slug>.json
```

If no provider is configured, crawl markdown and extract manually:

```bash
/Users/srinji/.local/bin/crwl crawl "<url>" -o markdown -O .crwl/gap-<slug>.md
```

## Crawl Axes

| Axis | Question | Example sources |
|---|---|---|
| `visual_node_ui` | What do block/node UIs already solve, and where do they fail? | Blockly, Node-RED, React Flow |
| `process_modeling` | How do business process standards bridge stakeholder diagrams to execution? | BPMN |
| `decision_modeling` | How are decisions separated from process flow? | DMN, decision tables |
| `schema_validation` | What can schemas validate and what cannot they express? | JSON Schema, SHACL |
| `state_machines` | How are states/transitions modeled visually and executably? | SCXML, XState/Stately |
| `build_graph` | How do build tools encode dependency truth? | Bazel, Buck, Pants |
| `agent_governance` | How do agent frameworks expose capability/tool boundaries? | MCP, OpenAI tools, LangGraph |
| `security_provenance` | How is generated code traced and trusted? | SLSA, Sigstore, in-toto |

## Done Criteria For A Gap Crawl

Each crawl should produce:

- one or more claims with source spans;
- one or more research gaps;
- candidate compiler primitives;
- an anti-dredging check;
- a verify-to-close action.

## First Gap Findings

Small crawls on 2026-05-31 suggest:

- Blockly validates the need for domain-specific blocks that generate code, but it mainly generates
  strings from blocks; our compiler needs typed graph semantics and audit evidence.
- Node-RED validates node/wire runtime flows, but its flow model is not enough for authority,
  compile-time ontology, or multi-swimlane decomposition.
- BPMN validates stakeholder-readable process diagrams precise enough to translate into software
  process components; our gap is executable authority/evidence per path.
- DMN validates separating decision dependencies from process flow and using executable expression
  logic; our gap is integrating decisions with graph chunk compilation.
- JSON Schema validates declarative structure and constraints; our gap is semantic relationships,
  authority, and state transitions beyond document shape.
- Statecharts validate deterministic states/transitions plus hierarchy/concurrency; our gap is
  combining statecharts with entity ownership, evidence, and projection generation.
