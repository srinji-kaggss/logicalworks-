"""
lgwks_preview — the safe sibling of `lgwks x`. Same brace math, no execution, human rendering.

The "one tool" mental model collapses in front of a human here: a brace expression
(expanded by `lgwks_multiply._expand_braces`, classified by `lgwks_multiply._classify`)
becomes a *HumanPreview* projection, never an execution path. Read-only chains are
auto-allowed, mutate chains ask, unknown verbs are surfaced by name, destructive
chains are denied — and the verdict is text, not a process.

  lgwks preview 'git {status, log -1, diff --stat}'   # 3 read-only steps, auto-allowed
  lgwks preview 'rm -rf /'                            # destructive, denied (verdict, not error)
  lgwks preview 'frobnicate x'                        # unknown verb named in steps
  lgwks preview 'git add {a.py,b.py}'                 # mutate, needs yes

Safety (T0): no subprocess, no `_run_one`, no shell. The `//why` line on `_to_geoexpr`
is the only place argv is computed, and the argv are the expanded commands verbatim
typed into argv lists (no shlex round-trip into a shell string). Output is two shapes
only: TTY → human rendering; non-TTY (or `--json`) → the HumanPreview JSON object.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# //why reuse, not re-declare: the brace grammar + risk classifier live in lgwks_multiply
# (the single source of truth shared with `lgwks x`). One risk map, no drift.
from lgwks_multiply import _expand_braces, _classify

# //why reuse, not re-declare: the typed compiler + HumanPreview projection live in
# lgwks_geoexpr. We feed the same shape so plan_id is byte-identical to what `lgwks geo
# preview` would emit, and so a future `lgwks run --from-preview <plan_id>` can join them.
import lgwks_geoexpr as geo

# //why reuse, not re-declare: brand palette + spine + band are in lgwks_ui. preview is a
# viewer, not a re-painter; all colour comes from the existing tokens.
import lgwks_ui as ui

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "geo-runs"
SCHEMA_GEOEXPR = "lgwks-geoexpr/1"

# Approval -> one-line verdict (the human-facing translation of the gate).
_VERDICTS = {
    "auto_allowed": "auto-allowed (read-only, no confirmation)",
    "ask": "needs yes — pass to `lgwks x` with --yes",
    "deny": "denied (destructive) — refusing to run; pass to `lgwks x` with --force to override",
}

# Risk class -> (glyph, lgwks_ui colour token). Mirrors lgwks_multiply._show_chain's set.
# //why reuse the same glyph set: the spine language is one vocabulary across verbs.
_GLYPHS = {
    "read": ("·", ui.EMERALD),
    "mutate": ("▲", ui.AMBER),
    "destructive": ("✗", ui.RUST),
    "unknown": ("?", ui.AMBER),
}

# //why conservative: deny anything ambiguous. An empty/brace-less expr has nothing to preview
# and the spec's round-1 acceptance says "rc != 0 is reserved for: missing argv, unparseable
# brace (no `{}` group, or empty group)".
_MISSING_ARG_RC = 2


def _to_geoexpr(expr: str) -> dict:
    """brace-expr -> a single-axis GeoExpr (verb = expanded command, scope = a single bound).

    The verb axis values are the expanded commands *verbatim* (spec). Reuses the same
    `_expand_braces` routine that `lgwks x` uses, so the brace grammar is one source of truth.
    The `scope` axis is a single deterministic value for parity with the geo schema; the
    cartesian product collapses to N (one per expanded command), so plan_id depends only on
    the commands, not on the scope axis.
    """
    commands = _expand_braces(expr)
    if not commands:
        raise ValueError("empty expansion")
    return {
        "schema": SCHEMA_GEOEXPR,
        "op": "product",
        "axes": [
            {"name": "verb", "values": commands},
            {"name": "scope", "values": ["preview"]},
        ],
        "constraints": {"risk_max": "read", "requires_human_preview": True},
    }


def render_preview(preview: dict, *, on: bool) -> str:
    """HumanPreview -> rendering string. No colour when on=False.

    The shape is a stable, line-by-line projection: a band header, a one-paragraph summary,
    a numbered list of steps (one line per `effect`), a risk glyph line, and a verdict.
    All colour goes through lgwks_ui tokens (no inline escape codes).
    """
    lines: list[str] = []
    risk = preview.get("risk", "unknown")
    glyph, code = _GLYPHS.get(risk, ("·", ui.MUTED))
    plan_id = preview.get("plan_id", "")

    # header band: verb (preview) + subtitle (plan_id short)
    pid_short = plan_id[:12] if plan_id else "-"
    lines.extend(ui.band("preview", f"plan {pid_short}…", on=on))

    # summary paragraph (one paragraph, not a list — per spec)
    summary = preview.get("summary", "").strip()
    if summary:
        lines.append(ui.spine(
            ui.fg(summary, ui.CREAM, on=on), on=on))

    # numbered steps (one line per `effect`, not `label` — per spec)
    steps = preview.get("steps", []) or []
    for i, step in enumerate(steps, start=1):
        effect = (step.get("effect") or step.get("label") or "").strip()
        label = (step.get("label") or "").strip()
        if label and effect and label != effect:
            text = f"{i}. {effect}  ({label})"
        else:
            text = f"{i}. {effect or label}"
        lines.append(ui.spine(
            ui.fg(text, ui.CREAM_DIM, on=on), on=on))

    # risk line: coloured glyph + class
    risk_line = (ui.fg(f"{glyph} ", code, on=on, bold=True)
                 + ui.fg(f"[{risk}]", code, on=on)
                 + ui.fg(f"   risk_max=read", ui.SLATE_DIM, on=on))
    lines.append(ui.spine(risk_line, on=on))

    # verdict
    approval = preview.get("approval", "ask")
    verdict = verdict_line(approval)
    verdict_code = ui.EMERALD if approval == "auto_allowed" else (
        ui.RUST if approval == "deny" else ui.AMBER)
    lines.append(ui.spine(
        ui.fg(verdict, verdict_code, on=on, bold=True), on=on))

    return "\n".join(lines)


def verdict_line(approval: str) -> str:
    """Approval string -> one-line verdict (text on the page, not a real prompt)."""
    return _VERDICTS.get(approval, f"approval={approval} — review the plan")


def _persist_preview(plan_id: str, preview: dict) -> None:
    """Write the HumanPreview JSON under store/geo-runs/<plan_id>/, parity with `geo run`.

    //why write the file even though preview never executes: the round-1 acceptance demands
    parity with `geo run`'s on-disk footprint for the same plan, so an agent can later pick up
    the preview by plan_id and pass it to `lgwks x` for execution.
    """
    run_dir = RUN_ROOT / plan_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "human-preview.json").write_text(
        json.dumps(preview, indent=2, sort_keys=True), encoding="utf-8")


def preview_command(args) -> int:
    """CLI entry point. Returns the process exit code.

    Exits 0 in all four success cases (read / mutate / unknown / destructive) — "denied" is
    a verdict, not an error. rc != 0 is reserved for: missing argv, unparseable brace, and
    a compiler Result whose `ok` is False.
    """
    expr = getattr(args, "expr", None)
    if not expr or not expr.strip():
        print("usage: lgwks preview '<brace-expr>'", file=sys.stderr)
        return _MISSING_ARG_RC

    try:
        geoexpr = _to_geoexpr(expr)
    except ValueError as e:
        print(f"refusing: brace expansion failed: {e}", file=sys.stderr)
        return _MISSING_ARG_RC

    compiled = geo.compile_plan(geoexpr)
    if not compiled["ok"]:
        print(json.dumps(compiled, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    plan = compiled["value"]
    risk_max = geoexpr.get("constraints", {}).get("risk_max", "read")
    preview = geo.human_preview(plan, risk_max)

    # persist the HumanPreview (parity with `geo run`'s on-disk footprint)
    try:
        _persist_preview(plan["plan_id"], preview)
    except OSError:
        # //why degrade: the spec says preview is read-only + non-executing; an unwritable
        # store must not block the verdict the human asked for.
        pass

    if getattr(args, "json", False):
        print(json.dumps(preview, indent=2, sort_keys=True))
        return 0

    on = ui.color_on(sys.stdout)
    print(render_preview(preview, on=on))
    return 0


def add_parser(sub) -> None:
    """Register `lgwks preview` as a top-level verb. The verb is user-facing, NOT under `geo`.

    `geo` is the internal compiler; `preview` is what the human types. The split keeps the
    user surface orthogonal to the typed surface (one verb per mental step).
    """
    p = sub.add_parser("preview",
                       help="preview a brace expression as a HumanPreview (safe sibling of `x`)")
    p.add_argument("expr", help="brace expression, e.g. 'git {status, log -1, diff --stat}'")
    p.add_argument("--json", action="store_true",
                   help="emit the HumanPreview JSON object (same shape as `lgwks geo preview`)")
    p.set_defaults(func=preview_command)
