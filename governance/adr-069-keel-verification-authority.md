# ADR 069: Keel adopted as the verification authority

**Date**: 2026-06-17
**Status**: Accepted

## Context
As part of our commitment to DO-178B deterministic standards and to replace human review at the verification floor, we require a verification authority. Keel provides a standalone, deterministic verification engine (the "three-valued algebra").

## Decision
We adopt Keel as the verification authority for the `lgwks` codebase.
- **Vendored-not-forked:** Keel's `src/` and `schema/` directories are directly vendored into `lgwks_verify/keel/` from the upstream `~/keel` repository. We do not fork it; we pull updates via a byte-for-byte copy.
- **Contract is the seam:** `lgwks` binds to Keel strictly through the `run.mjs` and `--machine` contract. `lgwks verify` shells out to the vendored script. Keel's output (verdict, crossing coverage, and advisories) is the authoritative signal for our CI pipeline.
- **Unified Risk Engine:** Keel advisories are routed seamlessly into the existing `lgwks_had.py` abstention engine. A Keel advisory corresponds to the "confirm" tier, ensuring that failures to satisfy advisory bounds trigger human review rather than silent failures.
- **Drift Protection:** The `VENDORED.txt` file records the SHA of the upstream Keel repository. Any synchronization must ensure byte-identity with the upstream kernel.

## Cross-links
- This ADR resolves lgwks issue #235.
- Cross-links to kernel epic #639.
- Connects to kernel #651 (embedding proposer) which is routed as evidence.
- Integrates with lgwks #143 (risk/abstention engine) for surfacing advisories.