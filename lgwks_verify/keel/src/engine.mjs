// engine.mjs — the shared verdict core (the basement; docs/01 §1, docs/02 §2.6).
//
// One place computes a verdict, for EVERY front-end (profile, kernel-registry, …). A
// front-end's only job is to produce ACTIVATIONS — flat (atom, unit, binding) triples —
// and a gate concept; the engine evaluates each as a content-addressed node, aggregates
// per-atom with three-valued ∧, and composes the gate. Determinism: identity is content,
// no wall-clock, no randomness. Standalone: only Node builtins + Keel's own modules.

import { globFingerprint, SRC_GLOBS, EXCLUDE } from './anchor.mjs';
import { atomNode } from './atoms.mjs';
import { evalConcept, evalFormula } from './concepts.mjs';
import { mapPool, defaultConcurrency } from './concurrency.mjs';

// Re-exported for back-compat (front-ends import these from engine). The single definition lives
// in anchor.mjs so binding-scope fingerprinting (atoms.mjs) shares it — never a divergent copy.
export { SRC_GLOBS, EXCLUDE } from './anchor.mjs';

/** Content fingerprint of a whole unit dir: every source file (the coarsest, default scope).
 *  A binding may narrow this to its own `scope` (atoms.unitFingerprint) for finer staleness. */
export function contentFingerprint(dir, { globs = SRC_GLOBS, exclude = EXCLUDE } = {}) {
  return globFingerprint(dir, globs, exclude);
}

/** Three-valued ∧ aggregating one atom across its units: false dominates, then unknown. */
export function kleeneAll(vs) {
  return vs.includes('false') ? 'false' : vs.includes('unknown') ? 'unknown' : 'true';
}

/** Cross a graded atom's score to a three-valued floor verdict against a profile threshold
 *  (docs/02 §2.5, #648 item 8). No measurement OR no declared threshold => 'unknown' (the bar is
 *  the auditor's parameter; absence of a bar blocks, it never silently passes). */
export function crossGraded(score, threshold) {
  if (typeof score !== 'number' || Number.isNaN(score)) return 'unknown';
  if (typeof threshold !== 'number') return 'unknown';
  return score >= threshold ? 'true' : 'false';
}

/**
 * Claim-coherence (the punishing gate; docs/09): you may CLAIM only what you DEMONSTRATED.
 * Given the formula of the concept a profile asserts it meets (`assurance_claim`) and the measured
 * atom values, find every atom the claim rests on that has NO definite evidence (unknown/unrun/
 * unbound). If any exist the claim OUTRUNS the evidence — the run must BLOCK, regardless of how
 * narrow the enforced `gate_concept` was. This is "deeply punishing of overclaim, without being
 * overhot": it fires ONLY when you explicitly assert a claim, and only on the gap between assertion
 * and demonstration — an honest `unknown` on something you never claimed does not block.
 *
 * A claim is DEMONSTRATED only when its concept formula actually HOLDS under the measured values —
 * not merely when every atom was measured. Two honest failure modes are kept distinct:
 *   - `undemonstrated` (claim formula 'unknown' — a claimed atom is unrun/unbound): the claim
 *     OUTRAN its evidence ⇒ BLOCK.
 *   - `refuted` (claim formula 'false' under measured atoms): the evidence DISPROVES the claim
 *     ⇒ NO-GO.
 * Prior bug (Open Risk #4, 2026-06-21 handoff): only `unknown` atoms counted as undemonstrated, so
 * a claimed atom measured FALSE was reported "coherent / demonstrated" — overclaim dressed as proof.
 * Now a false claimed atom that breaks the formula refutes the claim.
 * Returns { coherent, claimValue, claimedAtoms, undemonstrated, refuted, refutingAtoms }.
 */
export function claimCoherence(claimFormula, atomValues) {
  const claimedAtoms = [...collectAtoms(claimFormula)];
  const undemonstrated = claimedAtoms.filter((id) => atomValues[id] !== 'true' && atomValues[id] !== 'false');
  const claimValue = evalFormula(claimFormula, atomValues);
  return {
    coherent: claimValue === 'true',
    claimValue,
    claimedAtoms,
    undemonstrated,
    refuted: claimValue === 'false',
    refutingAtoms: claimValue === 'false' ? claimedAtoms.filter((id) => atomValues[id] === 'false') : [],
  };
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
export async function composeReport({ activations, gate, anchor, concurrency = defaultConcurrency(), thresholds = {}, policy = null }) {
  const evaluated = await mapPool(activations, concurrency, async (act) => {
    // pass the channel meta so the node id is namespaced by advisory/source (engine never lets
    // an advisory node's verdict be reused by a gated atom — C3 defence-in-depth in atoms.mjs).
    // `policy` (execution_policy) confines the evidence run's env (R#3); it does not affect the
    // node id (the binding's declared env still does), only which ambient vars the tool can read.
    const node = atomNode(act.atomDef, act.binding, act.unit, { advisory: act.advisory, source: act.source, policy });
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
    // GRADED threshold crossing (#648 item 8): the cached score crosses to boolean HERE, in
    // post-process, against the profile threshold — keeping the bar out of the cached node so
    // re-bar never re-runs the tool. No bar => unknown (blocks, never silently passes).
    let value = verdict.value, graded;
    if (act.atomDef?.kind === 'graded' && verdict.value === 'graded') {
      const threshold = thresholds[act.atomId];
      value = crossGraded(verdict.score, threshold);
      graded = { score: verdict.score, threshold };
    }
    const row = {
      atom: act.atomId, unit: act.unit.id, value,
      reason: (value === 'unknown' && graded && graded.threshold === undefined)
        ? `graded score ${graded.score} but no profile threshold — set thresholds['${act.atomId}'] (docs/02 §2.5)`
        : verdict.reason,
      score: graded?.score, threshold: graded?.threshold,
      cached: e.cached, source: act.source,
      points: points.length > 1 ? points.map(p => ({ label: p.label, value: p.value, score: p.score })) : undefined,
    };
    if (act.advisory) { advisories.push({ ...row, role: act.role }); continue; }
    atoms.push(row);
    (perAtom[act.atomId] ||= []).push(value);
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
