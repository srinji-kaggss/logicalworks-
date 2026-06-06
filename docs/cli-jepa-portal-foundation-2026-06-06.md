# CLI JEPA Portal Foundation

Date: 2026-06-06  
Status: proposed foundation, first executable slice landing with `lgwks portal`

## Why

`lgwks` should stop treating natural language as the system of record.

Words are already compressed packets carrying:

- intent
- shared context
- entity references
- causal hints
- human framing noise

The job of the CLI membrane is not to "understand chat" directly. It is to:

1. ingest the raw view
2. separate signal from framing residue
3. align the view to local and global structure
4. emit a typed portal packet that coding agents can consume

The stable execution loop is:

```text
human dump
-> machine refine
-> deterministic graph / repo / ingest passes
-> typed portal packet
-> coding agent synthesis
-> deterministic verification
```

LLMs remain in the loop, but not as the first parser of reality.

## Design laws

1. Similarity is never a durable relation by itself.
2. Embedding/JEPA proximity proposes where to search, not what is true.
3. A relation is durable only after a typed path exists.
4. Raw human prose is an ingress format, not the ontology.
5. Every durable packet must preserve provenance and transformation path.

## Edge lifecycle

The graph must distinguish candidate structure from durable structure.

```text
soft edge     = proposed by similarity / JEPA / view proximity
search edge   = candidate under deterministic investigation
hard edge     = validated and typed by an explainable path
rejected edge = investigated and denied
```

Invariant:

```text
similarity(a, b) != relation(a, b)
relation(a, b) requires a typed support path
```

Typed support paths may come from:

- explicit import/call/dependency edges
- shared entity chain
- citation/evidence chain
- repeated cross-view confirmation
- repo/file/symbol binding

## Tranches

As active graph complexity rises, `lgwks` must force data into tranches instead of retrieving raw blobs.

- `repo_code`
- `project_intent`
- `external_research`
- `infra_machine`
- `math_stem`
- `human_framing`

The first executable CLI slice only builds `repo_code` + `project_intent`, but the schema must leave
space for all six.

## Portal packet

Portal packets are deterministic AI-facing context objects. They are not chat logs.

Shape:

```json
{
  "schema": "lgwks.portal.v1",
  "key": "portal:...",
  "project_key": "project:...",
  "repo": "/abs/path",
  "intent": "cleaned operator intent",
  "summary": "machine prose summary",
  "tranches": ["repo_code", "project_intent"],
  "candidate_files": [
    {"path": "lgwks_auth_runtime.py", "score": 0.92, "why": ["token_overlap", "graph_centrality"]}
  ],
  "relation_candidates": [
    {"source": "intent", "target": "lgwks_auth_runtime.py", "state": "search", "kind": "relevance"}
  ],
  "hard_edges": [
    {"source": "a.py", "target": "b.py", "kind": "import", "state": "hard"}
  ]
}
```

## OSS build-on-top call

Recommendation:

- Build the portal/compiler/machine membrane in `lgwks`.
- Treat `datalab-to` projects as optional ingestion backends, not as the substrate.

Product lesson from `datalab-to`:

- the wedge is not "we built a grand platform"
- the wedge is "one painful seam suddenly feels dramatically better"
- value arrives before ontology

For `lgwks`, the seam should be:

```text
messy human context now -> reliable code-grounded agent re-entry later
```

If that seam is great, the broader graph/global-db/product naturally earns usage. If that seam is weak,
the architecture does not matter.

Rationale:

- `datalab-to/marker`, `surya`, and related repos are strong at OCR/document extraction.
- They do not solve the typed portal packet, repo alignment, relation lifecycle, or coding-agent relay.
- They are a good future backend for multimodal/document ingress only.

Current call:

- keep `lgwks_extract` as the stable ingest seam
- later add optional adapters for:
  - `marker` for PDF -> markdown/JSON
  - `surya` for OCR/layout
  - `pdftext` for fast fallback

Do not make the CLI architecture depend on them.

## First hardening slice

Land a deterministic `portal` surface:

- `lgwks portal build`
- `lgwks portal show`
- `lgwks portal code`

The first slice must:

1. persist a portal packet under `.lgwks/portals/`
2. generate stable `project:` and `portal:` keys
3. rank likely repo files from local graph structure + intent tokens
4. expose relation candidates with explicit `search` state
5. keep real graph edges and candidate edges separate

This is intentionally narrower than the final multimodal vision, but it hardens the CLI around the
right ontology now instead of later.
