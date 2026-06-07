# Axiom end-to-end framework slice

Date: 2026-06-06
Status: first CLI harness slice

## Research grounding

The build direction is JVM-like, not "chatbot-like":

- The JVM split source language from class-file artifact and verifier. lgwks mirrors that split as
  human/AI intent -> Axiom capsule bytes -> verifier click -> fabric.
- WebAssembly validation keeps untrusted producers consumable by checking a module before execution. lgwks
  uses the same rule: untrusted authors may propose, but the artifact must validate before it attaches.
- MLIR's dialect model is the right mental frame for future lowering: Axiom is the stable verified dialect;
  repo, research, comms, and health gauges are upper dialects; WASM/AOC/etc. are lower targets.

Primary references used for this slice:

- Oracle JVM Specification, Java SE 21, "The class File Format" and "Verification of class Files":
  https://docs.oracle.com/javase/specs/jvms/se21/html/index.html
- WebAssembly Core Specification, validation:
  https://webassembly.github.io/spec/core/
- MLIR Language Reference and Dialects:
  https://mlir.llvm.org/docs/LangRef/
  https://mlir.llvm.org/docs/Dialects/

## Layer map

```text
L7 UX / CLI             lgwks axiom capture/check/doctor
L6 Harness sensors      git status, diff, test exit code, tool metadata
L5 Divergence radar     narration claim vs captured emissions
L4 Portal/comms/gauges  future folds over emissions, not model prose
L3 Axiom capsule        canonical Claim/Hole byte artifact
L2 Axiom verifier       enum + lineage + interval + base-first click
L1 Fabric               immutable CID DAG + hash-chained log
L0 Lowering/runtime     future WASM/MLIR/AOC target; unbuilt
```

`axiom/` remains the JVM-classfile equivalent: stable byte format and verifier. `lgwks_axiom.py` is the
classloader/harness equivalent: it observes the host world and turns facts into artifacts.

## What landed

`lgwks axiom capture`

- Captures git repo facts: repo validity, branch, head, status, diff.
- Optionally runs one test command and captures return code plus bounded output tails.
- Emits every fact as an Axiom `evidence` capsule rooted in a signed harness genesis.
- Persists:
  - `.lgwks/axiom/runs/<run>/emissions.jsonl`
  - `.lgwks/axiom/runs/<run>/fabric-log.json`
  - `.lgwks/axiom/runs/<run>/packet.json`

`lgwks axiom check`

- Compares a narration claim against captured emissions.
- Current first radar checks:
  - "tests passed" requires a captured test command with return code 0.
  - "implemented/changed/modified" requires captured dirty status or diff files.
  - "clean worktree/no changes" requires captured dirty count 0.

`lgwks axiom replay`

- Reloads persisted `emissions.jsonl` bytes into a fresh fabric.
- Recomputes each capsule CID from canonical bytes.
- Reconstructs the hash-chained fabric log.
- Fails if emission bytes, CIDs, or `fabric-log.json` were tampered.

`lgwks axiom doctor`

- Verifies the byte layer does not import upward `lgwks*` modules.

## CLI experience gaps identified

1. The root `lgwks` entrypoint is still too large. New verbs are registered manually in one dense parser
   block. This works, but the experience gap is discoverability and reviewability.
2. There is no universal run packet yet. `capture`, `session`, `run`, `portal`, and `axiom` all persist
   adjacent artifacts with different shapes. The next CLI spine should normalize these under one run index.
3. Machine mode exists, but command output contracts are still per-command. `lgwks axiom capture --json`
   is structured; the next step is adding it to `manifest --for-agent` so agents discover it without help
   probing.
4. Divergence checks are still keyword-level. The important invariant is correct now, because Channel B is
   captured emissions, but the claim parser should become a typed `NarrationClaim` capsule instead of string
   matching.
5. The harness can run one test command, not a test matrix. The next JVM-style step is a deterministic
   "test suite descriptor" so multiple commands become one verified method-table, not ad hoc shell strings.

## Next build tranche

1. Add `axiom` to the agent manifest with expected JSON schemas.
2. Add a run index under `.lgwks/runs/` that links session/capture/portal/axiom packets by CID.
3. Replace string narration matching with typed narration capsules.
4. Add `lgwks axiom test-matrix` for multiple test commands with bounded output, timeout, and deterministic
   labels.
