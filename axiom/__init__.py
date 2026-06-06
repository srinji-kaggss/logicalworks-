"""
axiom — the standalone byte framework for the Axiom machine-first ISA.

TRULY INDEPENDENT OF EVERYTHING ABOVE IT. This package imports nothing upward — no CLI, no lgwks, no
gauges, no weights, no AI, no network, no filesystem. Stdlib only. Consumers (the lgwks CLI, the gauge/
weight layer) sit ON TOP and import this; this imports none of them. Delete everything above and the byte
framework still stands and still verifies. Bottom-up by construction.

Grounded in the fundamentals that make WASM and the JVM work (STUDY-isa-wasm-jvm-to-machine-first.md):
  varint  — LEB128 base-128 varints (WASM lengths/indices)
  wire    — canonical TLV, deterministic ordering, forward-compatible unknown-field skip
  cid     — content-address over canonical bytes (BLAKE3-256 canon; blake2b stand-in until blake3 wired)
  capsule — the typed Claim/Hole record, closed kind vocabulary
  verify  — the decidable click (enum∈ + capability⊆ + interval + base-first), single-pass, edge-runnable
  fabric  — immutable content-addressed DAG + checkout refs + hash-chained log (git/GDrive model, SPEC §14)

Hardened against AUDIT-axiom-byte-framework-adversarial.md (pen-test FAIL at first-pass). Every audit exploit
has a mirrored negative test. Determinism: no wall-clock / no randomness in the core; logical time only.
"""
