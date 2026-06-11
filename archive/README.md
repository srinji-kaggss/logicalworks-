# archive/

Modules moved here were staling (no active callers) or orphaned as of 2026-06-11.
They are NOT deleted — each may have value as a future building block.

Do not import from active code. Do not run their tests in CI until re-integrated.

| module | reason archived | potential future home |
|---|---|---|
| `lgwks_actor.py` | orphan — U2 Actor contract, no callers yet | U2 (PRD §12 L1) when actor-chain is wired |
| `lgwks_algorithms.py` | staling — L4 narrow-ML catalog, no callers | L4 subconscious engine (PRD-06) |
| `lgwks_diff.py` | staling — semantic diffing, no callers | PRD-09 review / change detection |
| `lgwks_had.py` | staling — Human Assumption Decoder, no callers | PRD-06 subconscious engine (intent math) |
| `lgwks_local_llm.py` | staling — Ollama bridge, superseded by lgwks_embed_port | may be retired entirely |
| `lgwks_math.py` | orphan — algebraic verb signatures, no callers | U1 capability map enrichment |
| `lgwks_monitor.py` | staling — change-detection snapshots, no callers | PRD-07 side-effect capture / U10 |
| `lgwks_sast.py` | staling — CFG + taint engine, no callers | PRD-09 review attenuation |
