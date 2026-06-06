"""
lgwks_expression -- lgwks-expression/1 parser and resolver.

Expression strings encode directed capability pipelines: verb invocations
composed with ' | ', args in [] brackets, compiled to a typed plan that can be
validated, hashed, and approved before any execution occurs.

Grammar (from spec):
  expression <- pipeline EOF
  pipeline   <- step (' | ' step)*
  step       <- verb_id ('[' kv_list ']')?
  verb_id    <- SEGMENT ('.' SEGMENT)*
  kv_list    <- kv (',' kv)*
  kv         <- KEY ':' value
  value      <- STRING | NUMBER | BOOL | NULL

# //why recursive-descent not a parser library: stdlib only per spec constraint;
# // the grammar is LL(1) so a hand-written parser is ~120 lines and unambiguous.
# //why PEG-style: ordered choice means no ambiguity even if a future verb_id
# // segment collides with a keyword (true | false | null are matched inside
# // value position only, never as SEGMENT tokens).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class ExpressionParseError(ValueError):
    """Raised on invalid expression syntax. Always includes position and token."""

    def __init__(self, message: str, pos: int = -1, token: str = ""):
        detail = f"{message} (pos={pos}, near={token!r})" if pos >= 0 else message
        super().__init__(detail)
        self.pos = pos
        self.token = token


class VerbResolutionError(LookupError):
    """Raised when a required verb_id cannot be resolved and strict mode is requested."""
    pass


# ---------------------------------------------------------------------------
# AST types
# ---------------------------------------------------------------------------

# ExprAST is a list of step dicts. Using dicts (not dataclasses) keeps
# everything JSON-serialisable from the start with no import burden on callers.

def _make_step(verb_id: str, args: dict, index: int) -> dict:
    return {"verb_id": verb_id, "args": args, "index": index, "metadata": {}}


ExprAST = list  # list[dict] returned by parse()


# ---------------------------------------------------------------------------
# Shell injection guard
# ---------------------------------------------------------------------------

# //why block at parse time not at execution: the expression is a typed artifact;
# presence of shell metacharacters means it was not produced by the grammar
# and is either malformed or adversarial input. Reject early with a clear error.
_SHELL_INJECTION_RE = re.compile(
    r"\$\(|`|\beval\b|\bexec\b|&&|\|\||;|\bsudo\b|\brm\b|\bdd\b|\bchmod\b"
)


def _check_injection(expr: str) -> None:
    m = _SHELL_INJECTION_RE.search(expr)
    if m:
        raise ExpressionParseError(
            "expression contains shell injection pattern",
            pos=m.start(),
            token=expr[m.start(): m.start() + 12],
        )


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

# Allowed characters for a SEGMENT token (verb_id component).
_SEGMENT_RE = re.compile(r"[a-z][a-z0-9_]*")
# KEY is slightly broader -- allows uppercase and underscore.
_KEY_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_VALID_RISKS = {"read", "mutate", "unknown", "destructive"}
_NEGATION_STRINGS = {"0", "false", "no", "none", "null", "off", "disabled"}


class _Parser:
    """Single-pass recursive-descent parser over an expression string."""

    def __init__(self, src: str):
        self._src = src
        self._pos = 0

    # -- low-level helpers ---------------------------------------------------

    def _peek(self) -> str:
        return self._src[self._pos] if self._pos < len(self._src) else ""

    def _rest(self) -> str:
        return self._src[self._pos:]

    def _advance(self, n: int = 1) -> str:
        chunk = self._src[self._pos: self._pos + n]
        self._pos += n
        return chunk

    def _expect(self, literal: str) -> None:
        if not self._rest().startswith(literal):
            raise ExpressionParseError(
                f"expected {literal!r}",
                pos=self._pos,
                token=self._rest()[:16],
            )
        self._pos += len(literal)

    # -- grammar productions -------------------------------------------------

    def parse_pipeline(self) -> ExprAST:
        steps: ExprAST = []
        steps.append(self.parse_step(len(steps)))
        # PIPE is exactly ' | ' (space-pipe-space) per spec.
        while self._rest().startswith(" | "):
            self._pos += 3  # consume ' | '
            steps.append(self.parse_step(len(steps)))
        if self._pos != len(self._src):
            raise ExpressionParseError(
                "unexpected trailing content",
                pos=self._pos,
                token=self._rest()[:16],
            )
        return steps

    def parse_step(self, index: int) -> dict:
        verb_id = self.parse_verb_id()
        args: dict = {}
        if self._peek() == "[":
            self._advance()  # consume '['
            args = self.parse_kv_list()
            self._expect("]")
        return _make_step(verb_id, args, index)

    def parse_verb_id(self) -> str:
        # verb_id ::= SEGMENT ('.' SEGMENT)*
        m = _SEGMENT_RE.match(self._src, self._pos)
        if not m:
            raise ExpressionParseError(
                "expected verb_id (lowercase letter + alphanumeric/underscore segments)",
                pos=self._pos,
                token=self._rest()[:16],
            )
        self._pos = m.end()
        segments = [m.group()]
        # Greedily consume '.SEGMENT' as long as they immediately follow.
        while self._peek() == "." and _SEGMENT_RE.match(self._src, self._pos + 1):
            self._pos += 1  # consume '.'
            m2 = _SEGMENT_RE.match(self._src, self._pos)
            assert m2 is not None  # //why: while condition checked same pos; guaranteed non-None
            self._pos = m2.end()
            segments.append(m2.group())
        return ".".join(segments)

    def parse_kv_list(self) -> dict:
        kv: dict = {}
        key, val = self.parse_kv()
        kv[key] = val
        while self._peek() == ",":
            self._advance()  # consume ','
            key, val = self.parse_kv()
            kv[key] = val
        return kv

    def parse_kv(self) -> tuple:
        # KEY may be either a quoted string ("max-pages") or a bare identifier (limit).
        # The spec grammar shows KEY as a bare identifier but the spec examples use
        # quoted keys consistently (e.g. "target":"url", "max-pages":20). Support both
        # so the parser handles all spec examples without rejection.
        if self._peek() == '"':
            key = self.parse_string()
        else:
            m = _KEY_RE.match(self._src, self._pos)
            if not m:
                raise ExpressionParseError(
                    "expected key (letter/underscore start, or quoted string)",
                    pos=self._pos,
                    token=self._rest()[:16],
                )
            key = m.group()
            self._pos = m.end()
        self._expect(":")
        val = self.parse_value()
        return key, val

    def parse_value(self) -> Any:
        rest = self._rest()
        if rest.startswith('"'):
            return self.parse_string()
        if rest.startswith("true"):
            self._pos += 4
            return True
        if rest.startswith("false"):
            self._pos += 5
            return False
        if rest.startswith("null"):
            self._pos += 4
            return None
        # NUMBER: optional '-', digits, optional decimal.
        m = re.match(r"-?\d+(?:\.\d+)?", rest)
        if m:
            raw = m.group()
            self._pos += len(raw)
            return float(raw) if "." in raw else int(raw)
        raise ExpressionParseError(
            "expected value (string, number, bool, null)",
            pos=self._pos,
            token=rest[:16],
        )

    def parse_string(self) -> str:
        self._expect('"')
        buf: list[str] = []
        while self._pos < len(self._src) and self._src[self._pos] != '"':
            ch = self._src[self._pos]
            if ch == "\\":
                self._pos += 1
                esc = self._src[self._pos] if self._pos < len(self._src) else ""
                # Basic JSON escape sequences only; unrecognised escapes are an error
                # //why reject unknown escapes: silently stripping the backslash (the
                # // fallback .get(esc,esc)) changes the string value without warning,
                # // which could mask injection attempts in arg values.
                _ESC_MAP = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
                if esc not in _ESC_MAP:
                    raise ExpressionParseError(
                        f"unsupported escape sequence \\{esc!r} in string literal",
                        pos=self._pos - 1,
                        token="\\" + esc,
                    )
                buf.append(_ESC_MAP[esc])
                self._pos += 1
            else:
                if ch == "\x00":
                    raise ExpressionParseError(
                        "null byte not allowed in string literal",
                        pos=self._pos,
                        token="\\x00",
                    )
                buf.append(ch)
                self._pos += 1
        self._expect('"')
        return "".join(buf)


# ---------------------------------------------------------------------------
# Public parse() entry point
# ---------------------------------------------------------------------------


def parse(expr_string: str) -> ExprAST:
    """Parse an lgwks-expression/1 string into a list of Step dicts.

    Returns a list of step dicts: [{verb_id, args, index, metadata}, ...].
    Raises ExpressionParseError on invalid syntax or shell injection patterns.
    Never executes, never calls a subprocess.
    """
    if not isinstance(expr_string, str) or not expr_string.strip():
        raise ExpressionParseError("expression must be a non-empty string", pos=0, token="")
    _check_injection(expr_string)
    return _Parser(expr_string.strip()).parse_pipeline()


# ---------------------------------------------------------------------------
# Canonicalisation + plan_id
# ---------------------------------------------------------------------------


def _canonical_step(step: dict) -> str:
    """Render one step as its canonical string for plan_id computation.

    # //why canonical form: plan_id is SHA-256 of the canonical expression so the
    # // same intent expressed with different arg ordering or whitespace gives the
    # // same plan_id (portable, machine-agnostic identity for the intent).
    """
    vid = step["verb_id"].lower()
    args = step["args"]
    if not args:
        return vid
    # Sort args by key (lexicographic) per spec.
    sorted_pairs = sorted(args.items())
    parts = []
    for k, v in sorted_pairs:
        if v is None:
            parts.append(f"{k}:null")
        elif isinstance(v, bool):
            parts.append(f"{k}:{'true' if v else 'false'}")
        elif isinstance(v, str):
            # Re-serialise as a JSON string so whitespace inside values is
            # unambiguous and the canonical form is valid JSON-string syntax.
            parts.append(f"{k}:{json.dumps(v, ensure_ascii=False)}")
        else:
            parts.append(f"{k}:{v}")
    return f"{vid}[{','.join(parts)}]"


def _canonicalise(ast: ExprAST) -> str:
    """Produce the canonical expression string from the parsed AST.

    Rules (spec Content-Addressing):
      1. Normalise whitespace (collapse runs, strip edges).
      2. Sort each step's args by key.
      3. Lowercase verb_id chain.
    """
    return " | ".join(_canonical_step(s) for s in ast)


def _plan_id(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

# //why reuse _classify from lgwks_multiply not re-declare: two drifting risk
# classifiers is worse than one imperfect one. Same principle as lgwks_geoexpr.
from lgwks_multiply import _classify, _RISK_ORDER  # noqa: E402


def _manifest_capability_entry(verb_id: str, manifest: dict) -> dict[str, Any] | None:
    for cap_entry in manifest.get("capabilities", []):
        if cap_entry.get("capability") == verb_id:
            return cap_entry
    return None


def _is_live_mcp_wiring(wired: Any) -> bool:
    if not isinstance(wired, str):
        return False
    stripped = wired.strip()
    return bool(stripped) and stripped.lower() not in _NEGATION_STRINGS


def _risk_for_primitive(primitive_ref: str | None, verb_id: str, manifest: dict) -> str:
    """Assign risk_class to a step based on its resolved primitive.

    Policy (spec Risk Classification):
      cli:     -> run _classify on the cli verb string (reuse from lgwks_multiply)
      mcp:     -> 'mutate' (conservative; external call, side effects unknown)
      skill:   -> 'unknown'
      agent:   -> 'unknown'
      null (unresolved) -> 'unknown'
    """
    if primitive_ref is None:
        return "unknown"
    if primitive_ref.startswith("cli:"):
        cli_verb = primitive_ref[4:]  # strip "cli:" prefix
        return _classify(cli_verb)
    if primitive_ref.startswith("mcp:"):
        cap_entry = _manifest_capability_entry(verb_id, manifest) or {}
        if cap_entry.get("risk") == "read":
            return "read"
        return "mutate"
    # skill: and agent: both default to unknown per spec.
    return "unknown"


def _max_risk(risks: list[str]) -> str:
    """Return the maximum risk class across a list of risk strings."""
    worst = max((_RISK_ORDER.get(r, 2) for r in risks), default=0)
    return next(k for k, v in _RISK_ORDER.items() if v == worst)


# ---------------------------------------------------------------------------
# Verb resolution
# ---------------------------------------------------------------------------


def _resolve_verb_against_manifest(verb_id: str, manifest: dict) -> str | None:
    """Resolve verb_id against the live manifest. Returns a PrimitiveRef or None.

    Priority order (spec Verb Resolution Protocol):
      1. cli: verb_id matches a manifest verb name (dot -> space)
      2. mcp: capabilities list has a wired, non-null entry matching verb_id
      3. skill: ~/.claude/skills/<verb_id>/SKILL.md exists
      4. agent: ~/.claude/agents/<verb_id>.md or directory exists
    First match wins.
    """
    # 1. cli -- convert dots to spaces to match manifest verb names.
    cli_name = verb_id.replace(".", " ")
    verb_names = {v["verb"] for v in manifest.get("verbs", [])}
    if cli_name in verb_names:
        return f"cli:{cli_name}"

    # 2. mcp -- capabilities list with a wired, live non-empty string entry.
    # //why reject negation-looking strings: manifests are JSON-ish surfaces and hostile or
    # // buggy producers can serialize "inactive" as "false"/"0"/"null". Treat those as
    # // unwired here so the compiler fails closed instead of activating an MCP primitive.
    for cap_entry in manifest.get("capabilities", []):
        wired = cap_entry.get("wired")
        if cap_entry.get("capability") == verb_id and _is_live_mcp_wiring(wired):
            return f"mcp:{verb_id}"

    # 3. skill -- global skills directory.
    skill_path = Path.home() / ".claude" / "skills" / verb_id / "SKILL.md"
    if skill_path.exists():
        return f"skill:{verb_id}"

    # 4. agent -- global agents directory.
    agents_dir = Path.home() / ".claude" / "agents"
    if (agents_dir / f"{verb_id}.md").exists() or (agents_dir / verb_id).is_dir():
        return f"agent:{verb_id}"

    return None


def _schema_for_verb(_verb_id: str, _manifest: dict) -> tuple[dict, dict]:
    """Return (input_schema, output_schema) for a verb_id.

    Currently returns ({}, {}) (any) for all verbs; the manifest v0 does not
    yet carry per-verb JSON Schema fragments. The caller emits schema_unknown
    warnings when this returns ({}, {}).
    """
    # Future: manifest verbs could carry input_schema/output_schema keys.
    return {}, {}


# ---------------------------------------------------------------------------
# Type compatibility check (spec Type System)
# ---------------------------------------------------------------------------


def _schemas_compatible(upstream_output: dict, downstream_input: dict) -> bool:
    """Structural subtype: True if every required field in downstream_input
    exists in upstream_output with a compatible type, or either schema is {} (any).

    # //why {} == any: the spec says 'either schema is any -> compatible'. Un-annotated
    # // verbs do not break pipelines; the gap is surfaced as a warning.
    """
    if not upstream_output or not downstream_input:
        return True
    # Simple type-level check: if both declare a top-level 'type', they must agree.
    up_type = upstream_output.get("type")
    dn_type = downstream_input.get("type")
    if up_type and dn_type and up_type != dn_type:
        return False
    return True


# ---------------------------------------------------------------------------
# JSON Schema validation
# ---------------------------------------------------------------------------


def _validate_plan_schema(plan: dict) -> None:
    """Validate the plan dict against the lgwks-expression-v1 schema rules.

    Uses stdlib only (no jsonschema library per spec dependency constraint).
    Checks required keys, const values, and regex patterns from the schema.

    # //why validate inside compile not at caller: the plan must be valid before
    # // it leaves this module; callers should not need a separate validation call.
    """
    required_keys = {
        "schema", "plan_id", "expression", "canonical_expression",
        "manifest_version", "steps", "risk_class", "compile_policy",
    }
    missing = required_keys - set(plan)
    if missing:
        raise ExpressionParseError(f"plan missing required keys: {sorted(missing)}")

    if plan["schema"] != "lgwks-expression/1":
        raise ExpressionParseError(
            f"plan schema must be 'lgwks-expression/1', got {plan['schema']!r}"
        )

    if not re.match(r"^[0-9a-f]{64}$", plan["plan_id"]):
        raise ExpressionParseError(
            f"plan_id must be 64-char lowercase hex, got {plan['plan_id']!r}"
        )

    if plan["risk_class"] not in _VALID_RISKS:
        raise ExpressionParseError(
            f"risk_class must be one of {sorted(_VALID_RISKS)}"
        )

    cp = plan.get("compile_policy", {})
    if cp.get("shell") is not False:
        raise ExpressionParseError(
            "compile_policy.shell must be false (invariant: no shell execution)"
        )

    if not plan["steps"]:
        raise ExpressionParseError("plan must have at least one step")

    step_required = {
        "index", "verb_id", "resolved_primitive", "args",
        "input_schema", "output_schema", "risk_class", "needs_review",
    }
    expected_indices = list(range(len(plan["steps"])))
    actual_indices = [s.get("index") for s in plan["steps"]]
    if actual_indices != expected_indices:
        raise ExpressionParseError(
            f"step indices must be sequential starting at 0, got {actual_indices!r}"
        )

    for s in plan["steps"]:
        step_missing = step_required - set(s)
        if step_missing:
            raise ExpressionParseError(
                f"step {s.get('index', '?')} missing keys: {sorted(step_missing)}"
            )
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", s["verb_id"]):
            raise ExpressionParseError(
                f"verb_id {s['verb_id']!r} does not match VerbId pattern"
            )
        if s["resolved_primitive"] is not None:
            if not re.match(r"^(cli:|mcp:|skill:|agent:).+$", s["resolved_primitive"]):
                raise ExpressionParseError(
                    f"resolved_primitive {s['resolved_primitive']!r} does not match PrimitiveRef pattern"
                )
        # //why validate step-level risk_class: the schema enum applies per-step, not just
        # // plan-level. A malformed plan (e.g. produced by compile() with a crafted AST) could
        # // carry an invalid risk_class that confuses downstream risk aggregation.
        if s["risk_class"] not in _VALID_RISKS:
            raise ExpressionParseError(
                f"step {s.get('index', '?')} risk_class {s['risk_class']!r} not in valid set"
            )
        # //why validate needs_review is a bool: a non-bool truthy value (e.g. string) passes
        # // any(s["needs_review"]...) in approval_for_plan, but a non-bool falsy value (e.g. "")
        # // could allow a review-required step to slip through the deny gate.
        if not isinstance(s["needs_review"], bool):
            raise ExpressionParseError(
                f"step {s.get('index', '?')} needs_review must be bool, got {type(s['needs_review']).__name__!r}"
            )


# ---------------------------------------------------------------------------
# Main compile entry point (from string -- preserves original)
# ---------------------------------------------------------------------------


def compile_from_string(expr_string: str, manifest: dict) -> dict:
    """Parse an expression string and compile it to an lgwks-expression/1 plan.

    This is the preferred entry point for all callers (CLI, routing, tests).
    Preserves the original expression string in plan['expression'].

    Never executes, never calls a subprocess.
    Raises ExpressionParseError on invalid syntax.
    Unresolved verbs produce warnings (not errors) per spec.
    """
    ast = parse(expr_string)
    canonical = _canonicalise(ast)
    pid = _plan_id(canonical)

    warnings: list[str] = []
    steps_out: list[dict] = []
    prev_output_schema: dict = {}

    for idx, step in enumerate(ast):
        verb_id = step["verb_id"]
        args = step["args"]

        primitive = _resolve_verb_against_manifest(verb_id, manifest)
        # //why agent:/skill: also need review: per spec and schema, needs_review must
        # // be True for unresolved verbs AND for agent:/skill: primitives (both namespaces
        # // have unbounded execution scope not visible from the expression alone). Leaving
        # // needs_review=False for agent: would allow approval='ask' instead of 'deny'.
        needs_review = (
            primitive is None
            or (isinstance(primitive, str) and (
                primitive.startswith("agent:") or primitive.startswith("skill:")
            ))
        )
        if primitive is None:
            warnings.append(
                f"step {idx}: verb_id {verb_id!r} unresolved; needs_review=true"
            )
        elif needs_review:
            warnings.append(
                f"step {idx}: primitive {primitive!r} requires human review; needs_review=true"
            )

        risk = _risk_for_primitive(primitive, verb_id, manifest)
        input_schema, output_schema = _schema_for_verb(verb_id, manifest)

        # Emit schema_unknown warning -- all verbs currently lack schema metadata.
        warnings.append(f"step {idx}: schema_unknown for {verb_id!r}")

        # Type compatibility check with previous step's output.
        if idx > 0 and not _schemas_compatible(prev_output_schema, input_schema):
            warnings.append(
                f"step {idx}: type incompatibility between step {idx - 1} output "
                f"and step {idx} input"
            )
        prev_output_schema = output_schema

        steps_out.append({
            "index": idx,
            "verb_id": verb_id,
            "resolved_primitive": primitive,
            "args": args,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "risk_class": risk,
            "needs_review": needs_review,
        })

    plan_risk = _max_risk([s["risk_class"] for s in steps_out])

    plan = {
        "schema": "lgwks-expression/1",
        "plan_id": pid,
        "expression": expr_string,
        "canonical_expression": canonical,
        "manifest_version": manifest.get("manifest", "unknown"),
        "steps": steps_out,
        "risk_class": plan_risk,
        "compile_policy": {
            "shell": False,
            "unknown_requires_review": True,
            "destructive_requires_force": True,
        },
        "warnings": warnings,
    }

    _validate_plan_schema(plan)
    return plan


# compile() is an alias for compile_from_string() for API symmetry with parse().
def compile(expr_ast: ExprAST, manifest: dict) -> dict:  # noqa: A001
    """Compile a pre-parsed ExprAST to an lgwks-expression/1 plan.

    Use compile_from_string() when you have the original expression string
    (preferred). This variant is provided for callers who have already parsed.
    The plan['expression'] field will contain the canonical form.
    """
    canonical = _canonicalise(expr_ast)
    pid = _plan_id(canonical)

    warnings: list[str] = []
    steps_out: list[dict] = []
    prev_output_schema: dict = {}

    for idx, step in enumerate(expr_ast):
        verb_id = step["verb_id"]
        args = step["args"]

        primitive = _resolve_verb_against_manifest(verb_id, manifest)
        # //why same fix as compile_from_string: agent:/skill: -> needs_review=True.
        needs_review = (
            primitive is None
            or (isinstance(primitive, str) and (
                primitive.startswith("agent:") or primitive.startswith("skill:")
            ))
        )
        if primitive is None:
            warnings.append(
                f"step {idx}: verb_id {verb_id!r} unresolved; needs_review=true"
            )
        elif needs_review:
            warnings.append(
                f"step {idx}: primitive {primitive!r} requires human review; needs_review=true"
            )

        risk = _risk_for_primitive(primitive, verb_id, manifest)
        input_schema, output_schema = _schema_for_verb(verb_id, manifest)
        warnings.append(f"step {idx}: schema_unknown for {verb_id!r}")

        if idx > 0 and not _schemas_compatible(prev_output_schema, input_schema):
            warnings.append(
                f"step {idx}: type incompatibility between step {idx - 1} output "
                f"and step {idx} input"
            )
        prev_output_schema = output_schema

        steps_out.append({
            "index": idx,
            "verb_id": verb_id,
            "resolved_primitive": primitive,
            "args": args,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "risk_class": risk,
            "needs_review": needs_review,
        })

    plan_risk = _max_risk([s["risk_class"] for s in steps_out])

    plan = {
        "schema": "lgwks-expression/1",
        "plan_id": pid,
        "expression": canonical,  # no original string available; use canonical
        "canonical_expression": canonical,
        "manifest_version": manifest.get("manifest", "unknown"),
        "steps": steps_out,
        "risk_class": plan_risk,
        "compile_policy": {
            "shell": False,
            "unknown_requires_review": True,
            "destructive_requires_force": True,
        },
        "warnings": warnings,
    }

    _validate_plan_schema(plan)
    return plan


# ---------------------------------------------------------------------------
# Approval policy (mirrors geo compiler approval matrix, spec Risk Classification)
# ---------------------------------------------------------------------------


def approval_for_plan(plan: dict) -> str:
    """Derive approval class from the compiled plan.

      read + all resolved  -> auto_allowed
      mutate or unknown    -> ask
      destructive or any needs_review -> deny
    """
    if plan["risk_class"] == "destructive":
        return "deny"
    if any(s["needs_review"] for s in plan["steps"]):
        return "deny"
    if plan["risk_class"] == "read":
        return "auto_allowed"
    return "ask"


# ---------------------------------------------------------------------------
# Routing helper used by lgwks_geoexpr
# ---------------------------------------------------------------------------


def is_expression_string(text: str) -> bool:
    """Return True if text looks like an lgwks-expression/1 string.

    Heuristic: starts with a lowercase SEGMENT identifier (not '{', '[', '"'),
    followed by either '[' (args) or ' | ' (pipe) or end of input.

    # //why heuristic not full parse: cheap O(1) probe for routing. A false
    # // negative sends the input to the existing JSON path which correctly errors.
    # // A false positive produces a descriptive ExpressionParseError.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Must start with a lowercase letter -- not a JSON object, array, or string.
    if not stripped[0].isalpha() or not stripped[0].islower():
        return False
    if stripped[0] in "{[\"":
        return False
    # Matches: verb_id alone, verb_id[...], or verb_id ... | ...
    return bool(re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*(\[.*])?(\s*\|.*)?$", stripped, re.DOTALL))
