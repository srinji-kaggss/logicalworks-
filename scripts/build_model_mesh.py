#!/usr/bin/env python3
"""build_model_mesh — freeze the model law as a queryable manifest (#119).

Emits `.lgwks/model_mesh.json` (`lgwks.model.mesh.v1`) from the static law in
`lgwks_model_mesh.MESH_LAW`, generated from the one canonical source
`spec/second-harness/model-law.json` (prose anchor: `docs/AETHERIUS_SPEC_2026.md §3`).

This script records inventory; it does NOT change it. It imports no model
package and touches no `store/models/` weights — the mesh is descriptive. The
runtime (doctor) prefers this frozen artifact but rebuilds the same law from
`lgwks_model_mesh.MESH_LAW` when the artifact is absent, so this script is an
optimization + declared-provenance record, never a hard dependency.

Run from repo root:  python3 scripts/build_model_mesh.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / ".lgwks" / "model_mesh.json"


def main() -> int:
    sys.path.insert(0, str(_REPO))
    from lgwks_clock import now_iso
    import lgwks_model_mesh as mesh_mod

    now = now_iso()
    mesh = mesh_mod.build_mesh(generated_at=now)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(mesh, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    n = len(mesh["models"])
    current = sum(1 for m in mesh["models"] if m["status"] == "current_law")
    opens = sum(1 for m in mesh["models"] if m["status"] == "open_slot")
    print(f"wrote {_OUT.relative_to(_REPO)} — {n} entries ({current} current_law, {opens} open_slot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
