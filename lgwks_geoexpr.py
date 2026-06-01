"""
lgwks_geoexpr — deterministic geometric-CLI compiler (SPEC-geometric-cli-translator-v1).

Scaffolding slice. The typed compiler that sits BEHIND `lgwks x`, not a replacement (spec §9):

    GeoExpr (typed, AI-emitted)  ->  CommandPlan (argv, no shell)  ->  HumanPreview (projection)

Deliberately NOT in this slice (kept as explicit stubs):
  - the Deep ML Model translation/scoring layer (confidence stays None; translator = "deterministic-v0")
  - the correction ledger wiring (the CorrectionRecord *builder* lives here; the store is remaining-work #4)
  - any destructive expansion (denied without the existing force gate)

Safety (T0): the compiler never executes opaque shell strings. Each command is an argv list, risk-classified
by the same conservative classifier `lgwks x` uses (reused, not reinvented — avoids two drifting risk maps).
"""

from __future__ import annotations

import hashlib
import json

# //why reuse, not re-declare: a second risk classifier would drift from `lgwks x`. One source of risk truth.
from lgwks_multiply import _classify, _RISK_ORDER

SCHEMA_GEOEXPR = "lgwks-geoexpr/1"
SCHEMA_PREVIEW = "lgwks-human-preview/1"
SCHEMA_PLAN = "lgwks-command-plan/1"
SCHEMA_CORRECTION = "lgwks-correction/1"

RISK_VOCAB = tuple(_RISK_ORDER)  # ("read", "mutate", "unknown", "destructive")

# Deterministic verb vocabulary. Dotted verb -> argv template + human-facing reason. Read-only spine for
# the scaffolding slice; unknown verbs are surfaced, never silently auto-run (compile_policy.unknown_requires_review).
VERB_REGISTRY: dict[str, dict] = {
    "git.status": {"argv": ["git", "status"], "why": "repo state"},
    "git.log": {"argv": ["git", "log", "-5", "--oneline"], "why": "recent history"},
    "git.diff": {"argv": ["git", "diff", "--stat"], "why": "diff summary"},
    "git.branch": {"argv": ["git", "branch", "--show-current"], "why": "current branch"},
    "fs.list": {"argv": ["ls", "-la"], "why": "list current directory"},
    "fs.pwd": {"argv": ["pwd"], "why": "working directory"},
}


def _ok(value):
    return {"ok": True, "value": value}


def _err(error_code: str, detail: str):
    # //why typed error, not exception: validation failures are recoverable and the caller (AI/Tongue or CLI)
    # must distinguish the kind to ask the right clarifying question.
    return {"ok": False, "error_code": error_code, "detail": detail}


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_geoexpr(obj) -> dict:
    """Return Result. Shape-checks lgwks-geoexpr/1 before any compilation (schema layer of T0 stack)."""
    if not isinstance(obj, dict):
        return _err("schema_not_object", "GeoExpr must be a JSON object")
    if obj.get("schema") != SCHEMA_GEOEXPR:
        return _err("schema_mismatch", f"expected schema {SCHEMA_GEOEXPR}, got {obj.get('schema')!r}")
    if obj.get("op") != "product":
        return _err("unsupported_op", f"only op='product' is supported, got {obj.get('op')!r}")
    axes = obj.get("axes")
    if not isinstance(axes, list) or not axes:
        return _err("axes_empty", "axes must be a non-empty list")
    names = set()
    for axis in axes:
        if not isinstance(axis, dict) or "name" not in axis or "values" not in axis:
            return _err("axis_malformed", "each axis needs 'name' and 'values'")
        if not isinstance(axis["values"], list) or not axis["values"]:
            return _err("axis_values_empty", f"axis {axis.get('name')!r} has no values")
        if axis["name"] in names:
            return _err("axis_duplicate", f"duplicate axis name {axis['name']!r}")
        names.add(axis["name"])
    if "verb" not in names:
        return _err("axis_missing_verb", "a 'verb' axis is required as the command spine")
    constraints = obj.get("constraints", {})
    risk_max = constraints.get("risk_max", "read")
    if risk_max not in _RISK_ORDER:
        return _err("risk_max_unknown", f"risk_max must be one of {RISK_VOCAB}, got {risk_max!r}")
    return _ok(obj)


def _product(axes: list[dict]) -> list[dict]:
    """Cartesian product across axes -> list of {axis_name: value}. Deterministic order (axis order preserved)."""
    combos: list[dict] = [{}]
    for axis in axes:
        combos = [{**c, axis["name"]: v} for c in combos for v in axis["values"]]
    return combos


def _resolve_verb(verb_token: str, scope: str | None) -> dict:
    spec = VERB_REGISTRY.get(verb_token)
    why = VERB_REGISTRY.get(verb_token, {}).get("why", "")
    if scope:
        why = f"{why} [{scope}]" if why else f"scope {scope}"
    if spec is None:
        return {"verb": verb_token, "argv": None, "risk": "unknown", "why": why or "unknown verb",
                "needs_review": True}
    cmd = " ".join(spec["argv"])
    return {"verb": verb_token, "argv": list(spec["argv"]), "risk": _classify(cmd), "why": why or spec["why"],
            "needs_review": False}


def compile_plan(geoexpr: dict) -> dict:
    """GeoExpr -> CommandPlan Result. Pure/deterministic: same GeoExpr always yields the same plan_id."""
    valid = validate_geoexpr(geoexpr)
    if not valid["ok"]:
        return valid
    combos = _product(geoexpr["axes"])
    commands = []
    for combo in combos:
        scope = next((v for k, v in combo.items() if k != "verb"), None)
        resolved = _resolve_verb(combo["verb"], scope)
        commands.append({k: resolved[k] for k in ("argv", "risk", "why", "verb", "needs_review")})
    plan = {
        "schema": SCHEMA_PLAN,
        "source_expr": _sha(geoexpr),
        "commands": commands,
        "compile_policy": {
            "shell": False,
            "unknown_requires_review": True,
            "destructive_requires_force": True,
        },
        "translator": "deterministic-v0",
        "model_confidence": None,  # Deep ML scoring deferred to a later slice
    }
    plan["plan_id"] = _sha(plan["commands"])
    return _ok(plan)


def _worst_risk(commands: list[dict]) -> str:
    worst = max((_RISK_ORDER[c["risk"]] for c in commands), default=0)
    return next(k for k, v in _RISK_ORDER.items() if v == worst)


def human_preview(plan: dict, risk_max: str = "read") -> dict:
    """Render HumanPreview as a projection of the CommandPlan — never authored as the source of truth."""
    commands = plan["commands"]
    worst = _worst_risk(commands)
    if any(c["risk"] == "destructive" for c in commands):
        approval = "deny"  # destructive needs the explicit force gate, never auto-previewed to allow
    elif _RISK_ORDER[worst] <= _RISK_ORDER[risk_max] and worst == "read":
        approval = "auto_allowed"
    else:
        approval = "ask"
    return {
        "schema": SCHEMA_PREVIEW,
        "summary": "; ".join(c["why"] for c in commands) or "no steps",
        "steps": [{"label": c["verb"], "effect": c["why"]} for c in commands],
        "risk": worst,
        "approval": approval,
        "plan_id": plan["plan_id"],
    }


def correction_record(*, source_expr: str, failure_type: str, before: dict, after: dict,
                      corrected_by: str, embedding_ref: str = "") -> dict:
    """Builder for lgwks-correction/1. The ledger STORE is remaining-work #4; this is its typed shape."""
    valid_failures = {"human_misread", "ai_schema_error", "model_translation_error", "execution_surprise"}
    if failure_type not in valid_failures:
        return _err("correction_failure_type_unknown", f"failure_type must be one of {sorted(valid_failures)}")
    if corrected_by not in {"human", "ai", "model", "execution"}:
        return _err("correction_corrected_by_unknown", f"corrected_by invalid: {corrected_by!r}")
    return _ok({
        "schema": SCHEMA_CORRECTION,
        "source_expr": source_expr,
        "failure_type": failure_type,
        "before": before,
        "after": after,
        "corrected_by": corrected_by,
        "training_use": "local_only",
        "embedding_ref": embedding_ref,
    })


# --- CLI surface -----------------------------------------------------------------------------------------

def _load_geoexpr(args) -> dict:
    import sys
    raw = open(args.file, encoding="utf-8").read() if getattr(args, "file", None) else sys.stdin.read()
    try:
        return _ok(json.loads(raw))
    except json.JSONDecodeError as e:
        return _err("geoexpr_unparseable", str(e))


def compile_command(args) -> int:
    loaded = _load_geoexpr(args)
    if not loaded["ok"]:
        print(json.dumps(loaded), file=__import__("sys").stderr)
        return 2
    result = compile_plan(loaded["value"])
    if not result["ok"]:
        print(json.dumps(result), file=__import__("sys").stderr)
        return 2
    print(json.dumps(result["value"], indent=2, sort_keys=True))
    return 0


def preview_command(args) -> int:
    loaded = _load_geoexpr(args)
    if not loaded["ok"]:
        print(json.dumps(loaded), file=__import__("sys").stderr)
        return 2
    geoexpr = loaded["value"]
    result = compile_plan(geoexpr)
    if not result["ok"]:
        print(json.dumps(result), file=__import__("sys").stderr)
        return 2
    risk_max = geoexpr.get("constraints", {}).get("risk_max", "read")
    print(json.dumps(human_preview(result["value"], risk_max), indent=2, sort_keys=True))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("geo", help="geometric-CLI translator: typed GeoExpr -> argv plan (no shell)")
    gs = p.add_subparsers(dest="geo_command", required=True)
    comp = gs.add_parser("compile", help="GeoExpr JSON (--file or stdin) -> CommandPlan")
    comp.add_argument("--file", help="path to a GeoExpr JSON file; omit to read stdin")
    comp.set_defaults(func=compile_command)
    prev = gs.add_parser("preview", help="GeoExpr JSON -> HumanPreview projection")
    prev.add_argument("--file", help="path to a GeoExpr JSON file; omit to read stdin")
    prev.set_defaults(func=preview_command)
