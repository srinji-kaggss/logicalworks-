#!/usr/bin/env node
// Maturity scream — multi-axis IEC 61508-style assessment for logicalworks-.
//
// Why this exists: the merge floor (lgwks_floor) gates on 3 of Keel's 20 atoms.
// A developing codebase can clear that floor while being deficient on 16 other
// axes — and the CI stayed SILENT about them. IEC 61508's discipline is the
// opposite: a battery of axes, and an axis you did not MEASURE earns NO credit
// (it is a deficiency, not a pass). This lane runs the FULL axis assessment and
// the whole concept ladder, then says loudly how far the product is from sound /
// resilient / defense-in-depth / Excellent.
//
// It is REPORT-ONLY (exit 0). It does not block merges — the merge gate stays
// lgwks_floor. The scream is the deliverable: honest multi-axis maturity, not a
// gate that fakes a pass on axes nobody checked.
//
// Data: one Keel run against `Excellent` yields the values of the BOUND atoms
// (in the symbolic projection). Every UNBOUND atom is, by definition, unmeasured
// -> unknown. The concept ladder is then evaluated from that 20-axis matrix with
// Keel's own 3-valued AND (false dominates; else unknown; else true). The atom
// and concept definitions are READ from the vendored schema — never copied here
// (no divergent second source).

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, writeFileSync, statSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VENDOR = join(ROOT, 'lgwks_verify', 'keel');
const PROFILE = join(ROOT, 'lgwks.profile.json');
const KEEL_DIR = join(ROOT, '.keel');

function readJSON(p) { return JSON.parse(readFileSync(p, 'utf8')); }

// 3-valued AND: a false anywhere is false; else any unknown is unknown; else true.
function andKleene(values) {
  if (values.includes('false')) return 'false';
  if (values.includes('unknown')) return 'unknown';
  return 'true';
}
function evalFormula(formula, matrix) {
  if (formula.all) return andKleene(formula.all.map((a) => matrix[a] ?? 'unknown'));
  if (formula.not) {
    const inner = evalFormula(formula.not, matrix);
    return inner === 'true' ? 'false' : inner === 'false' ? 'true' : 'unknown';
  }
  return 'unknown';
}
const verdictOf = (v) => (v === 'true' ? 'GO' : v === 'false' ? 'NO-GO' : 'BLOCKED');

function newestProjection() {
  if (!existsSync(KEEL_DIR)) return null;
  const cands = readdirSync(KEEL_DIR)
    .filter((f) => f.startsWith('projection-symbolic-') && f.endsWith('.json'))
    .map((f) => ({ f, t: statSync(join(KEEL_DIR, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  return cands.length ? join(KEEL_DIR, cands[0].f) : null;
}

function buildMatrix() {
  const atomsRaw = readJSON(join(VENDOR, 'schema', 'atoms.json'));
  const atoms = (Array.isArray(atomsRaw) ? atomsRaw : atomsRaw.atoms).map((a) => a.id || a.name);
  const profile = readJSON(PROFILE);
  const bound = new Set((profile.bindings || []).map((b) => b.atom));

  // One Keel run against the all-20 concept forces every BOUND atom to evaluate.
  // Exit code is expected NO-GO/BLOCKED — we read the projection, not the exit.
  const r = spawnSync(process.execPath,
    [join(VENDOR, 'src', 'run.mjs'), '--profile', PROFILE, '--concept', 'Excellent'],
    { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, env: process.env });
  const proj = newestProjection();
  const measured = {};
  if (proj) {
    for (const e of readJSON(proj).atoms || []) measured[e.atom] = { value: e.value, reason: e.reason || '' };
  }

  const matrix = {};
  const rows = [];
  for (const atom of atoms) {
    let value, reason;
    if (measured[atom]) {
      value = measured[atom].value; reason = measured[atom].reason;
    } else if (!bound.has(atom)) {
      value = 'unknown'; reason = 'no binding — UNMEASURED (no evidence source declared)';
    } else {
      value = 'unknown'; reason = 'bound but not evaluated';
    }
    matrix[atom] = value;
    rows.push({ atom, value, measured: bound.has(atom), reason });
  }
  return { atoms, matrix, rows, runStderr: r.stderr || '' };
}

function main() {
  const { matrix, rows } = buildMatrix();
  const concepts = readJSON(join(VENDOR, 'schema', 'concepts.json')).concepts
    .filter((c) => c.origin !== 'framework' || c.id === 'Excellent' || c.id === 'CoreGroundedCorrect');

  // Ladder ordered by stringency (atoms required), so "highest tier cleared" is meaningful.
  const gateConcepts = concepts
    .filter((c) => c.formula && c.formula.all)
    .map((c) => ({ id: c.id, need: c.formula.all, verdict: verdictOf(evalFormula(c.formula, matrix)) }))
    .sort((a, b) => a.need.length - b.need.length);

  const evidenced = rows.filter((r) => r.value === 'true');
  const failed = rows.filter((r) => r.value === 'false');
  const unmeasured = rows.filter((r) => r.value === 'unknown');
  const cleared = gateConcepts.filter((c) => c.verdict === 'GO').map((c) => c.id);
  const highest = cleared.length ? cleared[cleared.length - 1] : '(none — clears no tier)';

  const bar = '═'.repeat(64);
  console.log(bar);
  console.log('MATURITY SCREAM — multi-axis assessment (IEC 61508 discipline: unmeasured ≠ pass)');
  console.log(bar);
  console.log(`  axes evidenced (true) : ${evidenced.length}/20`);
  console.log(`  axes failed (false)   : ${failed.length}/20`);
  console.log(`  axes UNMEASURED       : ${unmeasured.length}/20   ← no credit; each is a deficiency`);
  console.log(`  highest tier cleared  : ${highest}`);
  console.log(bar);
  console.log('  CONCEPT LADDER (least → most stringent):');
  for (const c of gateConcepts) {
    const mark = c.verdict === 'GO' ? '✓ GO   ' : c.verdict === 'NO-GO' ? '✗ NO-GO' : '? BLOCK';
    const missing = c.need.filter((a) => matrix[a] !== 'true');
    console.log(`    ${mark}  ${c.id}  (${c.need.length} axes)` + (missing.length ? `  — missing: ${missing.join(', ')}` : ''));
  }
  console.log(bar);
  console.log('  AXIS MATRIX:');
  for (const r of rows) {
    const m = r.value === 'true' ? '✓' : r.value === 'false' ? '✗' : '?';
    console.log(`    ${m} ${r.atom}` + (r.value !== 'true' ? `  — ${r.reason || r.value}` : ''));
  }
  console.log(bar);
  console.log(`VERDICT (full-axis / Excellent): ${verdictOf(evalFormula({ all: rows.map((r) => r.atom) }, matrix))}` +
    `  ·  ${evidenced.length}/20 evidenced  ·  report-only (merge gate = lgwks_floor)`);

  const summary = {
    schema: 'lgwks.ci.maturity/v0',
    evidenced: evidenced.length, failed: failed.length, unmeasured: unmeasured.length, total: 20,
    highest_tier_cleared: highest,
    ladder: gateConcepts,
    axes: rows,
  };
  mkdirSync(KEEL_DIR, { recursive: true });
  writeFileSync(join(KEEL_DIR, 'maturity.json'), JSON.stringify(summary, null, 2) + '\n');
  return summary;
}

// Standalone (`node scripts/ci/maturity.mjs`) or imported by run.mjs.
if (import.meta.url === `file://${process.argv[1]}`) {
  try { main(); process.exit(0); }
  catch (e) { console.error('maturity assessment fault:', e && e.stack ? e.stack : String(e)); process.exit(2); }
}
export { main as maturityReport, buildMatrix, evalFormula };
