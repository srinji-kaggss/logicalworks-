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

import json
import shlex
import sys
from pathlib import Path

# //why reuse, not re-declare: a second risk classifier would drift from `lgwks x`. One source of risk truth.
from lgwks_multiply import _classify, _RISK_ORDER, _run_one

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "geo-runs"  # runtime output; gitignored, never source of truth
SCHEMA_TRANSCRIPT = "lgwks-result-transcript/1"
SCHEMA_EMBEDDING = "lgwks-artifact-embedding/1"
EMBED_DIMS = 128

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


from lgwks_hashing import canonical_id as _sha, digest as _digest  # canonical object/text ids (one source of truth)


def validate_geoexpr(obj) -> dict:
    """Return Result. Shape-checks lgwks-geoexpr/1 before any compilation (schema layer of T0 stack)."""
    if not isinstance(obj, dict):
        return _err("schema_not_object", "GeoExpr must be a JSON object")
    if obj.get("schema") != SCHEMA_GEOEXPR:
        return _err("schema_mismatch", f"expected schema {SCHEMA_GEOEXPR}, got {obj.get('schema')!r}")
    op = obj.get("op")
    if op not in ("product", "union", "intersection", "difference"):
        return _err("unsupported_op", f"op must be 'product', 'union', 'intersection' or 'difference', got {op!r}")
    axes = obj.get("axes")
    if op == "product" and (not isinstance(axes, list) or not axes):
        return _err("axes_empty", "axes must be a non-empty list for product op")
    
    if op in ("union", "intersection", "difference"):
        sets = obj.get("sets")
        if not isinstance(sets, list) or not sets:
            return _err("sets_empty", f"sets must be a non-empty list for {op} op")

    if op == "product":
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


def _embed_record(kind: str, item_id: str, text: str) -> dict:
    """Deterministic local embedding record. //why reuse lgwks_embed: one embedder, no drift."""
    import lgwks_embed
    return {
        "schema": SCHEMA_EMBEDDING,
        "kind": kind,
        "item_id": item_id,
        "text_sha256": _digest(text),
        "embedding_model": "deterministic-feature-hash-v1",
        "dimensions": EMBED_DIMS,
        "embedding": lgwks_embed._embedding(text, EMBED_DIMS),
        "local_only": True,
    }


def execute_plan(plan: dict, *, allow_unknown: bool = False, force: bool = False) -> dict:
    """Gate then execute a CommandPlan. Returns a ResultTranscript Result.

    Gate (mirrors `lgwks x`, the single approval authority):
      - destructive  -> refused unless force (compile_policy.destructive_requires_force)
      - unknown verb -> refused unless allow_unknown (compile_policy.unknown_requires_review)
    Only validated argv run, never a shell string.
    """
    commands = plan["commands"]
    if any(c["risk"] == "destructive" for c in commands) and not force:
        return _err("execute_destructive_blocked", "destructive commands need force; refusing")
    if any(c["needs_review"] for c in commands) and not allow_unknown:
        return _err("execute_unknown_blocked", "unknown verbs need review (--allow-unknown); refusing")
    results = []
    for c in commands:
        if c["argv"] is None:
            results.append({"verb": c["verb"], "argv": None, "rc": 2, "ok": False, "out": "unresolved verb"})
            continue
        # //why shlex.join then _run_one: reuse the audited no-shell executor; argv come from a controlled
        # registry with no shell metacharacters, so the round-trip is lossless and injection-free.
        r = _run_one(shlex.join(c["argv"]))
        results.append({"verb": c["verb"], "argv": c["argv"], "rc": r["rc"], "ok": r["ok"], "out": r["out"]})
    return _ok({
        "schema": SCHEMA_TRANSCRIPT,
        "plan_id": plan["plan_id"],
        "source_expr": plan["source_expr"],
        "results": results,
        "all_ok": all(r["ok"] for r in results),
    })


def _persist_run(geoexpr: dict, plan: dict, preview: dict, transcript: dict) -> Path:
    """Embed every translation/preview/plan/result locally (spec §8 pass-condition). Returns the run dir."""
    run_dir = RUN_ROOT / plan["plan_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "geoexpr.json").write_text(json.dumps(geoexpr, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "command-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "human-preview.json").write_text(json.dumps(preview, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "result-transcript.json").write_text(json.dumps(transcript, indent=2, sort_keys=True),
                                                    encoding="utf-8")
    embeddings = [
        _embed_record("geoexpr", plan["source_expr"], json.dumps(geoexpr, sort_keys=True)),
        _embed_record("command-plan", plan["plan_id"], json.dumps(plan["commands"], sort_keys=True)),
        _embed_record("human-preview", plan["plan_id"], preview["summary"]),
    ]
    for i, r in enumerate(transcript["results"]):
        embeddings.append(_embed_record("result", f"{plan['plan_id']}:{i}", r.get("out", "") or r["verb"]))
    with (run_dir / "artifact-embeddings.jsonl").open("w", encoding="utf-8") as fh:
        for row in embeddings:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return run_dir


# --- CLI surface -----------------------------------------------------------------------------------------

def _load_geoexpr(args) -> dict:
    import lgwks_inline
    raw = lgwks_inline.get_precedence_payload(
        expr=getattr(args, "expr", None),
        file_at=getattr(args, "file", None),
        stdin_text=None if sys.stdin.isatty() else sys.stdin.read()
    )
    if not raw:
        return _err("missing_input", "provide --expr, --file, or pipe stdin")
    try:
        return _ok(json.loads(raw))
    except json.JSONDecodeError as e:
        return _err("geoexpr_unparseable", str(e))


def _load_raw(args) -> str:
    """Read the raw input string without attempting JSON decode.

    Priority: --expr flag > --file flag > stdin.
    //why --expr is highest priority: an explicit inline expression string is
    // unambiguous; it avoids reading stdin when the caller is non-interactive.
    """
    import lgwks_inline
    return lgwks_inline.get_precedence_payload(
        expr=getattr(args, "expr", None),
        file_at=getattr(args, "file", None),
        stdin_text=None if sys.stdin.isatty() else sys.stdin.read()
    )


def compile_command(args) -> int:
    # //why probe for expression string before JSON: lgwks-expression/1 strings
    # are not JSON; a leading identifier (not '{') signals the new layer.
    # Brace-expansion paths are unchanged — they go through compile_plan as before.
    raw = _load_raw(args)
    raw_stripped = raw.strip()

    import lgwks_expression as expr_mod
    if expr_mod.is_expression_string(raw_stripped):
        # Route through the lgwks-expression/1 compiler.
        import lgwks_manifest as man
        manifest = man.build_manifest()
        try:
            plan = expr_mod.compile_from_string(raw_stripped, manifest)
        except expr_mod.ExpressionParseError as e:
            print(json.dumps(_err("expression_parse_error", str(e))), file=sys.stderr)
            return 2
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    # Existing GeoExpr JSON path -- preserved unchanged.
    try:
        geoexpr_obj = json.loads(raw_stripped)
    except json.JSONDecodeError as e:
        print(json.dumps(_err("geoexpr_unparseable", str(e))), file=sys.stderr)
        return 2
    result = compile_plan(geoexpr_obj)
    if not result["ok"]:
        print(json.dumps(result), file=sys.stderr)
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


def run_command(args) -> int:
    loaded = _load_geoexpr(args)
    if not loaded["ok"]:
        print(json.dumps(loaded), file=sys.stderr)
        return 2
    geoexpr = loaded["value"]
    compiled = compile_plan(geoexpr)
    if not compiled["ok"]:
        print(json.dumps(compiled), file=sys.stderr)
        return 2
    plan = compiled["value"]
    risk_max = geoexpr.get("constraints", {}).get("risk_max", "read")
    preview = human_preview(plan, risk_max)
    # //why gate before execute: non-interactive callers (agents) must opt in; auto_allowed is read-only.
    if preview["approval"] == "deny":
        print(json.dumps(_err("run_denied", "preview approval is 'deny' (destructive)")), file=sys.stderr)
        return 2
    if preview["approval"] == "ask" and not getattr(args, "yes", False):
        print(json.dumps(_err("run_needs_yes", "approval 'ask' needs --yes in non-interactive run")),
              file=sys.stderr)
        return 2
    transcript = execute_plan(plan, allow_unknown=getattr(args, "allow_unknown", False),
                              force=getattr(args, "force", False))
    if not transcript["ok"]:
        print(json.dumps(transcript), file=sys.stderr)
        return 2
    run_dir = _persist_run(geoexpr, plan, preview, transcript["value"])
    out = {"run_dir": str(run_dir), "transcript": transcript["value"]}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if transcript["value"]["all_ok"] else 1


def add_parser(sub) -> None:
    p = sub.add_parser("geo", help="geometric-CLI translator: typed GeoExpr -> argv plan (no shell)")
    gs = p.add_subparsers(dest="geo_command", required=True)
    comp = gs.add_parser(
        "compile",
        help="GeoExpr JSON (--file or stdin) -> CommandPlan; "
             "or lgwks-expression/1 string (--expr) -> expression plan",
    )
    comp.add_argument("--file", help="path to a GeoExpr JSON file; omit to read stdin")
    # //why --expr on the existing 'geo compile' subparser not a new subparser:
    # spec §Integration Points says expression routing extends 'geo compile', not a new verb.
    comp.add_argument(
        "--expr",
        metavar="EXPRESSION",
        help="lgwks-expression/1 pipeline string, e.g. 'extract[target:\"url\"] | store'",
    )
    comp.set_defaults(func=compile_command)
    prev = gs.add_parser("preview", help="GeoExpr JSON -> HumanPreview projection")
    prev.add_argument("--file", help="path to a GeoExpr JSON file; omit to read stdin")
    prev.set_defaults(func=preview_command)
    run = gs.add_parser("run", help="compile -> preview -> gated execute (argv, no shell) -> embed locally")
    run.add_argument("--file", help="path to a GeoExpr JSON file; omit to read stdin")
    run.add_argument("--yes", action="store_true", help="approve an 'ask' plan in non-interactive run")
    run.add_argument("--allow-unknown", action="store_true", help="allow unknown verbs (still never executed)")
    run.add_argument("--force", action="store_true", help="required for destructive commands")
    run.set_defaults(func=run_command)
