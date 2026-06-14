# archive/

Modules moved here were staling (no active callers) or orphaned as of 2026-06-11.
They are NOT deleted — each may have value as a future building block.

Do not import from active code. Do not run their tests in CI until re-integrated.

**Revived to root (no longer archived):** `lgwks_had.py` + `lgwks_algorithms.py` — pulled
back into the live risk path 2026-06-14 (#143, unified abstention engine). Their tests now
live in `tests/`.

| module | reason archived | potential future home |
|---|---|---|
| `lgwks_actor.py` | orphan — U2 Actor contract, no callers yet | U2 (PRD §12 L1) when actor-chain is wired |
| `lgwks_diff.py` | staling — semantic diffing, no callers | PRD-09 review / change detection |
| `lgwks_local_llm.py` | staling — Ollama bridge, superseded by lgwks_embed_port | may be retired entirely |
| `lgwks_math.py` | orphan — algebraic verb signatures, no callers | U1 capability map enrichment |
| `lgwks_monitor.py` | staling — change-detection snapshots, no callers | PRD-07 side-effect capture / U10 |
| `lgwks_sast.py` | staling — CFG + taint engine, no callers | PRD-09 review attenuation |
