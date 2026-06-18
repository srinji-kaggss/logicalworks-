// engine.mjs — the shared verdict core (the basement; docs/01 §1, docs/02 §2.6).
//
// One place computes a verdict, for EVERY front-end (profile, kernel-registry, …). A
// front-end's only job is to produce ACTIVATIONS — flat (atom, unit, binding) triples —
// and a gate concept; the engine evaluates each as a content-addressed node, aggregates
// per-atom with three-valued ∧, and composes the gate. Determinism: identity is content,
// no wall-clock, no randomness. Standalone: only Node builtins + Keel's own modules.

import { globSync } from 'node:fs';
import { join } from 'node:path';
import { H, hashFile } from './anchor.mjs';
import { atomNode } from './atoms.mjs';
import { evalConcept } from './concepts.mjs';
import { mapPool, defaultConcurrency } from './concurrency.mjs';

export const SRC_GLOBS = ['**/*.mjs', '**/*.js', '**/*.ts', '**/*.rs', '**/*.py', '**/*.toml'];
export const EXCLUDE = ['/.git/', '/.keel/', '/node_modules/', '/target/', '/.worktrees/'];

/** Content fingerprint of a unit dir: hash of sorted [relpath, contentHash] (staleness spine). */
export function contentFingerprint(dir, { globs = SRC_GLOBS, exclude = EXCLUDE } = {}) {
  const files = [];
  for (const pat of globs) {
    for (const f of globSync(pat, { cwd: dir })) {
      if (exclude.some(x => ('/' + f + '/').includes(x))) continue;
      files.push([f, hashFile(join(dir, f))]);
    }
  }
  files.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  return H(files);
}

/** Three-valued ∧ aggregating one atom across its units: false dominates, then unknown. */
export function kleeneAll(vs) {
  return vs.includes('false') ? 'false' : vs.includes('unknown') ? 'unknown' : 'true';
}

/** Collect the atom ids a concept formula references. */
export function collectAtoms(f, acc = new Set()) {
  if (typeof f === 'string') acc.add(f);
  else if (f.all) f.all.forEach(x => collectAtoms(x, acc));
  else if (f.any) f.any.forEach(x => collectAtoms(x, acc));
  else if (f.not) collectAtoms(f.not, acc);
  return acc;
}

/**
 * The engine core. Given a flat list of ACTIVATIONS, evaluate every one as a
 * content-addressed node through the anchor — CONCURRENTLY, with at most `concurrency`
 * tools running at once (concurrency.mjs) — aggregate per-atom across its units with
 * three-valued ∧, fill any gate-referenced atom that was never activated with 'unknown'
 * (unknown ≠ pass; docs/02 §2.6), and compose the gate concept. The single calculator-test
 * core — the only place a verdict is computed.
 *
 * Concurrency is sound here because identity is CONTENT: a node's verdict and id do not
 * depend on evaluation order, so crossing the activation set in parallel yields the
 * identical composed verdict as crossing it serially (docs/07 §7.4).
 *
 * ADVISORY activations (act.advisory === true) are evaluated and surfaced but are EXCLUDED
 * from the gate's atom values — the seam (docs/05 §5.5) that lets a non-deterministic or
 * proposer signal share the ontology without ever flipping GO→NO-GO.
 *
 * activation = { atomId, atomDef, binding|null, unit, source?, advisory?, role? }
 * returns    = { gate, atomValues, atoms, advisories, crossing, recomputed, reused }
 */
export async function composeReport({ activations, gate, anchor, concurrency = defaultConcurrency() }) {
  const evaluated = await mapPool(activations, concurrency, async (act) => {
    // pass the channel meta so the node id is namespaced by advisory/source (engine never lets
    // an advisory node's verdict be reused by a gated atom — C3 defence-in-depth in atoms.mjs).
    const node = atomNode(act.atomDef, act.binding, act.unit, { advisory: act.advisory, source: act.source });
    const res = await anchor.evaluateAsync(node);
    return { act, verdict: res.verdict, cached: res.cached };
  });

  const perAtom = {};
  const atoms = [];
  const advisories = [];
  let crossedPoints = 0, crossedFalse = 0, crossedUnknown = 0;
  for (let i = 0; i < evaluated.length; i++) {
    const e = evaluated[i];
    const act = activations[i];
    // a thrown evaluator is unknown, never a silent pass (docs/02 §2.6)
    const verdict = e.__poolError ? { value: 'unknown', reason: `evaluator fault: ${e.__poolError.message}` } : e.verdict;
    const points = verdict.points || [];
    crossedPoints += points.length || 1;
    crossedFalse += points.filter(p => p.value === 'false').length;
    crossedUnknown += points.filter(p => p.value === 'unknown').length;
    const row = {
      atom: act.atomId, unit: act.unit.id, value: verdict.value,
      reason: verdict.reason, cached: e.cached, source: act.source,
      points: points.length > 1 ? points.map(p => ({ label: p.label, value: p.value })) : undefined,
    };
    if (act.advisory) { advisories.push({ ...row, role: act.role }); continue; }
    atoms.push(row);
    (perAtom[act.atomId] ||= []).push(verdict.value);
  }

  const atomValues = {};
  for (const id of Object.keys(perAtom)) atomValues[id] = kleeneAll(perAtom[id]);
  for (const id of collectAtoms(gate.formula)) if (!(id in atomValues)) atomValues[id] = 'unknown';
  return {
    gate: evalConcept(gate, atomValues), atomValues, atoms, advisories,
    crossing: { points: crossedPoints, failed: crossedFalse, unknown: crossedUnknown },
    recomputed: anchor.recomputed, reused: anchor.reused,
  };
}

/**
 * Coverage instrument (the H1 measurement): of the full atom ontology, how many carry a
 * DEFINITE verdict (true|false — i.e. evidence actually ran) vs are 'unknown' (unbound or
 * tool-absent). This is the honest denominator — unknown is NEVER counted as covered.
 */
export function coverage(atomsDoc, atomValues) {
  const all = atomsDoc.atoms.map(a => a.id);
  const definite = all.filter(id => atomValues[id] === 'true' || atomValues[id] === 'false');
  const unknown = all.filter(id => !(atomValues[id] === 'true' || atomValues[id] === 'false'));
  return {
    total: all.length,
    covered: definite.length,
    uncovered: unknown.length,
    ratio: definite.length / all.length,
    covered_atoms: definite,
    uncovered_atoms: unknown,
  };
}
