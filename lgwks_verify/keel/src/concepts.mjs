// concepts.mjs — the concept algebra (docs/02 §2.3).
//
// A concept is a formula over atom ids:  atomId | {all:[…]} | {any:[…]} | {not:f}
// Evaluated in three-valued (Kleene) logic over atom values 'true'|'false'|'unknown'
// (docs/02 §2.6). 'unknown' is never silently 'true': a gated concept that evaluates
// to 'unknown' is a BLOCK upstream (run.mjs), not a pass.
//
// The algebra is deterministic and associative — the calculator test. It runs in the
// engine; only the result (verdict + failing atoms) crosses to a projection.

const T = 'true', F = 'false', U = 'unknown';

/** Collect the atom ids a formula references (so the runner knows what to gather). */
export function atomsOf(formula, acc = new Set()) {
  if (typeof formula === 'string') acc.add(formula);
  else if (formula.all) formula.all.forEach(f => atomsOf(f, acc));
  else if (formula.any) formula.any.forEach(f => atomsOf(f, acc));
  else if (formula.not) atomsOf(formula.not, acc);
  return acc;
}

/** Evaluate a formula given values: { atomId -> 'true'|'false'|'unknown' }. */
export function evalFormula(formula, values) {
  if (typeof formula === 'string') return values[formula] ?? U;
  if (formula.all) return kleeneAll(formula.all.map(f => evalFormula(f, values)));
  if (formula.any) return kleeneAny(formula.any.map(f => evalFormula(f, values)));
  if (formula.not) return kleeneNot(evalFormula(formula.not, values));
  throw new Error('malformed concept formula: ' + JSON.stringify(formula));
}

function kleeneAll(vs) { // ∧: false dominates, then unknown, else true
  if (vs.includes(F)) return F;
  if (vs.includes(U)) return U;
  return T;
}
function kleeneAny(vs) { // ∨: true dominates, then unknown, else false
  if (vs.includes(T)) return T;
  if (vs.includes(U)) return U;
  return F;
}
function kleeneNot(v) { return v === T ? F : v === F ? T : U; }

/**
 * Evaluate a concept against atom values and report the atoms responsible for a
 * non-true verdict — the surprise-weighted payload a projection actually needs.
 */
export function evalConcept(concept, values) {
  const verdict = evalFormula(concept.formula, values);
  const referenced = [...atomsOf(concept.formula)];
  const offenders = referenced.filter(a => (values[a] ?? U) !== T)
    .map(a => ({ atom: a, value: values[a] ?? U }));
  return { concept: concept.id, verdict, offenders };
}
