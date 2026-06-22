#!/usr/bin/env node
// qualify.mjs — DO-330-INSPIRED self-qualification for KEEL ITSELF ("who audits the auditor").
//
// NOT a DO-330 TQL credential (that needs a Tool Qualification Plan, tool operational requirements,
// independence, and a certification authority — docs/10 §10.3). This adopts the DISCIPLINE: a tool
// that gates must PROVE it catches what it claims. The kernel proves its detectors against a
// known-bad corpus (scripts/ci/selftest-qualification.mjs); this is the same discipline turned
// on Keel's OWN core guarantees — the properties an independent reviewer most needs to trust:
//
//   unknown ≠ pass     — a gate over an UNBOUND atom must BLOCK (exit 1), never GO.
//   false blocks       — a binding whose tool exits nonzero must make the gate NO-GO (exit 1).
//   clean control      — a satisfied binding must GO (exit 0): no false positive.
//   crossing ∧         — a `cross` matrix with one failing point must go NO-GO (find where it fails).
//   advisory ≠ verdict — an advisory signal going red must NOT flip a GO (the Phase-2 seam).
//
// Each fixture is a self-contained profile/registry + an expected verdict. The harness runs
// Keel against it in a throwaway dir (hermetic; no shared .keel/) and asserts the verdict.
// Determinism: no wall-clock, no RNG. Exit 0 = Keel qualified · 1 = a MISS (Keel gave the
// wrong verdict on a planted case — it must not gate) · 2 = harness fault.
//
// Usage:  node src/qualify.mjs [--self-test]
//   --self-test : meta-qualify THIS harness (prove it reports a MISS when Keel passes a case
//                 that was supposed to fail — the auditor-of-the-auditor).

import { spawnSync } from 'node:child_process';
import { readFileSync, readdirSync, existsSync, mkdtempSync, cpSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkConformance } from './conformance.mjs';
import { leanBuild } from './adapters/lean.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));      // src/
const ROOT = resolve(HERE, '..');
const CORPUS = join(ROOT, 'fixtures', 'known-bad');
const SCHEMA = join(ROOT, 'schema');
const LEAN_PKG = join(ROOT, 'lean');
const LEAN = join(LEAN_PKG, 'ExcellentCode', 'Framework.lean');
const NODE = process.execPath;
const MAXBUF = 32 * 1024 * 1024;
const FRONT_ENDS = { profile: 'run.mjs', registry: 'run-registry.mjs', soak: 'run-soak.mjs', simulate: 'run-simulate.mjs', latency: 'run-latency.mjs', sim: 'run-sim.mjs' };

// M2: a fixture is a trusted-but-verify boundary (a poisoned fixture's bindings run as code).
// Scrub the env to a hermetic minimum so a fixture cannot read host secrets or touch the host
// git/HOME, and confine the entry path to the sandbox so `../` cannot escape it.
function hermeticEnv(sb) {
  return {
    PATH: process.env.PATH || '/usr/bin:/bin', HOME: sb,
    GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_SYSTEM: '/dev/null', GIT_TERMINAL_PROMPT: '0',
    LANG: process.env.LANG || 'C', TMPDIR: sb,
  };
}
function safeJoin(sb, rel) {
  const p = resolve(sb, rel);
  if (p !== sb && !p.startsWith(sb + '/')) throw new Error(`entry '${rel}' escapes the sandbox`);
  return p;
}

/** Run Keel against one fixture in a hermetic temp dir; return { verdict, exit }. */
function runFixture(dir, c) {
  const sb = mkdtempSync(join(tmpdir(), 'keel-qual-'));
  try {
    cpSync(dir, sb, { recursive: true, filter: (s) => !s.endsWith('case.json') });
    const script = join(HERE, FRONT_ENDS[c.front_end] || 'run.mjs');
    const entryFlag = c.front_end === 'registry' ? '--registry' : '--profile';
    const entry = safeJoin(sb, c.entry || '');
    if ((c.args || []).some((a) => typeof a === 'string' && a.includes('..')))
      throw new Error(`case args contain '..' (refused): ${JSON.stringify(c.args)}`);
    const args = [script, entryFlag, entry, ...(c.args || [])];
    const r = spawnSync(NODE, args, { cwd: sb, env: hermeticEnv(sb), encoding: 'utf8', maxBuffer: MAXBUF });
    const out = `${r.stdout || ''}\n${r.stderr || ''}`;
    return { exit: r.status, verdict: parseVerdict(out, r.status), out };
  } finally {
    rmSync(sb, { recursive: true, force: true });
  }
}

/** Read the verdict mark off Keel's render (GO / NO-GO / BLOCKED), falling back to exit code. */
function parseVerdict(out, exit) {
  if (/\bNO-GO\b/.test(out)) return 'NO-GO';
  if (/\bBLOCKED\b/.test(out)) return 'BLOCKED';
  if (/\bGO\b/.test(out)) return 'GO';
  return exit === 0 ? 'GO' : exit === 2 ? 'FAULT' : 'NO-GO';
}

/** The qualification verdict for one fixture given Keel's result. */
function judge(c, r) {
  if (r.exit === 2) return { qualified: false, why: `Keel runner FAULTED (exit 2) — ${tail(r.out)}` };
  // M1: the EXIT CODE is the contract run.mjs/run-registry.mjs guarantee (0 GO · 1 NO-GO/BLOCKED ·
  // 2 fault). Require every case to assert it so the fragile verdict-string parse is never the sole
  // signal. expect_verdict (GO/NO-GO/BLOCKED) is an additional, optional discriminator.
  if (c.expect_exit === undefined)
    return { qualified: false, why: `case must declare expect_exit (the authoritative contract); verdict text alone is not trusted` };
  if (r.exit !== c.expect_exit)
    return { qualified: false, why: `expected exit ${c.expect_exit}, got ${r.exit}` };
  if (c.expect_verdict && r.verdict !== c.expect_verdict)
    return { qualified: false, why: `expected verdict ${c.expect_verdict}, got ${r.verdict}` };
  return { qualified: true, why: `Keel returned ${r.verdict} (exit ${r.exit}) as planted` };
}

const tail = (s) => (s || '').trim().split('\n').filter(Boolean).slice(-1)[0] || '';

function discover() {
  if (!existsSync(CORPUS)) return [];
  return readdirSync(CORPUS, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => join(CORPUS, d.name))
    .filter((p) => existsSync(join(p, 'case.json')))
    .sort();
}

function metaSelfTest() {
  // Take the clean control (Keel correctly returns GO) but JUDGE it as if NO-GO were expected.
  // The harness MUST report a MISS — otherwise it is blind and must not certify Keel.
  console.log('================================================');
  console.log('META SELF-TEST — qualification harness (audits the auditor)');
  console.log('================================================');
  const control = discover().find((d) => {
    try { return JSON.parse(readFileSync(join(d, 'case.json'), 'utf8')).expect_verdict === 'GO'; } catch { return false; }
  });
  if (!control) { console.error('✗ harness fault: no GO control fixture to meta-test against.'); process.exit(2); }
  const c = JSON.parse(readFileSync(join(control, 'case.json'), 'utf8'));
  const r = runFixture(control, c);
  const asGo = judge({ ...c, expect_verdict: 'GO', expect_exit: 0 }, r);
  const asNoGo = judge({ ...c, expect_verdict: 'NO-GO', expect_exit: 1 }, r);
  console.log(`  control '${control.split('/').pop()}' · Keel returned ${r.verdict} (exit ${r.exit})`);
  console.log(`  judged under expect:GO    → qualified=${asGo.qualified} (MUST be true)`);
  console.log(`  judged under expect:NO-GO → qualified=${asNoGo.qualified} (MUST be false)`);
  if (asGo.qualified === true && asNoGo.qualified === false) {
    console.log('✓ harness correctly distinguishes a real GO from a missed NO-GO.');
    process.exit(0);
  }
  console.error('✗ HARNESS-QUALIFICATION FAILURE: the auditor cannot tell a pass from a miss. Fix judge().');
  process.exit(1);
}

// concept↔Lean conformance (issue ledger #645 item 7; docs/02 §2.4): re-derive the three
// framework concepts from the Lean skeleton and assert concepts.json matches it structurally.
// This is the ALWAYS-ON, zero-dependency gate (no toolchain needed). It proves the JSON did not
// drift from the declared skeleton; leanMachineCheckRow() below proves the skeleton TYPECHECKS.
function conformanceRow() {
  const J = (f) => JSON.parse(readFileSync(join(SCHEMA, f), 'utf8'));
  const leanText = readFileSync(LEAN, 'utf8');
  const r = checkConformance({ conceptsDoc: J('concepts.json'), leanText, atomsDoc: J('atoms.json') });
  return {
    name: 'concept-lean-conformance',
    expect: 'CONFORM', got: r.ok ? 'CONFORM' : 'DRIFT',
    qualified: r.ok,
    why: r.ok ? `${r.checked.length} framework concepts match Framework.lean (structural)` : r.discrepancies.join('; '),
  };
}

// Lean machine-check (issue ledger item 6 / #646; docs/05 §5.2): `lake build` the skeleton so the
// conformance reference is COMPILED, not merely transcribed. This closes the #645 item-7 residual.
// Three-valued, honest: toolchain present + builds ⇒ qualified COMPILED; present + fails ⇒ a real
// MISS (the skeleton stopped typechecking — drift the structural check cannot see); ABSENT ⇒ SKIP,
// qualified-but-skipped (Lean depth is purchasable, docs/05 §5.2 — it never blocks the floor, and
// conformanceRow() still gates). `unknown` is never silently upgraded to a pass.
function leanMachineCheckRow() {
  const r = leanBuild(LEAN_PKG);
  if (!r.present)
    return { name: 'lean-skeleton-machinecheck', expect: 'COMPILED', got: 'SKIP', qualified: true, skipped: true, why: r.reason };
  const ok = r.value === 'true';
  return {
    name: 'lean-skeleton-machinecheck',
    expect: 'COMPILED', got: ok ? 'COMPILED' : 'FAILED',
    qualified: ok,
    why: ok
      ? 'lake build certified lean/ExcellentCode/Framework.lean (kernel-checked, not transcribed)'
      : `lake build FAILED — the skeleton no longer typechecks: ${r.reason}`,
  };
}

function main() {
  if (process.argv.includes('--self-test')) return metaSelfTest();
  const fixtures = discover();
  console.log('================================================');
  console.log('KEEL SELF-QUALIFICATION — known-bad corpus (DO-330-inspired; not a TQL credential)');
  console.log('================================================');
  if (!fixtures.length) {
    console.error(`✗ no fixtures under ${CORPUS} — a self-qualifying gate with an empty corpus is theater.`);
    process.exit(1);
  }
  const rows = [];
  // ORG.selftest obligation: the framework concepts must equal their Lean definitions (structural),
  // AND the Lean definitions must typecheck (machine-check, when the toolchain is present).
  try { rows.push(conformanceRow()); }
  catch (e) { rows.push({ name: 'concept-lean-conformance', expect: 'CONFORM', got: 'FAULT', qualified: false, why: `conformance harness fault — ${String(e.message)}` }); }
  try { rows.push(leanMachineCheckRow()); }
  catch (e) { rows.push({ name: 'lean-skeleton-machinecheck', expect: 'COMPILED', got: 'FAULT', qualified: false, why: `lean machine-check harness fault — ${String(e.message)}` }); }
  for (const dir of fixtures) {
    const name = dir.split('/').pop();
    let c;
    try { c = JSON.parse(readFileSync(join(dir, 'case.json'), 'utf8')); }
    catch (e) { rows.push({ name, qualified: false, why: `bad case.json: ${e.message}` }); continue; }
    const r = runFixture(dir, c);
    const j = judge(c, r);
    rows.push({ name, expect: c.expect_verdict, got: r.verdict, qualified: j.qualified, why: j.why });
  }
  console.log(`\n${'FIXTURE'.padEnd(30)}${'EXPECT'.padEnd(10)}${'GOT'.padEnd(10)}RESULT`);
  for (const r of rows) {
    const mark = r.skipped ? '○ skipped — ' + r.why : r.qualified ? '✓ qualified' : '✗ MISS — ' + r.why;
    console.log(`${r.name.padEnd(30)}${String(r.expect || '').padEnd(10)}${String(r.got || '').padEnd(10)}${mark}`);
  }

  const misses = rows.filter((r) => !r.qualified);
  const skips = rows.filter((r) => r.skipped);
  console.log('\n================================================');
  if (!misses.length) {
    const passed = rows.length - skips.length;
    const skipNote = skips.length ? ` (${skips.length} check(s) SKIPPED, not passed: ${skips.map((s) => s.name).join(', ')})` : '';
    console.log(`✅ QUALIFIED — Keel returned the correct verdict on all ${passed} checked case(s).${skipNote}`);
    process.exit(0);
  }
  console.error(`❌ NOT QUALIFIED — ${misses.length} case(s) where Keel gave the wrong verdict. A floor that`);
  console.error(`   miscalls a planted case must not gate. Fix the engine (NEVER relax the case). Misses:`);
  for (const m of misses) console.error(`   ✗ ${m.name} — ${m.why}`);
  process.exit(1);
}

try { main(); }
catch (e) {
  console.error('\n⚠ HARNESS FAULT (not a qualification verdict): ' + String(e && e.stack ? e.stack : e));
  process.exit(2);
}
