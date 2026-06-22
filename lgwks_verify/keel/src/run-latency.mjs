#!/usr/bin/env node
// run-latency.mjs — the latency/jitter tier front-end (aircraft axiom A5; docs/10 §10.4).
//
// For each `latency` scenario, runs the bound harness `samples` times (the harness emits the
// operation's measured latency in ms on stdout), aggregates (max / p99 / jitter), and crosses the
// aggregate against the declared budget (latency.acceptLatency). Scenario atoms compose into the
// gate concept like the other tiers. The measurement is an empirical sensor; the decision is
// deterministic. Measured per source version and reused on unchanged source (content-addressed, A8).
//
// Usage:  node src/run-latency.mjs --profile <profile.json> [--concept <id>]
// Exit:   0 GO (every budget held) · 1 NO-GO (budget breached) / BLOCKED (unmeasured / no budget) · 2 fault.

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H } from './anchor.mjs';
import { contentFingerprint, kleeneAll, collectAtoms } from './engine.mjs';
import { evalConcept } from './concepts.mjs';
import { validateProfile } from './validate.mjs';
import { aggregateLatency, acceptLatency } from './latency.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');
const SKIP_EXIT = 77;
const DEFAULT_SAMPLES = 5;
const DEFAULT_TIMEOUT_MS = 600_000;

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };
function has(bin) { return spawnSync('bash', ['-c', `command -v ${bin}`]).status === 0; }

/** Run the harness once; return the latency sample (ms) it printed, or null (unmeasured). */
function oneSample(harness, root) {
  const cwd = harness.cwd ? join(root, harness.cwd) : root;
  const r = spawnSync(harness.tool, harness.argv, { cwd, env: { ...process.env, ...harness.env }, encoding: 'utf8', timeout: harness.timeout_ms || DEFAULT_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 });
  if (r.error || r.status === SKIP_EXIT || r.status !== 0) return null;
  const n = Number((r.stdout || '').trim().split(/\s+/).pop());
  return Number.isFinite(n) ? n : null;
}

function latencyNode(scn, root, fingerprint) {
  const samples = scn.samples || DEFAULT_SAMPLES;
  return {
    kind: `lat:${scn.name}`,
    params: { scenario: scn.name, atom: scn.atom },
    inputs: [fingerprint, H('lat-scn/v1', { harness: { tool: scn.harness.tool, argv: scn.harness.argv, cwd: scn.harness.cwd || '', env: scn.harness.env || {} }, budget: scn.budget || null, samples })],
    async compute() {
      for (const bin of scn.harness.needs || []) if (!has(bin)) return { value: 'unknown', reason: `harness toolchain absent: ${bin}` };
      const ms = [];
      for (let i = 0; i < samples; i++) { const s = oneSample(scn.harness, root); if (s != null) ms.push(s); }
      const agg = aggregateLatency(ms);
      const acc = acceptLatency(agg, scn.budget);
      return { value: acc.value, agg, reason: acc.reasons.length ? acc.reasons.join(' · ') : undefined };
    },
  };
}

async function main() {
  const profilePath = arg('--profile');
  if (!profilePath) { console.error('usage: run-latency.mjs --profile <profile.json> [--concept <id>]'); process.exit(2); }

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

  const scenarios = profile.latency || [];
  if (!scenarios.length) { console.error('⚠ no latency scenarios declared — nothing to measure (A5). Add a profile.latency block.'); process.exit(2); }
  for (const s of scenarios) if (!atomsDoc.atoms.find(a => a.id === s.atom)) { console.error(`latency scenario '${s.name}' binds unknown atom '${s.atom}'`); process.exit(2); }

  const gateId = arg('--concept') || profile.gate_concept || 'latency_bounded';
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  const root = profile.target?.root || process.cwd();
  const fingerprint = contentFingerprint(root);
  const anchor = new Anchor(join(process.cwd(), '.keel'));

  const perAtom = {};
  const rows = [];
  for (const scn of scenarios) {
    const res = await anchor.evaluateAsync(latencyNode(scn, root, fingerprint));
    const v = res.verdict || {};
    (perAtom[scn.atom] ||= []).push(v.value);
    rows.push({ name: scn.name, atom: scn.atom, value: v.value, agg: v.agg, reason: v.reason });
  }
  const atomValues = {};
  for (const id of Object.keys(perAtom)) atomValues[id] = kleeneAll(perAtom[id]);
  for (const id of collectAtoms(gate.formula)) if (!(id in atomValues)) atomValues[id] = 'unknown';
  const gateRes = evalConcept(gate, atomValues);

  const runId = H('latency', fingerprint, gateId, scenarios.map(s => s.name));
  anchor.seal(runId, { tier: 'latency', gate: gateId, verdict: gateRes.verdict });
  writeFileSync(join(anchor.dir, `latency-${runId}.json`), JSON.stringify({ schema: 'keel.latency-run/v0', run: runId, gate: gateId, verdict: gateRes.verdict, scenarios: rows }, null, 2) + '\n');

  const mark = gateRes.verdict === 'true' ? 'GO' : gateRes.verdict === 'false' ? 'NO-GO' : 'BLOCKED';
  console.log('═'.repeat(60));
  console.log(`KEEL — latency tier (A5)  ·  gate '${gateId}'  ·  scenarios=${scenarios.length}  ·  recomputed=${anchor.recomputed} reused=${anchor.reused}`);
  console.log('═'.repeat(60));
  console.log(`${mark} — gate '${gateId}' = ${gateRes.verdict}  (run ${runId})`);
  for (const r of rows) {
    const g = r.value === 'true' ? '✓' : r.value === 'false' ? '✗' : '?';
    const a = r.agg && r.agg.n ? `max=${r.agg.max}ms p99=${r.agg.p99}ms jitter=${r.agg.jitter}ms n=${r.agg.n}` : 'no samples';
    console.log(`  ${g} ${r.name.padEnd(24)} atom=${r.atom}  ${a}${r.reason ? `  — ${r.reason}` : ''}`);
  }
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/latency-${runId}.json  ·  measurement is empirical (sensor); the budget decision is deterministic (A5)`);
  process.exit(gateRes.verdict === 'true' ? 0 : 1);
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
