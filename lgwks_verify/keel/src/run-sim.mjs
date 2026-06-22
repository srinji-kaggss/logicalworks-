#!/usr/bin/env node
// run-sim.mjs — the multi-actor simulation tier (docs/04 §4.5; axioms A1 closed-loop / A7 repeatable;
// issue #644). The interaction surface is where atom 17 (concurrency_correctness) and atom 16
// (idempotence) actually live, and where single-unit testing is blind.
//
// For each `sim` scenario, Keel ENUMERATES the order-preserving interleavings of the declared actors'
// step sequences (the finite schedule space — the interaction analogue of the input crossing), drives
// each interleaving through the system-under-test harness (injected as env KEEL_SCHEDULE), and crosses
// the consistency oracle (Kleene ∧) over every interleaving. Concurrency-correct iff EVERY schedule is
// consistent; the breaking interleaving is the race, reported by label. Harness deferred behind the
// tool seam; unmeasured ⇒ BLOCKS (unknown ≠ pass). A fuller in-Keel linearizability oracle is a named
// deferral — today the per-target harness embeds the consistency check (exit 0 ok / nonzero violated).
//
// Usage:  node src/run-sim.mjs --profile <profile.json> [--concept <id>] [--concurrency N]
// Exit:   0 GO (every interleaving consistent) · 1 NO-GO/BLOCKED · 2 runner fault.

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H } from './anchor.mjs';
import { contentFingerprint, kleeneAll, collectAtoms } from './engine.mjs';
import { evalConcept } from './concepts.mjs';
import { mapPool, defaultConcurrency } from './concurrency.mjs';
import { validateProfile } from './validate.mjs';
import { enumerateInterleavings, crossOracle } from './simulate.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');
const SKIP_EXIT = 77;
const DEFAULT_TIMEOUT_MS = 600_000;

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };
function has(bin) { return spawnSync('bash', ['-c', `command -v ${bin}`]).status === 0; }

/** Drive ONE interleaving through the harness; oracle = exit 0 consistent · nonzero violated · 77 unknown. */
function driveSchedule(harness, schedule, root) {
  const env = { ...process.env, ...harness.env, KEEL_SCHEDULE: JSON.stringify(schedule.steps) };
  const cwd = harness.cwd ? join(root, harness.cwd) : root;
  const r = spawnSync(harness.tool, harness.argv, { cwd, env, encoding: 'utf8', timeout: harness.timeout_ms || DEFAULT_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 });
  const base = { label: schedule.label, off: false };
  if (r.error) return { ...base, value: 'unknown', reason: `harness failed to launch: ${r.error.message}` };
  if (r.status === SKIP_EXIT) return { ...base, value: 'unknown', reason: (r.stdout || '').trim().split('\n').pop()?.replace(/^SKIP:\s*/, '') || 'harness self-skipped' };
  return { ...base, value: r.status === 0 ? 'true' : 'false',
    reason: r.status === 0 ? undefined : `inconsistent under this interleaving (exit ${r.status})${(r.stderr || r.stdout) ? ': ' + (r.stderr || r.stdout).trim().split('\n').pop() : ''}` };
}

function simNode(scn, root, fingerprint, concurrency) {
  return {
    kind: `sim-actors:${scn.name}`,
    params: { scenario: scn.name, atom: scn.atom },
    inputs: [fingerprint, H('sim-actors/v1', { actors: scn.actors, harness: { tool: scn.harness.tool, argv: scn.harness.argv, cwd: scn.harness.cwd || '', env: scn.harness.env || {} }, max: scn.max_interleavings || null })],
    async compute() {
      for (const bin of scn.harness.needs || []) if (!has(bin)) return { value: 'unknown', reason: `harness toolchain absent: ${bin}` };
      const en = enumerateInterleavings(scn.actors, { cap: scn.max_interleavings });
      if (en.error) return { value: 'unknown', reason: en.error };
      const points = await mapPool(en.schedules, concurrency, async (sch) => driveSchedule(scn.harness, sch, root));
      const safe = points.map((p, i) => p && p.__poolError ? { label: en.schedules[i].label, off: false, value: 'unknown', reason: `driver fault: ${p.__poolError.message}` } : p);
      const oracle = crossOracle(safe);
      return { value: oracle.value, explored: oracle.driven,
        reason: oracle.breaking ? `race at interleaving [${oracle.breaking.label}]${oracle.breaking.reason ? ' — ' + oracle.breaking.reason : ''}` : undefined };
    },
  };
}

async function main() {
  const profilePath = arg('--profile');
  if (!profilePath) { console.error('usage: run-sim.mjs --profile <profile.json> [--concept <id>]'); process.exit(2); }
  const concurrency = Number(arg('--concurrency')) || defaultConcurrency();

  const atomsDoc = JSON.parse(readFileSync(join(SCHEMA, 'atoms.json'), 'utf8'));
  const conceptsDoc = JSON.parse(readFileSync(join(SCHEMA, 'concepts.json'), 'utf8'));
  const profileSchema = JSON.parse(readFileSync(join(SCHEMA, 'profile.schema.json'), 'utf8'));
  const profile = JSON.parse(readFileSync(profilePath, 'utf8'));

  const profileErrs = validateProfile(profile, { schema: profileSchema, atomsDoc, conceptsDoc });
  if (profileErrs.length) {
    console.error(`⚠ PROFILE INVALID (${profileErrs.length}) — refusing to run (RESTRICTIVE; docs/03 §3.1):`);
    for (const e of profileErrs) console.error('   · ' + e);
    process.exit(2);
  }

  const scenarios = profile.sim || [];
  if (!scenarios.length) { console.error('⚠ no sim scenarios declared — nothing to interleave (docs/04 §4.5). Add a profile.sim block.'); process.exit(2); }
  for (const s of scenarios) if (!atomsDoc.atoms.find(a => a.id === s.atom)) { console.error(`sim scenario '${s.name}' binds unknown atom '${s.atom}'`); process.exit(2); }

  const gateId = arg('--concept') || profile.gate_concept || 'concurrent_safe';
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  const root = profile.target?.root || process.cwd();
  const fingerprint = contentFingerprint(root);
  const anchor = new Anchor(join(process.cwd(), '.keel'));

  const perAtom = {};
  const rows = [];
  for (const scn of scenarios) {
    const res = await anchor.evaluateAsync(simNode(scn, root, fingerprint, concurrency));
    const v = res.verdict || {};
    (perAtom[scn.atom] ||= []).push(v.value);
    rows.push({ name: scn.name, atom: scn.atom, value: v.value, explored: v.explored, reason: v.reason });
  }
  const atomValues = {};
  for (const id of Object.keys(perAtom)) atomValues[id] = kleeneAll(perAtom[id]);
  for (const id of collectAtoms(gate.formula)) if (!(id in atomValues)) atomValues[id] = 'unknown';
  const gateRes = evalConcept(gate, atomValues);

  const runId = H('sim', fingerprint, gateId, scenarios.map(s => s.name));
  anchor.seal(runId, { tier: 'sim', gate: gateId, verdict: gateRes.verdict });
  writeFileSync(join(anchor.dir, `sim-${runId}.json`), JSON.stringify({ schema: 'keel.sim-run/v0', run: runId, gate: gateId, verdict: gateRes.verdict, scenarios: rows }, null, 2) + '\n');

  const mark = gateRes.verdict === 'true' ? 'GO' : gateRes.verdict === 'false' ? 'NO-GO' : 'BLOCKED';
  console.log('═'.repeat(60));
  console.log(`KEEL — multi-actor sim tier  ·  gate '${gateId}'  ·  scenarios=${scenarios.length}  ·  recomputed=${anchor.recomputed} reused=${anchor.reused}`);
  console.log('═'.repeat(60));
  console.log(`${mark} — gate '${gateId}' = ${gateRes.verdict}  (run ${runId})`);
  for (const r of rows) {
    const g = r.value === 'true' ? '✓' : r.value === 'false' ? '✗' : '?';
    console.log(`  ${g} ${r.name.padEnd(24)} atom=${r.atom}  interleavings=${r.explored ?? '—'}${r.reason ? `  — ${r.reason}` : ''}`);
  }
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/sim-${runId}.json  ·  Keel enumerates+crosses interleavings; the harness embeds the consistency oracle (full linearizability check = deferred)`);
  process.exit(gateRes.verdict === 'true' ? 0 : 1);
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
