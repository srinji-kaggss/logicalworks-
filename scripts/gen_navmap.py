#!/usr/bin/env python3
"""gen_navmap — relational + staleness module atlas for AI navigation (stdlib only).

Emits a STRICT, QUERYABLE map of the lgwks code surface so an agent reads/queries ONE
artifact instead of re-grepping ~46k LOC every session. Reproducible (re-run to refresh)
— generated from source, never hand-maintained, so it cannot rot.

Outputs (repo root):
  docs/navmap.json   machine-readable, schema `lgwks.navmap.v1` (the queryable contract)
  docs/NAVMAP.md     terse human/AI atlas grouped by subsystem + per-issue rollup

Per-module facts (pure AST + git, no model):
  purpose · loc · subsystem · deps · used_by · has_cli · has_tests · owning_issue ·
  last_commit_days · integration · staleness

Staleness enum (EXACT precedence — the layer the Director asked for):
  active      = used_by non-empty (imported by another module)  OR  (has_cli & has_tests & age<180)
  scaffolding = no caller, but owned by an OPEN canonical issue (pending wiring)
  staling     = no caller, CLI-only, no open issue, age>=180 (decide: wire or retire)
  orphan      = no caller, no CLI, no issue (deletion candidate)

Run from repo root:  python3 scripts/gen_navmap.py
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "lgwks.navmap.v1"
NOW = time.time()
AGE_ACTIVE_DAYS = 180

INCLUDE_DIRS = ["", "axiom", "graphify", "hooks", "scripts", "tools"]
SKIP = {"tests", "models", "store", ".venv", "node_modules", "__pycache__"}

# Curated linkage: module stem -> owning packet/issue (for holistic per-issue view).
# OPEN issues drive the `scaffolding` state; closed/landed packets are recorded for rollup.
PACKET_MAP = {
    "lgwks_vector": ("I1", None), "lgwks_input": ("I2", None),
    "lgwks_lfm2_extract": ("I3", None), "lgwks_embed_port": ("I4", None),
    "lgwks_score": ("I5", None), "lgwks_rank": ("I6", None),
    "lgwks_inbound": ("I7", None),
    "lgwks_admission": ("I8", "#72"), "lgwks_capability": ("I8", "#72"),
    "lgwks_crdt": ("I9", "#73"), "lgwks_viz_project": ("I10", "#74"),
    "lgwks_waste": ("I11", "#75"),
}
OPEN_ISSUES = {"#72", "#73", "#74", "#75"}

SUBSYSTEMS = [
    ("Ingestion spine (I1–I12)", r"\b(I[0-9]{1,2})\b|INGESTION",
     {"vector", "embed", "embed_port", "score", "rank", "inbound", "lfm2", "extract",
      "admission", "capability", "crdt", "viz_project", "waste", "input", "substrate_vector"}),
    ("Research / web acquisition / extract", r"crawl|fetch|web search|html-to|read-anything|public source|site-aware",
     {"crawl", "fetch", "ingest", "run", "preview", "convert", "files", "html", "sites",
      "site_profile", "public", "search", "geoexpr", "expression"}),
    ("Bots / detection / static analysis", r"static (security |)analyz|slop|stress bot|optimization static|detection",
     {"bot_code_hacker", "bot_optimizer", "bot_slop_math", "bot_stress", "debug", "diff",
      "cohere", "concept"}),
    ("Axiom byte framework", r"axiom", {"axiom"}),
    ("Graph / AST / code intelligence", r"graph|AST|leiden|cluster|code.?intelligence",
     {"graph", "graphify", "cluster", "entity", "codebase", "ast"}),
    ("Harness / daemon / orchestration", r"nervous|daemon|harness|reflex|subconscious|lane|orchestrat|re-entry|upkeep",
     {"machine", "cognition", "context", "actor", "synthesizer", "tongue", "route",
      "spawn", "agent", "workflow", "workflows", "repl", "session", "do", "project",
      "cycle", "portal", "monitor", "workercap", "hooks", "capabilities", "multiply", "solve"}),
    ("Membrane / intent / steering", r"membrane|intent|steering|algebraic signature|capability map",
     {"intent", "intent_classifier", "steering", "math", "map"}),
    ("Governance / gates / refusal / auth", r"governance|refus|gate|aup|url.?risk|vault|auth",
     {"aup", "auth", "vault", "keyvault", "urlrisk", "governance", "verify", "doctor"}),
    ("CLI / home / membrane surface", r"dispatcher|home screen|PRD §12",
     {"home", "ui", "manifest", "initialize", "foundation", "gh"}),
    ("Substrate / storage / schema", r"substrate|sqlite|schema|registry|store",
     {"sqlite", "substrate", "schema", "store", "memory"}),
    ("Models / runtime (opaque dep)", r"qwen|ollama|gemini|embedding (model|provider)|coreml|mlx|jepa|apple-local",
     {"ollama", "multimodal", "model", "jepa", "apple", "openrouter", "local_llm"}),
    ("Dev tooling / scripts", r"developer script|training script|one-time",
     {"gen_navmap", "setup_models", "train_intent_classifier", "check_schema_registry"}),
]
ORDER = [s[0] for s in SUBSYSTEMS] + ["Unclassified (triage)"]


def _module_name(path: Path) -> str:
    return str(path.relative_to(ROOT).with_suffix("")).replace("/", ".")


def _iter_py() -> list[Path]:
    out = []
    for f in sorted(ROOT.rglob("*.py")):
        rel = f.relative_to(ROOT)
        if any(part in SKIP for part in rel.parts):
            continue
        # root files (one path part) are always in; nested files must be under an included dir
        if len(rel.parts) > 1 and rel.parts[0] not in INCLUDE_DIRS:
            continue
        out.append(f)
    return out


def _purpose(tree: ast.Module) -> str:
    first = (ast.get_docstring(tree) or "").strip().split("\n", 1)[0].strip()
    first = re.sub(r"^[a-z_]+\s*[—-]\s*", "", first)
    return first[:120]


def _git_ages() -> dict[str, int]:
    """Most-recent-commit age in days, per file path, from one git call."""
    ages: dict[str, int] = {}
    try:
        out = subprocess.run(
            ["git", "log", "--format=@%ct", "--name-only", "--no-renames"],
            cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ages
    ts = None
    for line in out.splitlines():
        if line.startswith("@"):
            ts = int(line[1:])
        elif line and ts is not None and line not in ages:
            ages[line] = int((NOW - ts) // 86400)
    return ages


def main() -> int:
    files = _iter_py()
    all_mods = {_module_name(f): f for f in files}
    stems = {n.split(".")[0] for n in all_mods}
    ages = _git_ages()

    # corpus for textual/dynamic reference detection (the dispatcher loads modules
    # by NAME via __import__/SourceFileLoader — invisible to static import analysis).
    sources: dict[str, str] = {}
    disp = ROOT / "lgwks"
    dispatcher_src = disp.read_text(encoding="utf-8", errors="replace") if disp.exists() else ""

    data: dict[str, dict] = {}
    for name, path in all_mods.items():
        src = path.read_text(encoding="utf-8", errors="replace")
        sources[name] = src
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top in stems and top != name.split(".")[0]:
                        deps.add(top)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in stems and top != name.split(".")[0]:
                    deps.add(top)
        stem = name.split(".")[0]
        rel = str(path.relative_to(ROOT))
        packet, issue = PACKET_MAP.get(stem, (None, None))
        data[name] = {
            "purpose": _purpose(tree),
            "loc": src.count("\n") + 1,
            "deps": sorted(deps),
            "has_cli": "def add_parser" in src,
            "has_tests": (ROOT / "tests" / f"test_{stem.replace('lgwks_', '')}.py").exists()
                         or (ROOT / "tests" / f"test_{stem}.py").exists(),
            "packet": packet,
            "owning_issue": issue,
            "last_commit_days": ages.get(rel),
        }

    # reverse deps (static imports)
    used_by: dict[str, set[str]] = {n.split(".")[0]: set() for n in data}
    for name, d in data.items():
        for dep in d["deps"]:
            used_by.setdefault(dep, set()).add(name.split(".")[0])

    # callers = static importers ∪ textual/dynamic referencers (dispatcher, importlib, string loads)
    for name, d in data.items():
        stem = name.split(".")[0]
        callers = set(used_by.get(stem, set()))
        pat = re.compile(r"\b" + re.escape(stem) + r"\b")
        if dispatcher_src and pat.search(dispatcher_src):
            callers.add("lgwks(dispatcher)")
        for other, osrc in sources.items():
            if other == name:
                continue
            if pat.search(osrc):
                callers.add(other.split(".")[0])
        callers.discard(stem)
        d["used_by"] = sorted(callers)

    # subsystem
    def classify(name: str, d: dict) -> str:
        stem = name.split(".")[0].replace("lgwks_", "")
        leaf = name.split(".")[-1].replace("lgwks_", "")
        hay = name + " " + d["purpose"]
        for label, tag_re, _ in SUBSYSTEMS:
            if re.search(tag_re, hay, re.I):
                return label
        for label, _, kws in SUBSYSTEMS:
            for cand in (stem, leaf):
                if cand in kws or any(cand == k or cand.startswith(k + "_") for k in kws):
                    return label
        return "Unclassified (triage)"

    # staleness (exact precedence)
    def staleness(d: dict) -> str:
        age = d["last_commit_days"] if d["last_commit_days"] is not None else 0
        if d["used_by"]:
            return "active"
        if d["has_cli"] and d["has_tests"] and age < AGE_ACTIVE_DAYS:
            return "active"
        if d["owning_issue"] in OPEN_ISSUES:
            return "scaffolding"
        if d["has_tests"] or d["has_cli"]:
            return "staling"   # built/tested but nothing references it — wire or retire
        return "orphan"        # no caller, no tests, no CLI, no issue — deletion candidate

    def integration(d: dict) -> str:
        if d["used_by"]:
            return "integrated"
        if d["has_cli"]:
            return "cli_only"
        return "unreferenced"

    for name, d in data.items():
        d["subsystem"] = classify(name, d)
        d["staleness"] = staleness(d)
        d["integration"] = integration(d)

    # indexes
    by_subsystem: dict[str, list[str]] = {}
    by_staleness: dict[str, list[str]] = {}
    by_issue: dict[str, list[str]] = {}
    by_packet: dict[str, list[str]] = {}
    for name, d in sorted(data.items()):
        by_subsystem.setdefault(d["subsystem"], []).append(name)
        by_staleness.setdefault(d["staleness"], []).append(name)
        if d["owning_issue"]:
            by_issue.setdefault(d["owning_issue"], []).append(name)
        if d["packet"]:
            by_packet.setdefault(d["packet"], []).append(name)

    totals = {
        "modules": len(data),
        "loc": sum(d["loc"] for d in data.values()),
        "by_staleness": {k: len(v) for k, v in sorted(by_staleness.items())},
        "by_integration": {k: sum(1 for d in data.values() if d["integration"] == k)
                           for k in ("integrated", "cli_only", "unreferenced")},
    }

    doc = {
        "schema": SCHEMA,
        "generated_from": "scripts/gen_navmap.py",
        "staleness_rules": {
            "active": "used_by non-empty OR (has_cli & has_tests & age<180d)",
            "scaffolding": "no caller; owned by an open canonical issue (pending wiring)",
            "staling": "no caller anywhere; built/tested or has a CLI verb; no open issue (wire or retire)",
            "orphan": "no caller; no tests; no CLI; no issue (deletion candidate)",
        },
        "totals": totals,
        "index": {
            "by_subsystem": by_subsystem,
            "by_staleness": by_staleness,
            "by_issue": by_issue,
            "by_packet": by_packet,
        },
        "modules": data,
    }
    (ROOT / "docs" / "navmap.json").write_text(
        json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")

    # ---- markdown ----
    L: list[str] = []
    L.append("# NAVMAP — lgwks module atlas (generated; do not hand-edit)")
    L.append("")
    L.append(f"> `scripts/gen_navmap.py` from source — re-run to refresh. "
             f"**{totals['modules']} modules · {totals['loc']:,} LOC.** Read/query this FIRST. "
             f"Strict machine-readable contract: `docs/navmap.json` (`{SCHEMA}`).")
    L.append("")
    L.append(f"**Staleness:** " + " · ".join(f"`{k}` {v}" for k, v in totals["by_staleness"].items()))
    L.append("")
    L.append("Rules — `active`: referenced by another module/dispatcher (static or dynamic), or a tested "
             "CLI verb <180d · `scaffolding`: no caller, owned by an open issue · "
             "`staling`: no caller anywhere, but built/tested or has a CLI verb, no issue (wire or retire) · "
             "`orphan`: no caller, no tests, no CLI, no issue (deletion candidate).")
    L.append("")
    L.append("Row legend: `cli` `test` · `←N` imported by N · `→N` imports N · `Nd` days since last commit.")
    L.append("")

    # per-issue rollup first (the holistic "exploring an issue" view)
    if by_issue:
        L.append("## Per-issue rollup (open canonical issues → owned modules + staleness)")
        L.append("")
        L.append("| issue | packet | modules (staleness) |")
        L.append("|---|---|---|")
        for issue in sorted(by_issue):
            mods = by_issue[issue]
            cell = ", ".join(f"`{m.split('.')[0]}` ({data[m]['staleness']})" for m in mods)
            pk = ",".join(sorted({data[m]['packet'] for m in mods if data[m]['packet']}))
            L.append(f"| {issue} | {pk} | {cell} |")
        L.append("")

    for label in ORDER:
        mods = by_subsystem.get(label)
        if not mods:
            continue
        sub_loc = sum(data[m]["loc"] for m in mods)
        L.append(f"## {label}  ·  {len(mods)} mod · {sub_loc:,} LOC")
        L.append("")
        L.append("| module | purpose | loc | stale | rel |")
        L.append("|---|---|---|---|---|")
        for m in mods:
            d = data[m]
            rel = []
            if d["has_cli"]:
                rel.append("cli")
            if d["has_tests"]:
                rel.append("test")
            if d["used_by"]:
                rel.append(f"←{len(d['used_by'])}")
            if d["deps"]:
                rel.append(f"→{len(d['deps'])}")
            if d["last_commit_days"] is not None:
                rel.append(f"{d['last_commit_days']}d")
            purpose = (d["purpose"] or "—").replace("|", "\\|")
            L.append(f"| `{m}` | {purpose} | {d['loc']} | {d['staleness']} | {' '.join(rel)} |")
        L.append("")

    (ROOT / "docs" / "NAVMAP.md").write_text("\n".join(L), encoding="utf-8")

    print(f"navmap: {totals['modules']} modules, {totals['loc']:,} LOC → docs/NAVMAP.md + docs/navmap.json")
    print("  staleness:", totals["by_staleness"])
    print("  integration:", totals["by_integration"])
    n_unc = len(by_subsystem.get("Unclassified (triage)", []))
    print(f"  unclassified: {n_unc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
