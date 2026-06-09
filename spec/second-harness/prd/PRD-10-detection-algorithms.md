# PRD-10 — Detection Algorithms (SAST + Fraud-Engine Scoring) — FINALIZED

Parent: doctrine "review is a production-grade gate" + PRD-09 review · Status: **v1.0 finalized · build spec** · 2026-06-09
Absorbs: [inputs/sast-engine-blueprints.json](inputs/sast-engine-blueprints.json) (7 frontier SAST blueprints, fully cited).
Builds on verified prior art: [lgwks_bot_code_hacker.py](../../../lgwks_bot_code_hacker.py) (575 lines, 5-layer analyzer).

## §0 What exists today (verified, not assumed)

`lgwks_bot_code_hacker.py` is a working 5-layer analyzer (read in full):
- **Layer 1** AST surface (H1 shell-exec, H2 file-mutation, H3 net-egress, H4 secret-logging)
- **Layer 2** intra-file taint (`TaintTracker`: source→sink, f-string/concat/dict, confidence)
- **Layer 3** composite risk (`RiskScore`: base + context_boost − history_penalty → severity)
- **Layer 4** baseline diffing (`Baseline`: sha256 fingerprint, dismiss-count suppression)
- **Layer 5** SARIF 2.1.0 export (`SARIFConverter` — GitHub/VS Code/GitLab ingestible)

Honest limits of the prior art (the frontier gap this PRD closes): **Python-only** (`ast.parse`),
**single-file / intra-procedural** (no cross-file, no call graph), **surface patterns only**
(no IFDS, no CFG dataflow, no value-range, no state machine). It already states it applies
"fraud-engine principles" — so "fraud detection" in the Director's ask = **the detection-engine
methodology** (multi-signal aggregation, context, FP-suppression, explainability, feedback),
not a separate financial module. No financial-fraud code exists in-repo (verified by grep).

**Defect spotted in prior art** (fix in 10-a): `_make` uses `datetime.now()` (`:263`) →
violates determinism doctrine (T4: no wall-clock in core). Findings should be reproducible;
timestamp belongs in the run envelope, not per-finding. `_finding_fingerprint` correctly
excludes it — so the fix is isolating `created_at` to the run header.

## §1 Thesis & frontier claim

One **detection substrate** serves all analyzers: a pluggable engine where each *pattern*
declares its (sources, sinks, propagators, sanitizers, traversal) and the shared Layers 3–5
(scoring, baseline, SARIF) are reused. The 7 research blueprints are the v1 pattern set; the
substrate is what makes adding the 8th cheap.

**Why this is frontier, not a Semgrep clone:**
1. **Owned + offline + deterministic.** No LLM, no cloud, fail-closed on parse error
   (prior art already). Semgrep/Snyk/Greptile are services; this is a forkable local engine.
2. **Fraud-engine scoring over binary rules.** Most SAST emits pass/fail per rule. This
   aggregates weak multi-signal evidence into a calibrated composite (Layer 3), with a
   reasoning chain per finding (explainability) and a learning baseline (feedback loop) —
   the architecture of a modern fraud engine (Stripe Radar / Sift) applied to code defects.
   That cross-domain transfer is the novel framing.
3. **Wired to the World-Graph (PRD-02).** Interprocedural/cross-file analysis rides the
   owned code graph instead of a bespoke call-graph builder — the `context_boost` in
   `RiskScore` becomes real blast-radius from graph neighborhoods (the `_graph` param in
   `run()` is already reserved for exactly this).
4. **Cited-to-source.** Every pattern's logic traces to a named paper/standard (the input
   JSON carries `_citation` on every field) — the analyzer is auditable to academia, which
   is the 100k-star bar.

## §2 The pattern contract (FINALIZED — the substrate seam)

Every detector conforms to one schema, distilled from the research JSON's structure:

```jsonc
{
  "pattern_id": "TAINT-001-SQL-INJECTION",          // stable id
  "taxonomy": "...",                                 // CWE-class description + citation
  "languages": ["python", "javascript"],             // tree-sitter grammars required
  "ast_spec":   { "node_types": [...], "transform": "..." },
  "traversal":  "intra | interprocedural-ifds | state-machine | value-range | config-match",
  "taint":      { "sources": [...], "sinks": [...], "propagators": [...], "sanitizers": [...] },
  "noise_heuristics": [ /* dedup, exact-match sanitizer, context filter */ ],
  "frameworks": [ { "context", "signature", "remediation" } ],
  "citations":  { /* every clause → URL, from the research JSON */ }
}
```

Emits `lgwks.detect.v1` finding (extends the existing `lgwks.bot.record.v1`):
`{pattern_id, file, range, severity, confidence, reasoning_chain[], evidence_spans[],
remediation, citation}`. Consumers: PRD-09 (review attenuation — linter-covered findings
suppressed), PRD-07 cockpit.

## §3 The v1 pattern set (the 7 blueprints — each cited, each with a build target)

| Pattern | Class | Traversal (from research) | Languages | Maps to prior art |
|---|---|---|---|---|
| **TAINT-001** SQL injection | CWE-89 | IFDS interprocedural taint, taint-mode sources→sinks, sanitizer exact-match | py, js | extends Layer-2 TaintTracker → interprocedural |
| **MEM-002** use-after-free | CWE-416 | state machine Allocated→Freed→UAF, alias tracking, loop-unroll-1 | c, cpp | new — pointer state, not in prior art |
| **CONC-003** race condition | CWE-362 | RacerX lockset + unlockset, z-test statistical, heuristic scoring | c, cpp, js | new — directly feeds Layer-3 scoring (z-test IS fraud-scoring) |
| **FW-004** Spring misconfig | CWE-1004/352/916 | config pattern-match vs secure thresholds (no dataflow) | java | new — closest to prior-art surface patterns |
| **JS-005** prototype pollution | CWE-1321 | ODG (Object Dependence Graph), flow+context-sensitive, branch-hybrid | js | new — needs object-graph, frontier |
| **ARITH-006** integer overflow | CWE-190 | interval/value-range analysis, taint + sensitive-use gating | c, cpp | new — value-range engine |
| **XSS-007** React dangerous HTML | CWE-79 | component-level taint, props/state→sink, protocol whitelist | js, jsx | extends Layer-2 to JSX |

Severity gating across all: a finding is high only when **tainted source ∧ feasible path ∧
sensitive sink** (the research's shared precision rule — ARITH-006's three-condition gate
generalizes). This is the FP-suppression discipline already in PRD-09.

## §4 Documentation requirement (the Director's explicit ask: how written, why, frontier)

Every pattern ships with a `references/PATTERN-<id>.md` carrying THREE mandatory sections —
this is a hard gate, not a nicety (it is the audit trail and the frontier evidence):
- **How it was written:** the algorithm in plain terms, the AST nodes, the traversal, the
  exact source→sink→sanitizer sets, with the research citation for each clause.
- **Why this way:** the design choice and what was rejected (e.g. "IFDS over naive
  reachability because cross-function sanitizers must be honored — TChecker CCS'22"); ties
  to the fraud-engine principle it embodies.
- **Why it's frontier:** the specific advance over Semgrep/CodeQL community rules (offline,
  cited, graph-wired, fraud-scored) + the benchmark result (SCIENCE §10).

## §5 Units & acceptance (build order — prior art first, then frontier patterns)

| Unit | Acceptance |
|---|---|
| 10-a substrate refactor | extract Layers 3–5 from `bot_code_hacker` into a reusable engine; pattern contract (§2) defined; existing H1–H4 re-expressed as patterns; determinism fix (`created_at` to run header); existing tests green |
| 10-b tree-sitter multi-lang | parse py/js/java/c via tree-sitter (shared with PRD-02 02-a); per-language fixture; no regression on python `ast` path |
| 10-c TAINT-001 interprocedural | SQL-injection across function boundaries using PRD-02 call graph; on a planted fixture (Django + Express): catches cross-function taint, honors sanitizer, dedups multi-path to one trace; FP rate measured on a clean corpus |
| 10-d MEM-002 + ARITH-006 | C/C++ state-machine UAF + value-range overflow; fixtures with planted + guarded cases; guarded code (NULL-check, overflow-check) NOT flagged (range refinement) |
| 10-e CONC-003 | lockset + z-test race detection; the z-test score feeds Layer-3 composite directly; benchmark on RacerX-style fixtures |
| 10-f JS-005 + XSS-007 | prototype-pollution (ODG) + React dangerouslySetInnerHTML taint; Express/React fixtures; sanitizer recognition (DOMPurify, hpp, banned-keys) |
| 10-g FW-004 | Spring config thresholds (token TTL, BCrypt strength, CSRF, hardcoded secret); dev-vs-prod profile context filter |
| 10-h SARIF + cockpit | all patterns emit SARIF 2.1.0 (prior art) + `lgwks.detect.v1`; findings flow to PRD-09 attenuation then PRD-07 cockpit |
| 10-i benchmark | on CORP-diffs (SCIENCE §3/§10): precision/recall per pattern; beats no-context baseline; FP rate target ≤ research-cited figures (TAINT-001: ≤2.1% per Cycode citation) reported honestly, not asserted |

## §6 How this fits the PRD family

PRD-10 is the analyzer **content**; PRD-09 is its **delivery discipline** (linter
subtraction, severity, exemplar grounding); PRD-02 is its **substrate** (graph for
interprocedural reach + tree-sitter parsing); PRD-05 is **optional** (a code-embedding tier
could rank finding similarity, but detection is deterministic by design — INV-4, models
never decide a vulnerability). The fraud-engine scoring (Layer 3) is the shared currency:
the same composite-risk + baseline-learning machinery is reusable for any future detector
(dependency risk, config drift) — that reuse is why it's a substrate, not a script.

RISK: the research blueprints describe algorithms at paper-grade (IFDS, ODG, VSA) that are
each a substantial engineering effort — a naive implementation that *claims* IFDS but does
shallow reachability would be the oversimplification sin wearing citations. The §4
documentation gate + §5-i benchmark against cited FP figures are the guard: a pattern ships
only when its measured precision matches the source it cites, or the gap is documented.
