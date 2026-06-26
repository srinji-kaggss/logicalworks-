---
type: Spec
title: lgwks-expression/1 Specification
description: A foreign AI holding lgwks manifest has a capability surface but no composition
tags: [spec]
timestamp: 2026-06-06T02:26:14-04:00
---

# lgwks-expression/1 Specification

## L0 Intent

A foreign AI holding `lgwks manifest` has a capability surface but no composition
primitive — it can name verbs but cannot describe a multi-step workflow as a
single typed artifact that another agent can validate, hash, preview, and approve
before a byte executes. `lgwks-expression/1` defines a compact, human-typeable
expression string that encodes a directed capability pipeline: verbs are agnostic
IDs resolved through the live manifest at dispatch time (never bash paths), edges
carry typed I/O contracts, the compiled plan is content-addressed (same expression
→ same plan_id), and the whole artifact is self-describing enough that any agent
with `lgwks manifest` can reproduce the compilation from scratch.

---

## Grammar (PEG)

```peg
expression   <- pipeline EOF
pipeline     <- step (PIPE step)*
step         <- verb_id args?
verb_id      <- SEGMENT (DOT SEGMENT)*          # e.g. "research", "embed.local", "store.vault"
args         <- LBRACKET kv_list RBRACKET
kv_list      <- kv (COMMA kv)*
kv           <- KEY COLON value
value        <- STRING | NUMBER | BOOL | NULL
STRING       <- '"' [^"]* '"'
NUMBER       <- '-'? [0-9]+ ('.' [0-9]+)?
BOOL         <- 'true' | 'false'
NULL         <- 'null'
KEY          <- [a-zA-Z_][a-zA-Z0-9_]*
SEGMENT      <- [a-z][a-z0-9_]*
PIPE         <- ' | '                            # single space on each side, exactly
LBRACKET     <- '['
RBRACKET     <- ']'
COLON        <- ':'
COMMA        <- ','
DOT          <- '.'
EOF          <- !.
```

// why PEG not EBNF: PEG is unambiguous by construction (ordered choice, no
// lookahead ambiguity), implementable without a parser combinator library in
// ~200 lines of recursive-descent Python, and the grammar stays deterministic
// even if a future verb_id segment collides with a keyword.

// why PIPE uses padded spaces: the expression is human-typeable; unpadded `|`
// would conflict with shell pipe interpretation when the expression is passed
// unquoted. Padded `' | '` is a single unambiguous delimiter that survives
// shell quoting conventions.

---

## Type System

Each step declares an `input_schema` and `output_schema` as JSON Schema
fragments. The compiler checks that the output_schema of step N is compatible
with the input_schema of step N+1 (structural subtype: every required field in
the downstream input_schema must appear in the upstream output_schema with a
compatible type). Incompatibility is a compile error, not a runtime error.

Built-in schema atoms:
```
text     ::= {"type": "string"}
blob     ::= {"type": "string", "contentEncoding": "base64"}
record   ::= {"type": "object", "additionalProperties": true}
records  ::= {"type": "array", "items": {"type": "object"}}
void     ::= {"type": "null"}
any      ::= {}
```

Verb metadata in the manifest carries `input_schema` and `output_schema` keys
(JSON Schema fragments). When absent, the compiler defaults both to `any` and
emits a `schema_unknown` warning (not an error) so unknown-schema verbs can
still be composed while the gap is visible.

// why structural subtype not nominal: verb implementations change; a nominal
// type ID ties the spec to an implementation name, which drifts. Structural
// compatibility survives verb reimplementation as long as the shape is
// compatible.

---

## Verb Resolution Protocol

Verb IDs are agnostic dot-delimited tokens, never bash paths or tool names.
Resolution runs at compile time against the live manifest, in priority order:

1. **cli:** — the verb_id matches a manifest verb name (space → dot in
   expression; "geo.compile" resolves to cli verb "geo compile").
2. **mcp:** — the manifest `capabilities` list contains an entry whose
   `capability` key matches the verb_id and `wired` is a live non-empty string.
   Negation markers like `"false"`, `"0"`, `"null"`, `"off"` are treated as
   unwired so hostile or buggy manifests fail closed.
3. **skill:** — a global skill registered under `~/.claude/skills/<verb_id>/`
   with a `SKILL.md` descriptor.
4. **agent:** — the verb_id matches a role agent under `~/.claude/agents/`.

The first match wins. Unresolved verb_ids compile to `primitive: null` with
`needs_review: true` — they appear in the plan but block auto execution
(mirrors geo compiler policy for unknown verbs).

The resolved primitive is recorded in the plan as a `PrimitiveRef`:
`"cli:geo compile"`, `"mcp:embed"`, `"skill:graphify"`, `"agent:coder"`.

// why priority cli > mcp > skill > agent: cli verbs are the most constrained
// (argv, no shell, deterministic); the progression toward agent is the
// progression toward less-bounded execution. Safer primitives win ties.

---

## Risk Classification

Risk classes (ordered): `read` < `mutate` < `unknown` < `destructive`.

Each step inherits its risk class from the resolved primitive:
- `cli:` primitives use the existing `_classify()` heuristic from `lgwks_multiply`.
- `mcp:` primitives default to `mutate` unless the capability metadata declares
  `risk: read` (conservative default; external call with side-effects unknown).
- `skill:` primitives default to `unknown`.
- `agent:` primitives default to `unknown`.
- Unresolved (`null`) primitives: `unknown`.

The plan-level `risk_class` is the maximum across all steps.

Approval matrix (mirrors geo compiler):
- `read` + all steps resolved → `auto_allowed`
- `mutate` or `unknown` → `ask`
- `destructive` or any step has `needs_review: true` → `deny`

// why reuse _classify not re-declare: two drifting risk classifiers is worse
// than one imperfect one. The geo compiler already established this principle.

---

## Content-Addressing

The plan_id is the SHA-256 of the canonical expression string, encoded as
lowercase hex. Canonicalisation rules:

1. Normalise whitespace: collapse runs to single space, strip leading/trailing.
2. Sort each step's args by key (lexicographic).
3. Lowercase the entire verb_id chain.

```
plan_id = sha256(canonical_expression_string).hexdigest()
```

Same canonical expression → same plan_id, regardless of whitespace variation or
arg ordering in the source string. This makes plan_id a stable reference for
caching, deduplication, and audit trails.

When compiling a pre-parsed AST, the compiler reindexes steps sequentially
(`0..N-1`) before validation. Caller-supplied indices are treated as advisory,
not authoritative.

// why hash the expression string not the compiled plan object: the compiled
// plan contains resolved primitives that vary across machines (different
// capability wiring). Hashing the expression gives a portable, machine-agnostic
// plan_id. Two agents on different machines compile the same expression to
// different primitives but the same plan_id — the ID names the intent, not
// the execution.

---

## Plan Object Shape

The compiled plan follows schema `lgwks-expression/1`:

```json
{
  "schema": "lgwks-expression/1",
  "plan_id": "<sha256-hex>",
  "expression": "<original expression string>",
  "canonical_expression": "<normalised expression string>",
  "manifest_version": "<lgwks.manifest.v0>",
  "steps": [
    {
      "index": 0,
      "verb_id": "extract",
      "resolved_primitive": "cli:extract",
      "args": {"target": "https://example.com"},
      "input_schema": {},
      "output_schema": {"type": "string"},
      "risk_class": "read",
      "needs_review": false
    }
  ],
  "risk_class": "read",
  "compile_policy": {
    "shell": false,
    "unknown_requires_review": true,
    "destructive_requires_force": true
  },
  "warnings": []
}
```

`warnings` is a list of strings for non-fatal compile conditions
(`schema_unknown`, `primitive_unresolved`, etc.). An agent must treat any step
with `needs_review: true` as blocked; it may not auto-execute.

---

## Integration Points

### geo compile / geo preview / geo run
`lgwks-expression/1` operates at a higher abstraction than `lgwks-geoexpr/1`.
A GeoExpr is a cartesian product of axis values; an expression is a directed
pipeline of typed verb invocations. The two are composable: an expression step
with verb_id `geo.compile` accepts a GeoExpr JSON on its input edge and emits
a CommandPlan on its output edge. They are not the same layer.

### lgwks x
`lgwks x` expands brace expressions into shell command chains. An
`lgwks-expression/1` pipeline that resolves entirely to `cli:` primitives can
be lowered to an `lgwks x` invocation for backward compatibility. The lowering
is one-way (x → expression is not definable because x has no typed I/O).

### lgwks preview
`lgwks preview <expr>` compiles the expression, classifies risk, and emits the
plan JSON without executing. Mirrors `geo preview` semantics.

### lgwks manifest
The manifest is the resolver's source of truth. The expression compiler calls
`build_manifest()` at compile time to resolve verb IDs. The plan records
`manifest_version` so replay can detect resolver drift.

---

## Examples

### Example 1 — Single read step
```
extract["target":"https://arxiv.org/abs/2401.00001"]
```
```json
{
  "schema": "lgwks-expression/1",
  "plan_id": "a3f2...c1",
  "expression": "extract[\"target\":\"https://arxiv.org/abs/2401.00001\"]",
  "steps": [
    {"index":0,"verb_id":"extract","resolved_primitive":"cli:extract",
     "args":{"target":"https://arxiv.org/abs/2401.00001"},
     "input_schema":{},"output_schema":{"type":"string"},
     "risk_class":"read","needs_review":false}
  ],
  "risk_class": "read"
}
```

### Example 2 — Two-step pipeline: crawl then embed
```
jarvis.crawl["source":"https://openai.com","max-pages":20] | embed["project":"openai-research"]
```
```json
{
  "steps": [
    {"index":0,"verb_id":"jarvis.crawl","resolved_primitive":"cli:jarvis crawl",
     "args":{"source":"https://openai.com","max-pages":20},
     "risk_class":"read","needs_review":false},
    {"index":1,"verb_id":"embed","resolved_primitive":"cli:embed",
     "args":{"project":"openai-research"},
     "risk_class":"read","needs_review":false}
  ],
  "risk_class": "read"
}
```

### Example 3 — Research pipeline with memory
```
public["query":"causal inference 2024","limit":10] | memory.remember["project":"research-q1"]
```
```json
{
  "steps": [
    {"index":0,"verb_id":"public","resolved_primitive":"cli:public",
     "args":{"query":"causal inference 2024","limit":10},
     "risk_class":"read","needs_review":false},
    {"index":1,"verb_id":"memory.remember","resolved_primitive":"cli:memory remember",
     "args":{"project":"research-q1"},
     "risk_class":"mutate","needs_review":false}
  ],
  "risk_class": "mutate",
  "compile_policy": {"shell":false,"unknown_requires_review":true,"destructive_requires_force":true}
}
```
Approval: `ask` (mutate step present).

### Example 4 — Unresolved verb (foreign AI capability)
```
reason["query":"summarise findings"] | store["project":"q1"]
```
```json
{
  "steps": [
    {"index":0,"verb_id":"reason","resolved_primitive":null,
     "args":{"query":"summarise findings"},
     "risk_class":"unknown","needs_review":true},
    {"index":1,"verb_id":"store","resolved_primitive":"cli:store",
     "args":{"project":"q1"},
     "risk_class":"read","needs_review":false}
  ],
  "risk_class": "unknown",
  "warnings": ["step 0: verb_id 'reason' unresolved; needs_review=true"]
}
```

### Example 5 — Geo compile as a pipeline step
```
geo.compile | geo.preview
```
```json
{
  "steps": [
    {"index":0,"verb_id":"geo.compile","resolved_primitive":"cli:geo compile",
     "input_schema":{},"output_schema":{"type":"object","title":"CommandPlan"},
     "risk_class":"read","needs_review":false},
    {"index":1,"verb_id":"geo.preview","resolved_primitive":"cli:geo preview",
     "input_schema":{"type":"object","title":"CommandPlan"},
     "output_schema":{"type":"object","title":"HumanPreview"},
     "risk_class":"read","needs_review":false}
  ],
  "risk_class": "read"
}
```

---

## Invariants

The following must hold for the spec to be trustworthy. Each is machine-checkable
in the test suite.

1. **Determinism**: `compile(expr) == compile(expr)` for any expression string on
   the same manifest. Same canonical_expression → same plan_id.
2. **No shell execution**: no step in a compiled plan ever passes through a shell
   interpreter. `compile_policy.shell` must be `false`.
3. **Risk monotonicity**: `plan.risk_class == max(step.risk_class for step in steps)`.
4. **Needs-review blocks auto-execute**: any step with `needs_review: true` forces
   plan-level `approval != auto_allowed`.
5. **Manifest version recorded**: `manifest_version` in every plan matches the
   `manifest` field returned by `build_manifest()` at compile time.
6. **plan_id is expression-derived**: `plan_id == sha256(canonical_expression)`;
   it does not change if the manifest changes (portability invariant).
7. **Pipeline type compatibility**: for each adjacent step pair (N, N+1), the
   output_schema of N is structurally compatible with input_schema of N+1, or
   either schema is `any` (`{}`).
8. **Grammar completeness**: every valid expression string parses without error;
   every parse error names the failing position and token.
