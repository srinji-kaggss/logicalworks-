# Handoff — Expression Hardening Follow-Through

**Date:** 2026-06-06  
**Worktree:** `../logicalworks-hardening`  
**Branch:** `codex/hardening-lgwks-20260606`

## What changed

Follow-through hardening landed in the expression compiler and manifest surface:

- `lgwks_expression.py`
  - rejects literal null bytes in string args at parse time
  - reindexes `compile()` AST steps to canonical sequential indices
  - rejects non-sequential step indices during plan validation
  - implements MCP `risk: read` override instead of forcing all MCP steps to `mutate`
  - hardens MCP resolution so negation-like `wired` strings (`"false"`, `"0"`, `"null"`, `"off"`, etc.) do not activate a capability
- `lgwks_capabilities.py`
  - capabilities now surface explicit `risk` metadata
- `lgwks_manifest.py`
  - manifest capabilities/tools now include that `risk` field
- `docs/lgwks-expression-v1-spec.md`
  - updated to match the hardened MCP wiring semantics and AST reindexing behavior
- `tests/test_research_stack.py`
  - added regressions for null-byte rejection, sequential index enforcement, MCP negation-string wiring rejection, and MCP `risk: read` downgrade

## Verification

- `python3 -m unittest tests.test_research_stack -q`
- `python3 -m unittest tests.test_repo tests.test_graph_rust tests.test_gh -q`

Both passed in this worktree.

## Independent feedback

These are the notable review conclusions after reading code + spec directly instead of trusting the prior handoff:

1. The prior hardening note treated `wired="false"` as a director call. The code comment already claimed that case was blocked, but the implementation did not actually do it. That mismatch was worse than either policy choice on its own, so I fixed the behavior and updated the spec.
2. The spec already promised MCP `risk: read` downgrade support, but the runtime had no path to carry capability risk metadata from resolver → manifest → compiler. This was a real contract drift, not just a deferred enhancement.
3. Reindexing in `compile()` was necessary, but validation also needed to reject non-sequential indices. Otherwise any external caller constructing a plan dict could still smuggle duplicate indices past `_validate_plan_schema`.
4. Null-byte rejection belongs in the compiler, not only in subprocess callers. Deferring that check to execution creates avoidable late failures and weakens the typed-artifact boundary.

## Residuals

- `compile()` still trusts caller-supplied AST strings beyond schema shape; it does not rerun `_check_injection()` because that path is still an internal/pre-parsed API.
- Quoted arg-key broadening remains permissive. The spec examples require at least hyphenated quoted keys, but the grammar text is still narrower than implementation reality.
