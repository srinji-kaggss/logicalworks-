#!/usr/bin/env node
// run-soak.mjs — the endurance-tier front-end (docs/04 §4.3–4.4; issue #643).
//
// Loads a tailoring profile, and for each dimension the profile's `envelope.target` declares,
// invokes the bound soak harness (a NATIVE tool that runs the escalate→bracket→revert→soak loop
// and emits a `capacity-profile/v0` artifact on stdout) as a content-addressed node — so an
// unchanged target reuses the (expensive) characterization. It then decides ENVELOPE-RELATIVE
// acceptance (soak.acceptEnvelope): GO iff measured V_NO ≥ target × margin on every dimension.
//
// The soak loop itself is deferred behind the tool seam (compiled per-target code; docs/04 §4.2):
// with no binding, an absent binary, or a self-skip (exit 77), the dimension is `unknown` and the
// run BLOCKS — unknown ≠ pass (docs/02 §2.6). Keel never prices anything (§4.6).
//
// Usage:  node src/run-soak.mjs --profile <profile.json>
// Exit:   0 GO (envelope held) · 1 NO-GO (shortfall) / BLOCKED (unmeasured) · 2 runner fault.

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H } from './anchor.mjs';
import { contentFingerprint } from './engine.mjs';
import { validateProfile } from './validate.mjs';
import { acceptEnvelope, validateCapacityProfile } from './soak.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');
const SKIP_EXIT = 77;
const DEFAULT_TIMEOUT_MS = 1_800_000; // soak is slow by nature (minutes–hours); generous bound

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };

function has(bin) { return spawnSync('bash', ['-c', `command -v ${bin}`]).status === 0; }

/** Build a content-addressed soak node for one dimension: run the harness, parse its
 *  capacity-profile/v0, return { v_no } or { v_no:null, reason } (unmeasured ⇒ unknown). */
function soakNode(dim, binding, root, fingerprint) {
  const ev = binding?.evidence;
  return {
    kind: `soak:${dim}`,
    params: { dimension: dim },
    inputs: [fingerprint, ev ? H('soak-ev/v1', { tool: ev.tool, argv: ev.argv || [], cwd: ev.cwd || '', env: ev.env || {} }) : 'nobind'],
    async compute() {
      if (!ev) return { v_no: null, reason: `no soak binding for dimension '${dim}'` };
      for (const bin of ev.needs || []) if (!has(bin)) return { v_no: null, reason: `soak harness toolchain absent: ${bin}` };
      if (!Array.isArray(ev.argv)) return { v_no: null, reason: 'soak binding has no argv (refusing to spawn a bare tool)' };
      const cwd = ev.cwd ? join(root, ev.cwd) : root;
      const r = spawnSync(ev.tool, ev.argv, { cwd, env: { ...process.env, ...ev.env }, encoding: 'utf8', timeout: ev.timeout_ms || DEFAULT_TIMEOUT_MS, maxBuffer: 64 * 1024 * 1024 });
      if (r.status === SKIP_EXIT) return { v_no: null, reason: (r.stdout || '').trim().split('\n').pop()?.replace(/^SKIP:\s*/, '') || 'soak harness self-skipped' };
      if (r.status !== 0) return { v_no: null, reason: `soak harness '${ev.tool}' exited ${r.status} — no characterization`, log: (r.stderr || r.stdout || '').slice(-2000) };
      let prof;
      try { prof = JSON.parse(r.stdout); } catch { return { v_no: null, reason: 'soak harness stdout is not valid capacity-profile/v0 JSON' }; }
      const perrs = validateCapacityProfile(prof);
      if (perrs.length) return { v_no: null, reason: `invalid capacity-profile: ${perrs.join('; ')}` };
      return { v_no: prof.v_no, v_ne: prof.v_ne, profile: prof };
    },
  };
}

async function main() {
  const profilePath = arg('--profile');
  if (!profilePath) { console.error('usage: run-soak.mjs --profile <profile.json>'); process.exit(2); }

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

  const envelope = profile.envelope;
  if (!envelope || !envelope.target || !Object.keys(envelope.target).length) {
    console.error('⚠ no envelope.target declared — the soak tier has nothing to accept against (docs/04 §4.4). Declare envelope.target in the profile.');
    process.exit(2);
  }

  const root = profile.target?.root || process.cwd();
  const fingerprint = contentFingerprint(root);
  const soakBindings = profile.soak || [];
  const bindingFor = (dim) => soakBindings.find((s) => s.dimension === dim);

  const anchor = new Anchor(join(process.cwd(), '.keel'));
  const profiles = {};
  for (const dim of Object.keys(envelope.target)) {
    const res = await anchor.evaluateAsync(soakNode(dim, bindingFor(dim), root, fingerprint));
    const v = res.verdict || {};   // compute()'s return is stored under .verdict
    profiles[dim] = v.v_no == null ? null : { v_no: v.v_no, v_ne: v.v_ne };
  }

  const decision = acceptEnvelope(profiles, envelope);
  const runId = H('soak', fingerprint, envelope, soakBindings);
  anchor.seal(runId, { tier: 'soak', verdict: decision.verdict, limiting: decision.limiting });
  writeFileSync(join(anchor.dir, `soak-${runId}.json`), JSON.stringify({ schema: 'keel.soak-run/v0', run: runId, envelope, decision, profiles }, null, 2) + '\n');

  const mark = decision.verdict === 'true' ? 'GO' : decision.verdict === 'false' ? 'NO-GO' : 'BLOCKED';
  console.log('═'.repeat(60));
  console.log(`KEEL — soak tier  ·  dimensions=${decision.dimensions.length}  ·  margin×=${envelope.margin ?? 1}  ·  recomputed=${anchor.recomputed} reused=${anchor.reused}`);
  console.log('═'.repeat(60));
  console.log(`${mark} — envelope ${decision.verdict === 'true' ? 'held with margin' : decision.verdict === 'false' ? 'NOT met' : 'NOT fully measured'}  (run ${runId})`);
  for (const d of decision.dimensions) {
    const m = d.margin == null ? '   —  ' : `${d.margin.toFixed(2)}×`;
    const glyph = d.value === 'true' ? '✓' : d.value === 'false' ? '✗' : '?';
    console.log(`  ${glyph} ${d.dimension.padEnd(22)} V_NO=${d.v_no ?? '—'}  required=${d.required}  margin=${m}${d.reason ? `  — ${d.reason}` : ''}`);
  }
  if (decision.limiting) console.log(`  limiting dimension: ${decision.limiting} (the spar that gives first)`);
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/soak-${runId}.json  ·  Keel emits the physical characterization; cost is a downstream projection (§4.6)`);
  process.exit(decision.verdict === 'true' ? 0 : 1);
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
