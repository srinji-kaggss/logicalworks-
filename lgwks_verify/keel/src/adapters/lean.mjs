// adapters/lean.mjs — the `tool: lean` seam: machine-check a Lean proof and graft it onto the
// anchor DAG as a content-addressed proof-term node (issue ledger item 6 / #646; docs/05 §5.2).
//
// Lean is REFERENCE, NEVER FORKED (Braid covenant). Keel runs `lake build` on the pinned
// package and reads ONE three-valued result (docs/02 §2.6) — it does not parse, embed, or
// reimplement Lean's kernel:
//   true    — `lake build` exited 0: the Lean kernel certified every proof term in the package.
//   false   — `lake build` exited nonzero: a proof failed to typecheck (drift / regression).
//   unknown — the toolchain is absent (no `lake` on PATH): we did not learn the answer. NEVER a
//             pass (the no-silent-under-check discipline, docs/02 §2.6).
//
// PURCHASABLE / DEFERRED (docs/05 §5.2 sequencing principle): a missing toolchain degrades to
// `unknown` and NEVER blocks the content-addressed floor. Lean depth is grafted ONTO the floor,
// not a prerequisite for it. The structural concept↔Lean conformance check (src/conformance.mjs)
// runs with zero dependencies and continues to gate even when this machine-check is skipped.
//
// The proof-term node's id folds in the CONTENT of the .lean sources + the toolchain pin + the
// grafted theorem names, so the proof TERM itself addresses the node: change the proof, change
// the id (the staleness spine, docs/01 §1.3). This is materially stronger than binding a generic
// atom node (atoms.mjs) to the lean directory as a `unit`, whose fingerprint would hash only the
// dir's path/size — not the proof text. That is why a Lean proof gets a dedicated node kind.

import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { H } from '../anchor.mjs';

export const LEAN_TOOL = 'lake';
const MAXBUF = 64 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 600_000;

/** Is the Lean build tool (`lake`) on PATH? Absence ⇒ the proof check is `unknown`, never pass. */
export function leanToolPresent(env = process.env) {
  return spawnSync('bash', ['-c', `command -v ${LEAN_TOOL}`], { env }).status === 0;
}

/**
 * Content fingerprint of the proof inputs: each module's source bytes + the toolchain pin.
 * A missing source hashes to '∅' (referential-truth-friendly; a vanished proof is never a
 * silent skip). Returned alongside the verdict so a reader can trace WHAT was checked.
 */
export function proofFingerprint(packageDir, modules) {
  const sources = modules.map((rel) => {
    try { return { module: rel, hash: H(readFileSync(join(packageDir, rel))) }; }
    catch { return { module: rel, hash: '∅' }; }
  });
  let toolchain = '';
  try { toolchain = readFileSync(join(packageDir, 'lean-toolchain'), 'utf8').trim(); } catch { /* unpinned */ }
  return { sources, toolchain };
}

/**
 * Run `lake build` on a Lean package; return a three-valued result.
 * { value:'true'|'false'|'unknown', present, exit?, reason?, log? }.
 * present=false ⇒ toolchain absent ⇒ value 'unknown' (purchasable; never blocks the floor).
 */
export function leanBuild(packageDir, { env = process.env, timeout = DEFAULT_TIMEOUT_MS } = {}) {
  if (!leanToolPresent(env))
    return { value: 'unknown', present: false, reason: `toolchain absent: ${LEAN_TOOL} (Lean depth is purchasable, docs/05 §5.2; the structural conformance check still gates)` };
  const r = spawnSync(LEAN_TOOL, ['build'], { cwd: packageDir, env, encoding: 'utf8', timeout, maxBuffer: MAXBUF });
  if (r.error) return { value: 'unknown', present: true, reason: `${LEAN_TOOL} failed to launch: ${r.error.message}` };
  const ok = r.status === 0;
  return {
    value: ok ? 'true' : 'false', present: true, exit: r.status,
    reason: ok ? undefined : `${LEAN_TOOL} build exited ${r.status} — a proof term failed to typecheck`,
    log: ok ? undefined : (r.stderr || r.stdout || '').slice(-2000),
  };
}

/**
 * The proof-term node: a content-addressed anchor node grafting a Lean proof onto the verdict
 * DAG (docs/05 §5.2). Pass it to `anchor.evaluate(node)` like any other node — its verdict is
 * cached keyed by the proof-source content, so an unchanged proof is never re-built.
 *
 * opts: { packageDir, modules:[relPath...], theorems?:[name...], env? }
 *   - modules  : the .lean files whose content addresses the node (the proof sources).
 *   - theorems : the grafted theorem names (provenance; e.g. ['excellent_not_hallucinated']).
 *                Part of the id so re-pointing the same sources at a different claim is a new node.
 */
export function leanProofNode({ packageDir, modules, theorems = [], env = process.env }) {
  const fp = proofFingerprint(packageDir, modules);
  const thms = [...theorems].sort();
  // IDENTITY = proof content, never location. params + inputs both feed anchor.nodeId, so the
  // volatile packageDir path MUST NOT appear here — only the module relpaths (folded into the
  // source fingerprint) and the grafted theorems. Same proof bytes anywhere ⇒ same node id.
  return {
    kind: 'lean:proof',
    params: { theorems: thms, modules: [...modules].sort() },
    inputs: [H('lean/proof/v1', { sources: fp.sources, toolchain: fp.toolchain, theorems: thms })],
    compute() {
      const r = leanBuild(packageDir, { env });
      return { value: r.value, present: r.present, reason: r.reason, theorems: thms, proof: fp };
    },
  };
}
