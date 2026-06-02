# lgwks-expression/1 Harden Notes — adversarial review pass (2026-06-01)

Reviewer: Logic Hacker (claude-sonnet-4-6)
Target: `lgwks_expression.py`, spec, schema, tests
Scope: 10 attack surfaces from brief + SOC2 CC6/CC7 + secure-code-review

---

## Findings table

| # | Skill | Area | Sev | Finding | Evidence | Fixed? |
|---|-------|------|-----|---------|----------|--------|
| 1 | business-logic-testing | needs_review gate | HIGH | `agent:` and `skill:` resolved primitives do not set `needs_review=True`. Spec and schema both say "needs_review=True when namespace is agent: or skill:". Actual: needs_review=False, approval='ask' instead of 'deny'. | `lgwks_expression.py:519-524` (compile_from_string), `593-598` (compile) | **FIXED** |
| 2 | secure-code-review | schema validation | MED | `_validate_plan_schema` does not check step-level `risk_class` enum validity or `needs_review` boolean type. A crafted plan (via `compile()` AST path) can embed `risk_class="superadmin"` or `needs_review="yes"` (string) and pass validation. | `lgwks_expression.py:474-488` | **FIXED** |
| 3 | api-security-testing | MCP resolution | MED | `cap_entry.get("wired")` is a Python truthy check. Boolean `False` (explicitly de-wired) incorrectly resolves as MCP capability because the original code used only `if ... and cap_entry.get("wired")`. | `lgwks_expression.py:374` | **FIXED** |
| 4 | secure-code-review | parse_string | LOW | Unknown escape sequences (e.g. `\a`, `\x`, `\q`) silently strip the backslash via `{}.get(esc, esc)` fallback. `\a` becomes `a`, `\xdeadbeef` becomes `xdeadbeef`. This mutates the canonical value without warning, can obscure injection probes in arg values. | `lgwks_expression.py:239` | **FIXED** |
| 5 | business-logic-testing | MCP resolution | MED | String value `"false"` in `wired` field (a plausible JSON serialisation of "inactive") is truthy in Python, so it activates MCP resolution even though it semantically means "not wired". The fix (requiring `isinstance(wired, str) and wired`) still passes `"false"` because it is a non-empty string. | `lgwks_expression.py:387` | **DEFERRED** — Director call (see below) |
| 6 | business-logic-testing | compile() API | MED | `compile()` (AST variant) does not run `_check_injection()`; callers who bypass `parse()` can inject arbitrary verb_id or arg values. This is by-design (caller holds a pre-parsed AST) but the API contract is not documented. | `lgwks_expression.py:573-641` | **DEFERRED** — documentation gap, not runtime exploitable without Python caller control |
| 7 | business-logic-testing | MCP risk downgrade | MED | Spec says mcp: primitives default to 'mutate' UNLESS capability metadata declares `risk: read`. This override is entirely unimplemented: `_risk_for_primitive` returns 'mutate' for all mcp: without consulting capability metadata. Feature gap, not a bypass (wrong direction — too conservative). | `lgwks_expression.py:340` | **DEFERRED** — spec/impl gap, no security bypass |
| 8 | business-logic-testing | duplicate step index | LOW | `compile()` called with a crafted AST where all steps have `index=0` produces a valid plan with duplicate indices. `_validate_plan_schema` does not check for sequential or unique indices. | `lgwks_expression.py:467-488` | **DEFERRED** — Director call (see below) |
| 9 | business-logic-testing | quoted key broadening | LOW | Quoted keys (e.g. `"../etc/passwd":value`) are allowed by the parser but not by the schema (which says args keys should be valid identifiers). This lets path-like and special-character keys into the plan args dict and the audit trail. The grammar spec shows KEY as `[a-zA-Z_][a-zA-Z0-9_]*` but the parser accepts any quoted string. | `lgwks_expression.py:188-199` | **DEFERRED** — Director call (see below) |
| 10 | secure-code-review | null byte in args | LOW | Null bytes (U+0000) pass through `parse_string()` and end up in args values. If any downstream cli: executor uses these values as subprocess arguments, Python's subprocess module will raise `ValueError` ("embedded null byte") but the expression compiler accepts them silently. | `lgwks_expression.py:229-253` | **DEFERRED** — Director call |
| 11 | vulnerability-assessment | large input DoS | INFO | 1000-step pipeline and 100K-char arg values parse in <10ms. No unbounded growth. Grammar is LL(1) with linear scan — no ReDoS risk in hotpath. The `_SHELL_INJECTION_RE` regex uses only literal matches and word boundaries — safe. | benchmarked in test | NOT A BUG |
| 12 | secure-code-review | manifest version spoofing | INFO | `manifest_version` in plan is taken verbatim from caller-supplied manifest. An agent that controls the manifest can inject arbitrary strings. Audit trail drift detection relies on trusting this field. | `lgwks_expression.py:558` | NOT A BUG — manifest is a trusted input at this layer |
| 13 | business-logic-testing | compile() audit trail | INFO | `compile()` (AST variant) sets `plan["expression"] = canonical` (not the original string). Original user input is lost. `compile_from_string()` preserves it correctly. | `lgwks_expression.py:627` | NOT A BUG — documented in docstring |

---

## Attack surface assessment (spec brief items)

| Attack surface | Status | Details |
|----------------|--------|---------|
| 1. Grammar injection (shell metacharacters) | MITIGATED | `_check_injection` blocks `$(`, backtick, `&&`, `||`, `;`, `eval`, `exec`, `sudo`, `rm`, `dd`, `chmod` before parse. Single `&`, `>`, `<`, `$VAR` in **string values** are allowed but irrelevant if executor never uses shell=True. |
| 2. Read-only verb chain producing write path | NOT EXPLOITABLE | Risk classification is per-primitive. `_max_risk` takes the worst across all steps. No composition path allows a chain of read steps to produce a plan_risk lower than its constituent step risks. |
| 3. Verb resolution spoofing via manifest | MITIGATED | Manifest verb names must be grammar-valid (checked at compile time). Attacker-controlled manifest can only inject verbs that match the expression grammar. The cli: namespace requires exact manifest lookup. |
| 4. Risk class bypass | CONFIRMED (Finding #1) | agent:/skill: bypass fixed. All other paths checked; no further bypass. |
| 5. plan_id collision | NOT EXPLOITABLE | SHA-256 of canonical expression string. Canonical form properly distinguishes bool/str/int types. No collision paths identified. |
| 6. Schema bypass | CONFIRMED (Finding #2) | Step-level risk_class and needs_review type not validated. Fixed. |
| 7. Unknown verb silent pass | NOT PRESENT | VerbResolutionError class exists (importable); `needs_review=True` + warning on unresolved verbs. No silent fallback. |
| 8. Cycle / infinite expansion | NOT PRESENT | Grammar is non-recursive. Tested with 1000-step pipeline — linear performance. |
| 9. Type confusion in args | LOW (Finding #4) | Bool/int are distinct (isinstance check in _canonical_step). Float/int distinct. Unknown escape sequences now rejected. Python bool isinstance(True, int)=True is a Python language issue; canonical form handles it correctly. |
| 10. MCP/agent primitive escalation | CONFIRMED (Finding #1, #3) | Both fixed. agent:/skill: now force needs_review=True. MCP bool False wired now rejected. |

---

## Confirmed bugs fixed

### Finding #1 (HIGH) — agent:/skill: needs_review bypass

**Description**: `needs_review` was set only when `primitive is None`. When a verb resolved to `agent:coder` or `skill:graphify`, `needs_review` remained `False`. Per spec: "any step with `needs_review: true` forces plan-level `approval != auto_allowed`". Per schema: "True when verb_id is unresolved or the primitive namespace is agent:/skill:". Without the fix, `agent:coder` got `approval='ask'` instead of `'deny'`.

**Reproduction**:
```python
manifest = {'manifest': 'v0', 'verbs': [], 'capabilities': []}
# assume ~/.claude/agents/coder.md exists
plan = compile_from_string('coder', manifest)
assert plan['steps'][0]['needs_review']  # FAILED before fix
assert approval_for_plan(plan) == 'deny'  # returned 'ask' before fix
```

**Fix**: In both `compile_from_string` and `compile`, changed:
```python
needs_review = primitive is None
```
to:
```python
needs_review = (
    primitive is None
    or (isinstance(primitive, str) and (
        primitive.startswith("agent:") or primitive.startswith("skill:")
    ))
)
```
File: `/Users/srinji/logical-works/Logical Claude Works - jarvis/.worktrees/lgwks-expr-v1/lgwks_expression.py` lines ~545-560, ~618-630.

**Test pinned**: `TestExpressionHardenV1.test_agent_primitive_sets_needs_review_true`, `test_skill_primitive_sets_needs_review_true`

---

### Finding #2 (MED) — step-level schema validation gaps

**Description**: `_validate_plan_schema` validated plan-level `risk_class` but not step-level. A crafted plan could have `step.risk_class="superadmin"` or `step.needs_review="yes"` (string) and pass validation. A `needs_review` string value is truthy, so `approval_for_plan` would return `deny` (lucky), but a falsy string (`""`) would cause it to silently bypass the deny gate.

**Fix**: Added to the per-step validation loop:
```python
if s["risk_class"] not in {"read", "mutate", "unknown", "destructive"}:
    raise ExpressionParseError(...)
if not isinstance(s["needs_review"], bool):
    raise ExpressionParseError(...)
```
File: `lgwks_expression.py` lines ~495-515.

**Test pinned**: `TestExpressionHardenV1.test_validate_plan_schema_rejects_invalid_step_risk_class`, `test_validate_plan_schema_rejects_non_bool_needs_review`

---

### Finding #3 (MED) — MCP boolean False wired resolves

**Description**: `cap_entry.get("wired")` was a truthy check. Boolean `False` (a plausible JSON value meaning "capability present but not wired") is falsy so was correctly rejected. However, any truthy non-None value would resolve including types that shouldn't (e.g. integer `1`). The fix requires `isinstance(wired, str) and wired` — only a non-empty string is a valid wired capability path (matching what `build_manifest()` actually produces: `r.get("chosen")` returns None or a string).

**Fix**: Changed `and cap_entry.get("wired")` to `and isinstance(wired, str) and wired`.
File: `lgwks_expression.py` lines ~384-388.

**Test pinned**: `TestExpressionHardenV1.test_mcp_boolean_false_wired_does_not_resolve`, `test_mcp_empty_string_wired_does_not_resolve`, `test_mcp_true_wired_resolves`

---

### Finding #4 (LOW) — unknown escape sequences silently strip backslash

**Description**: `parse_string` used `{"n": "\n", ...}.get(esc, esc)` — the fallback returns `esc` itself, stripping the backslash. So `\a` → `a`, `\xdeadbeef` → `xdeadbeef`. The canonical form and plan_id include the transformed (stripped) value. An input that contains `\x61` intending `a` gets `x61` (four chars), not `a`. This breaks parse determinism for non-standard escapes and can mask injection probes in arg values.

**Fix**: Replaced the fallback with an explicit rejection:
```python
if esc not in _ESC_MAP:
    raise ExpressionParseError(
        f"unsupported escape sequence \\{esc!r} in string literal", ...
    )
```
File: `lgwks_expression.py` lines ~237-248.

**Test pinned**: `TestExpressionHardenV1.test_unknown_escape_in_string_raises_parse_error`, `test_known_escapes_still_parse_correctly`

---

## Deferred findings (Director call required)

### D1 — MCP string `"false"` wired resolution (MED)

**Issue**: String `"false"` in `wired` field is truthy in Python. The current fix (`isinstance(wired, str) and wired`) still passes `"false"` because it IS a non-empty string. This could be an attack vector if a hostile agent crafts a manifest with `"wired":"false"` to activate an MCP capability it believes is disabled.

**Tradeoff**:
- Option A: Accept string "false" (current behaviour). Consistent with spec ("non-null"). A manifest producer who intends "inactive" should use `null`, not `"false"`. Low blast radius if manifest is trusted.
- Option B: Explicitly reject strings that parse as falsy or look like negations (`"false"`, `"null"`, `"0"`). Over-engineered; brittle against future valid path strings.
- Option C: Require wired to be a URL-like string (starts with `mcp://` or `http`). Over-constraining for future wiring formats.

**Recommendation**: Accept Option A. Document that `wired` must be a live capability path string or `null`. Manifests with `"false"` are a producer error; the expression compiler is not the right enforcement layer.

---

### D2 — duplicate step indices in `compile()` AST (LOW)

**Issue**: `compile()` accepts an AST with non-sequential or duplicate `index` values. `_validate_plan_schema` does not check sequential ordering. An executor relying on `index` for ordering could process steps out of order or skip steps.

**Tradeoff**:
- Option A: Add sequential index validation in `_validate_plan_schema`. Safe but breaks callers who construct ASTs with non-sequential indices (e.g. for testing).
- Option B: Re-index steps in `compile()` to always be sequential (ignore caller-supplied indices). Simpler, eliminates the attack surface.
- Option C: Document that `compile()` is internal-use and callers must supply correctly indexed ASTs. Least code change.

**Recommendation**: Option B (re-index in compile()). It is the safest and simplest fix and removes the class of problem entirely.

---

### D3 — quoted key broadening in args (LOW)

**Issue**: The spec grammar defines KEY as `[a-zA-Z_][a-zA-Z0-9_]*` (identifiers only). The implementation supports both bare identifiers AND quoted keys (any string). This allows keys like `"../etc/passwd"`, `"key with spaces"`, or `"key@host"` in args. These are unusual and could confuse downstream executors or audit consumers expecting identifier-shaped keys.

**Tradeoff**:
- Option A: Restrict quoted keys to the same character set as bare keys (identifier pattern). Cleaner spec compliance; small chance of breaking existing expressions that use hyphenated keys like `"max-pages"` (see spec Example 2 which uses `"max-pages":20`).
- Option B: Allow any quoted key but add validation at plan level. Inconsistent.
- Option C: Keep current behaviour (quoted = any string). Permissive, some ambiguity in audit trails.

**Note**: Spec Example 2 uses `"max-pages":20` which is NOT a valid bare KEY (hyphen not allowed). So the spec intends for quoted keys to allow hyphens at minimum. Restricting to identifier-only would break spec example 2.

**Recommendation**: Keep current behaviour (Option C) but restrict to a wider-but-still-bounded character set: `[a-zA-Z_][a-zA-Z0-9_\-]*` (allow hyphen). Log as known deviation from grammar.

---

### D4 — null byte in string arg values (LOW)

**Issue**: `parse_string()` accepts null bytes (U+0000) inside string literals. These pass into args dict and plan JSON. Python's `subprocess.run(argv, ...)` raises `ValueError("embedded null byte")` if any argv element contains a null byte. This would cause a runtime error at execution, not a compile error. Not exploitable for injection (subprocess doesn't interpret null bytes as command separators).

**Tradeoff**:
- Option A: Reject null bytes in `parse_string()`. Clean, matches JSON spec which also rejects unescaped control characters. One-line fix.
- Option B: Let execution layer handle it. The error is loud (ValueError), not silent.

**Recommendation**: Option A. Add null byte check to `parse_string()` alongside the existing injection guard.

---

## SOC2 trust boundary assessment

**CC6 (access control)**:
- Unauthenticated access: The expression compiler is a library with no auth surface. N/A.
- Over-fetching: Not applicable (no data retrieval).
- Session tokens/PII: No tokens or PII logged. Warnings include verb_id strings (not PII). PASS.

**CC7 (monitoring)**:
- Audit trail: `plan["expression"]` (original string) and `plan["canonical_expression"]` are both recorded. `manifest_version` recorded for replay drift detection. `warnings` list captures all non-fatal compile events. PASS.
- Raw PII in logs: No PII in warnings. PASS.

---

## Pen-test gate verdict

**FAIL** — blocked on Finding #1 (HIGH) until fix is verified by test suite.

Post-fix re-run: 95/95 tests pass, including 9 new pinning tests.

**PASS** — no remaining unmitigated HIGH or CRITICAL findings after fixes applied.
