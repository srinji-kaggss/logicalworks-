#!/usr/bin/env node
// selftest.mjs — deterministic qualification of the concept algebra (docs/05 §5.3,
// in miniature). It is BOTH a test (exit 0/1) and the evidence that instantiates
// `testability_falsifiability` for Keel's self-hosting profile: a falsifiable claim,
// mechanically checked. A precursor to the full ORG.selftest against known-bad
// fixtures (issue ledger).

import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { evalFormula, evalConcept, atomsOf } from './concepts.mjs';
import { Anchor, H, stableStringify } from './anchor.mjs';
import { atomNode } from './atoms.mjs';
import { mapPool, singleFlight } from './concurrency.mjs';

let fails = 0;
const eq = (got, want, msg) => {
  const g = stableStringify(got), w = stableStringify(want);
  if (g !== w) { console.error(`FAIL ${msg}: got ${g}, want ${w}`); fails++; }
};
const ne = (a, b, msg) => {
  if (stableStringify(a) === stableStringify(b)) { console.error(`FAIL ${msg}: expected DIFFERENT, both ${stableStringify(a)}`); fails++; }
};

// Kleene three-valued truth tables (docs/02 §2.6)
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'true' }), 'true', 'all true');
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'false' }), 'false', 'all: false dominates');
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'unknown' }), 'unknown', 'all: unknown when no false');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'true' }), 'true', 'any: true dominates');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'unknown' }), 'unknown', 'any: unknown when no true');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'false' }), 'false', 'any all false');
eq(evalFormula({ not: 'a' }, { a: 'true' }), 'false', 'not true');
eq(evalFormula({ not: 'a' }, { a: 'unknown' }), 'unknown', 'not unknown');

// unknown ≠ pass: a gated concept over a missing atom is unknown, never true
eq(evalFormula({ all: ['a'] }, {}), 'unknown', 'missing atom => unknown (never silently true)');

// Hallucinated = ¬CoreGroundedCorrect, computed not judged
const halluc = { id: 'Hallucinated', formula: { not: { all: ['referential_truth', 'type_soundness', 'totality_or_controlled_partiality', 'specification_fidelity'] } } };
eq(evalConcept(halluc, { referential_truth: 'false', type_soundness: 'true', totality_or_controlled_partiality: 'true', specification_fidelity: 'true' }).verdict,
   'true', 'unresolved symbol => Hallucinated=true');

// atomsOf collects references
eq([...atomsOf({ all: ['x', { not: 'y' }] })].sort(), ['x', 'y'], 'atomsOf');

// hashing is deterministic and order-insensitive for object keys
eq(H({ a: 1, b: 2 }) === H({ b: 2, a: 1 }), true, 'stable hash (key order)');

// ── node-id injectivity (C1/C2/C3 regression guard): materially-different evidence MUST get
// different node ids, or a broken/advisory verdict can be reused for a passing one. ──
const A = new Anchor(join(tmpdir(), 'keel-selftest-' + process.pid));
const nid = (binding, meta) => { const n = atomNode({ id: 'referential_truth' }, binding, { id: 'u', root: '.', fingerprint: 'fp' }, meta); return A.nodeId(n.kind, n.params, n.inputs); };
const bind = (ev) => ({ atom: 'referential_truth', evidence: ev });
const base = bind({ tool: 'bash', argv: ['-c', 'true'] });
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c true'] })), 'argv element boundaries change the id (C1)');
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c', 'true'], cwd: 'x' })), 'cwd changes the id (C2)');
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c', 'true'], env: { K: '1' } })), 'env changes the id (C2)');
ne(nid(base, { source: 'V1' }), nid(base, { source: 'V2' }), 'distinct verifier sources are distinct nodes (C3)');
ne(nid(base, { source: 'V', advisory: true }), nid(base, { source: 'V', advisory: false }), 'advisory channel is namespaced from gated (C3)');
eq(nid(base, { source: 'V' }) === nid(base, { source: 'V' }), true, 'identical evidence+source ⇒ identical id (reuse still works)');

// ── concurrency primitives (docs/07 §7.4): the seam that licenses crossing in parallel ──
async function concurrencyTests() {
  // mapPool resolves in INPUT order regardless of finish order (deterministic aggregation)
  const out = await mapPool([3, 1, 2], 3, async (n) => { await tick(n); return n * 10; });
  eq(out, [30, 10, 20], 'mapPool preserves input order under out-of-order completion');

  // a thrown worker is isolated as __poolError, never aborts the crossing (engine maps → unknown)
  const mixed = await mapPool([1, 2], 2, async (n) => { if (n === 1) throw new Error('boom'); return n; });
  eq(mixed[0] && mixed[0].__poolError instanceof Error, true, 'mapPool isolates a thrown crossing point');
  eq(mixed[1], 2, 'mapPool: a sibling fault does not poison other points');

  // bound is respected: at most `limit` in flight at once
  let live = 0, peak = 0;
  await mapPool([0, 0, 0, 0, 0], 2, async () => { live++; peak = Math.max(peak, live); await tick(1); live--; });
  eq(peak <= 2, true, 'mapPool never exceeds the concurrency bound');

  // singleFlight collapses identical concurrent keys to one computation
  let calls = 0;
  const once = singleFlight();
  const compute = async () => { calls++; await tick(1); return 'v'; };
  const [a, b] = await Promise.all([once('k', compute), once('k', compute)]);
  eq([a, b, calls], ['v', 'v', 1], 'singleFlight computes a concurrent key exactly once');
}
const tick = (n) => new Promise((r) => setImmediate(() => (n > 1 ? tick(n - 1).then(r) : r())));

concurrencyTests().then(() => {
  if (fails) { console.error(`selftest: ${fails} failed`); process.exit(1); }
  console.log('selftest: ok (algebra + hashing + concurrency qualified)');
}).catch((e) => { console.error('selftest harness fault:', e); process.exit(2); });
