// conformance.mjs — concept↔Lean conformance (issue ledger #645 item 7; docs/02 §2.4).
//
// The framework's three canonical concepts (CoreGroundedCorrect / Hallucinated / Excellent)
// have TWO declarations that must never disagree:
//   • the formal skeleton in `lean/ExcellentCode/Framework.lean` (the authority), and
//   • the machine-readable formulas in `schema/concepts.json` (what the engine evaluates).
// A "slight difference" between them is precisely the bug Keel exists to catch, turned on
// Keel itself. This module RE-DERIVES the three concepts from the Lean skeleton and asserts
// the JSON formulas are structurally identical — same atom leaf-set, same boolean shape.
//
// SCOPE: this module verifies STRUCTURAL agreement between the two declared artifacts — it does
// NOT run Lean. "Conformance passes" means "the JSON did not drift from the declared Lean
// skeleton". The COMPLEMENTARY check that the skeleton itself TYPECHECKS is now `lake build` via
// the `tool: lean` seam (src/adapters/lean.mjs), run as the `lean-skeleton-machinecheck` row in
// qualify.mjs (#646, ledger item 6 — the #645 residual is closed). Together: this proves the JSON
// matches the Lean; that proves the Lean is sound. This zero-dep check is the always-on gate;
// the machine-check degrades to SKIP when the toolchain is absent (Lean depth is purchasable).
// The check fails LOUDLY on any drift or on a Lean construct it cannot interpret (no silent
// under-check — the assertSchemaSupported discipline).

import { stableStringify } from './anchor.mjs';

const FRAMEWORK_CONCEPTS = ['CoreGroundedCorrect', 'Hallucinated', 'Excellent'];

/** Strip Lean comments so identifiers inside prose ("`holds a`") are never parsed as code. */
function stripComments(src) {
  // block comments /- ... -/ (covers /-- docstrings -/; this skeleton does not nest them)
  let s = src.replace(/\/-[\s\S]*?-\//g, ' ');
  // line comments -- ... (after block strip; no '--' appears inside code here)
  s = s.replace(/--[^\n]*/g, ' ');
  return s;
}

/** Constructor ids of `inductive Atom where | a | b ... deriving ...` — the atom universe. */
function parseAtomUniverse(stripped) {
  const m = stripped.match(/inductive\s+Atom\s+where([\s\S]*?)deriving\b/);
  if (!m) throw new Error('conformance: could not locate `inductive Atom where ... deriving`');
  return [...m[1].matchAll(/\|\s*([a-z_][a-zA-Z0-9_]*)/g)].map((x) => x[1]);
}

/** Capture a `def <Name> ... := <body>` body, up to the next top-level keyword or EOF. */
function defBody(stripped, name) {
  const re = new RegExp(`def\\s+${name}\\b[\\s\\S]*?:=([\\s\\S]*?)(?=\\n\\s*(?:def|theorem|end)\\b|$)`);
  const m = stripped.match(re);
  if (!m) throw new Error(`conformance: def ${name} not found in Framework.lean`);
  return m[1];
}

/**
 * Parse one def body into a raw shape:
 *   { op: 'not', ref: 'OtherDef' }  — a negation of another framework def
 *   { op: 'all'|'any', atoms: [...] } — a conjunction/disjunction over `holds <atom>`
 * Throws on a construct it cannot interpret (mixed ∧/∨, empty, unrecognized).
 */
function parseDef(body, name) {
  const neg = body.match(/¬\s*([A-Z][A-Za-z0-9_]*)/);
  if (neg) {
    // a pure negation of another def: there must be no bare `holds <atom>` conjuncts
    if (/holds\s+[a-z_]/.test(body))
      throw new Error(`conformance: def ${name} mixes ¬<Def> with holds-atoms — not interpretable`);
    return { op: 'not', ref: neg[1] };
  }
  const atoms = [...body.matchAll(/holds\s+([a-z_][a-zA-Z0-9_]*)/g)].map((m) => m[1]);
  if (!atoms.length) throw new Error(`conformance: def ${name} references no atoms and no negation`);
  const hasAnd = body.includes('∧'), hasOr = body.includes('∨');
  if (hasAnd && hasOr) throw new Error(`conformance: def ${name} mixes ∧ and ∨ — unsupported shape`);
  if (atoms.length > 1 && !hasAnd && !hasOr)
    throw new Error(`conformance: def ${name} lists multiple atoms with no ∧/∨ connective`);
  return { op: hasOr ? 'any' : 'all', atoms };
}

/** Parse the three framework defs + the atom universe from Framework.lean source text. */
export function parseLeanFramework(src) {
  const stripped = stripComments(src);
  const universe = parseAtomUniverse(stripped);
  const defs = {};
  for (const name of FRAMEWORK_CONCEPTS) defs[name] = parseDef(defBody(stripped, name), name);
  return { universe, defs };
}

/** Canonicalize a Lean raw shape to {op, atoms:sorted} | {op:'not', child}, resolving refs. */
function leanShape(name, defs, seen = new Set()) {
  if (seen.has(name)) throw new Error(`conformance: cyclic Lean def reference at ${name}`);
  seen.add(name);
  const d = defs[name];
  if (!d) throw new Error(`conformance: Lean def ${name} referenced but not parsed`);
  if (d.op === 'not') return { op: 'not', child: leanShape(d.ref, defs, seen) };
  return { op: d.op, atoms: [...d.atoms].sort() };
}

/** Canonicalize a concepts.json formula to the same shape grammar. */
function jsonShape(f, ctx) {
  if (typeof f === 'string') return { op: 'all', atoms: [f] }; // a bare atom = singleton conjunction
  if (f && f.not !== undefined) return { op: 'not', child: jsonShape(f.not, ctx) };
  for (const op of ['all', 'any']) {
    if (Array.isArray(f && f[op])) {
      const atoms = [];
      for (const child of f[op]) {
        if (typeof child === 'string') atoms.push(child);
        else throw new Error(`conformance: ${ctx} JSON formula nests a non-atom under ${op} — framework concepts must be flat`);
      }
      return { op, atoms: atoms.sort() };
    }
  }
  throw new Error(`conformance: ${ctx} JSON formula is not an interpretable shape: ${stableStringify(f)}`);
}

/**
 * Check concepts.json against the Lean skeleton.
 * @returns { ok: boolean, discrepancies: string[], checked: string[] }
 */
export function checkConformance({ conceptsDoc, leanText, atomsDoc }) {
  const discrepancies = [];
  const checked = [];
  const { universe, defs } = parseLeanFramework(leanText);

  const atomIds = new Set((atomsDoc.atoms || []).map((a) => a.id));

  // (1) the Lean atom universe must be exactly the schema's 20 atoms (no phantom, none missing).
  const uniSet = new Set(universe);
  for (const id of universe) if (!atomIds.has(id)) discrepancies.push(`Lean Atom universe declares '${id}', not in schema/atoms.json`);
  for (const id of atomIds) if (!uniSet.has(id)) discrepancies.push(`schema/atoms.json atom '${id}' is missing from the Lean Atom universe`);
  if (universe.length !== uniSet.size) discrepancies.push(`Lean Atom universe has duplicate constructors`);

  // (2) every framework concept in the schema must equal its Lean shape, and vice-versa.
  const byId = Object.fromEntries((conceptsDoc.concepts || []).map((c) => [c.id, c]));
  const frameworkInJson = (conceptsDoc.concepts || []).filter((c) => c.origin === 'framework').map((c) => c.id);
  for (const name of FRAMEWORK_CONCEPTS) {
    if (!byId[name]) { discrepancies.push(`framework concept '${name}' present in Lean but absent from concepts.json`); continue; }
    if (byId[name].origin !== 'framework') discrepancies.push(`concept '${name}' must be origin:'framework' (it is the Lean-bound set)`);
    let lean, json;
    try { lean = leanShape(name, defs); } catch (e) { discrepancies.push(String(e.message)); continue; }
    try { json = jsonShape(byId[name].formula, name); } catch (e) { discrepancies.push(String(e.message)); continue; }
    // every atom referenced must be a real atom
    const leaves = (s) => (s.op === 'not' ? leaves(s.child) : s.atoms);
    for (const a of leaves(json)) if (!atomIds.has(a)) discrepancies.push(`concept '${name}' references unknown atom '${a}'`);
    if (stableStringify(lean) !== stableStringify(json))
      discrepancies.push(`concept '${name}' DRIFT — Lean ${stableStringify(lean)} ≠ JSON ${stableStringify(json)}`);
    checked.push(name);
  }
  // a framework concept in JSON that Lean does not define is also drift
  for (const id of frameworkInJson)
    if (!FRAMEWORK_CONCEPTS.includes(id)) discrepancies.push(`concept '${id}' is origin:'framework' in concepts.json but has no Lean definition`);

  return { ok: discrepancies.length === 0, discrepancies, checked };
}
