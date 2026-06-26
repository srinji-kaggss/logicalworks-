#!/usr/bin/env python3
"""gen_model_law — generate the model law from its one canonical source (stdlib only).

The model law used to live in TWO independently hand-typed places that drifted:
the `MESH_LAW` Python literal in `lgwks_model_mesh.py`, and the prose stack table
in `docs/AETHERIUS_SPEC_2026.md` §3. Drift is how a hallucinated embed id
(`Qwen3.7-VL-8B`, a visual agent, not an embedder) slipped into the law. This
generator kills that bug class: there is now ONE authored source —
`spec/second-harness/model-law.json` (`lgwks.model.law.v1`) — and everything else
is GENERATED FROM it and GATED against it, so it cannot rot.

What this does for the model law what `gen_okf.py` does for docs and `gen_navmap.py`
does for code: the `MESH_LAW` block is regenerated from source between sentinels,
never hand-maintained. A `--verify` gate proves (1) the committed block matches a
fresh regeneration, (2) every entry conforms to the mesh vocabulary, and (3) the
Aetherius §3 prose table still matches the `prose_table` recorded in the source —
so a future prose edit that re-introduces a hallucinated id FAILS CI.

Modes:
  --verify  generation-freshness + vocab + prose-drift gate; exit 1 on violation (the CI gate).
  --write   regenerate the MESH_LAW block in lgwks_model_mesh.py from the source.
  (default) dry-run: report what --write would change, touch nothing.

Run from repo root:  python3 scripts/gen_model_law.py --write
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "spec" / "second-harness" / "model-law.json"
TARGET = ROOT / "lgwks_model_mesh.py"
AETHERIUS = ROOT / "docs" / "AETHERIUS_SPEC_2026.md"

BEGIN = "# === BEGIN GENERATED MESH_LAW"
END = "# === END GENERATED MESH_LAW ==="

# Emit order mirrors the lgwks_model_mesh._entry signature.
KW_ORDER = ["name", "runtime", "locality", "role", "trust_class", "status",
            "input_schema", "output_schema", "fallback", "eval_gate", "notes"]


# ── canonical source ──────────────────────────────────────────────────────────
def load_law() -> dict:
    with open(SOURCE, "r", encoding="utf-8") as fh:
        law = json.load(fh)
    if law.get("schema") != "lgwks.model.law.v1":
        raise ValueError(f"{SOURCE.name}: schema must be lgwks.model.law.v1")
    if not isinstance(law.get("entries"), list) or not law["entries"]:
        raise ValueError(f"{SOURCE.name}: 'entries' must be a non-empty list")
    return law


def law_entries(law: dict) -> list[dict]:
    """The raw _entry kwargs for each law row, in source order."""
    return [row["entry"] for row in law["entries"]]


# ── python emit (deterministic, idempotent) ────────────────────────────────────
def _py(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_py(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {_py(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"cannot emit {type(value)!r}")


def emit_block(law: dict) -> str:
    lines: list[str] = []
    lines.append(f"{BEGIN} — DO NOT EDIT. Source: spec/second-harness/model-law.json ===")
    lines.append("# Regenerate: python3 scripts/gen_model_law.py --write   (CI gate: --verify)")
    lines.append("MESH_LAW: list[dict[str, Any]] = [")
    candidate_header_done = False
    for row in law["entries"]:
        entry = row["entry"]
        if row.get("layer"):
            prov = row.get("provenance", "")
            lines.append(f"    # {row['layer']} — {entry.get('status')} · {prov}")
        elif entry.get("status") == "candidate_reference" and not candidate_header_done:
            lines.append("    # Candidate references: documented inventory, not runtime law.")
            candidate_header_done = True
        lines.append("    _entry(")
        for kw in KW_ORDER:
            if kw in entry:
                lines.append(f"        {kw}={_py(entry[kw])},")
        lines.append("    ),")
    lines.append("]")
    lines.append(END)
    return "\n".join(lines) + "\n"


def splice(text: str, block: str) -> str:
    src = text.splitlines(keepends=True)
    bi = next((i for i, ln in enumerate(src) if ln.startswith(BEGIN)), None)
    ei = next((i for i, ln in enumerate(src) if ln.rstrip("\n") == END), None)
    if bi is None or ei is None or ei < bi:
        raise ValueError(f"{TARGET.name}: missing/!ordered GENERATED MESH_LAW sentinels")
    return "".join(src[:bi]) + block + "".join(src[ei + 1:])


def current_block(text: str) -> str:
    src = text.splitlines(keepends=True)
    bi = next((i for i, ln in enumerate(src) if ln.startswith(BEGIN)), None)
    ei = next((i for i, ln in enumerate(src) if ln.rstrip("\n") == END), None)
    if bi is None or ei is None or ei < bi:
        raise ValueError(f"{TARGET.name}: missing/!ordered GENERATED MESH_LAW sentinels")
    return "".join(src[bi:ei + 1])


# ── prose-drift reconcile (the check that would have caught the hallucination) ──
def _strip_md(cell: str) -> str:
    return cell.replace("**", "").replace("`", "").strip()


def parse_aetherius_table() -> list[dict]:
    text = AETHERIUS.read_text(encoding="utf-8")
    # locate the §3 stack section, then take the first markdown table after it.
    m = re.search(r"^##\s*3\.\s.*8-Component Stack.*$", text, re.MULTILINE)
    if not m:
        raise ValueError("AETHERIUS_SPEC_2026.md: §3 8-Component Stack section not found")
    rows: list[dict] = []
    for line in text[m.end():].splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if rows:
                break  # table ended
            continue
        cells = [_strip_md(c) for c in s.strip("|").split("|")]
        if not any(cells):
            continue
        joined = "".join(cells).lower()
        if joined.startswith("layercomponent") or set("".join(cells)) <= set(":- "):
            continue  # header or separator row
        if len(cells) < 5:
            continue
        rows.append({"layer": cells[0], "component": cells[1], "model": cells[2],
                     "trust": cells[3], "purpose": cells[4]})
    return rows


def reconcile_prose(law: dict) -> list[str]:
    """Return a list of drift messages (empty == prose matches the recorded law)."""
    recorded = law.get("prose_table") or []
    parsed = parse_aetherius_table()
    problems: list[str] = []
    if len(parsed) != len(recorded):
        problems.append(f"Aetherius §3 has {len(parsed)} rows but model-law.json records {len(recorded)}")
        return problems
    for i, (p, r) in enumerate(zip(parsed, recorded), 1):
        for k in ("layer", "component", "model", "trust", "purpose"):
            if p.get(k) != r.get(k):
                problems.append(
                    f"row {i} field '{k}': Aetherius spec says {p.get(k)!r} but "
                    f"model-law.json records {r.get(k)!r} — reconcile the spec prose and the source together")
    return problems


# ── vocab validation (reuse the ONE canonical validator; no parallel copy) ──────
def validate_vocab(law: dict) -> list[str]:
    sys.path.insert(0, str(ROOT))
    import lgwks_model_mesh as mesh  # noqa: E402
    problems: list[str] = []
    try:
        built = [mesh._entry(**e) for e in law_entries(law)]
        mesh.validate_mesh({"schema": mesh.SCHEMA, "generated_at": None, "models": built})
    except (TypeError, ValueError) as exc:
        problems.append(f"entries do not conform to {mesh.SCHEMA}: {exc}")
    return problems


# ── catalog parity (the R7.1 gate: catalog keys == law local+current_law, by short name) ──
_CATALOG_RUNTIMES = frozenset({"mlx", "transformers"})
_HUB = ROOT / "lgwks_model_hub.py"


def _catalog_keys() -> set[str]:
    """AST-extract _MODEL_CATALOG keys from lgwks_model_hub without importing it."""
    tree = ast.parse(_HUB.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_MODEL_CATALOG"
            and isinstance(node.value, ast.Dict)
        ):
            return {str(k.value) for k in node.value.keys if isinstance(k, ast.Constant)}
    raise ValueError(f"{_HUB.name}: _MODEL_CATALOG not found")


def check_catalog_parity(law: dict) -> list[str]:
    """Compare catalog keys against law local+current_law (mlx/transformers) by short name.

    Short name = name.split('/')[-1] — the naming convention used throughout the catalog.
    Axiom-Byte-Framework (runtime='axiom') and custom-runtime entries are catalog-exempt.
    """
    law_names = {
        row["entry"]["name"].split("/")[-1]
        for row in law["entries"]
        if row["entry"].get("locality") == "local"
        and row["entry"].get("status") == "current_law"
        and row["entry"].get("runtime") in _CATALOG_RUNTIMES
    }
    catalog = _catalog_keys()
    problems: list[str] = []
    in_law_not_catalog = law_names - catalog
    in_catalog_not_law = catalog - law_names
    if in_law_not_catalog:
        problems.append(
            f"in law current_law but missing from _MODEL_CATALOG: {sorted(in_law_not_catalog)}"
        )
    if in_catalog_not_law:
        problems.append(
            f"in _MODEL_CATALOG but not law current_law: {sorted(in_catalog_not_law)}"
            " — either promote in model-law.json or remove from catalog"
        )
    return problems


# ── commands ────────────────────────────────────────────────────────────────
def cmd_write() -> int:
    law = load_law()
    block = emit_block(law)
    text = TARGET.read_text(encoding="utf-8")
    new = splice(text, block)
    if new == text:
        print(f"model.law: {TARGET.name} already current")
        return 0
    TARGET.write_text(new, encoding="utf-8")
    print(f"model.law: regenerated MESH_LAW in {TARGET.name} ({len(law['entries'])} entries)")
    return 0


def cmd_verify() -> int:
    law = load_law()
    problems: list[str] = []

    # 1. generation freshness — committed block must equal a fresh regeneration.
    text = TARGET.read_text(encoding="utf-8")
    if current_block(text) != emit_block(law):
        problems.append(
            f"{TARGET.name} MESH_LAW block is stale or hand-edited — run "
            "`python3 scripts/gen_model_law.py --write` (never edit the generated block)")

    # 2. vocabulary conformance.
    problems += validate_vocab(law)

    # 3. prose drift.
    problems += reconcile_prose(law)

    # 4. catalog parity — law local+current_law (mlx/transformers) == _MODEL_CATALOG keys.
    problems += check_catalog_parity(law)

    if problems:
        print("model.law: NO-GO")
        for p in problems:
            print(f"  - {p}")
        return 1
    n = len(law["entries"])
    cur = sum(1 for r in law["entries"] if r["entry"].get("status") == "current_law")
    print(f"model.law: GO — {n} entries ({cur} current_law); block fresh, vocab valid, prose reconciled")
    return 0


def cmd_dryrun() -> int:
    law = load_law()
    text = TARGET.read_text(encoding="utf-8")
    if current_block(text) == emit_block(law):
        print("model.law: clean (block matches source)")
    else:
        print("model.law: --write WOULD change lgwks_model_mesh.py MESH_LAW block")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_model_law", description="generate the model law from its canonical source")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true", help="regenerate the MESH_LAW block from source")
    g.add_argument("--verify", action="store_true", help="freshness + vocab + prose-drift gate (the CI gate)")
    args = ap.parse_args(argv)
    if args.write:
        return cmd_write()
    if args.verify:
        return cmd_verify()
    return cmd_dryrun()


if __name__ == "__main__":
    raise SystemExit(main())
