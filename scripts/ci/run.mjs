#!/usr/bin/env node
// Portable local CI runner for logicalworks- — Keel verification authority as the gate.
//
// Ported from keel/scripts/ci/run.mjs (the reference pattern). This is the repo-level
// CI/CD surface around the VENDORED Keel authority (lgwks_verify/keel, pinned at
// SHA 181707a per lgwks_verify/keel/VENDORED.txt). It runs the tier's lanes, writes
// per-lane logs, and seals a deterministic run manifest under .ci-runs/<id>/.
//
// Independence (Keel docs 06.2 / 12.2): this calls the VENDORED keel by RELATIVE path
// only — it owes nothing to a hosted CI service or to an absolute upstream checkout.
// GitHub Actions, if used, is a thin projection that calls this; this is the authority.
//
// Verdicts (3-valued, honest):
//   GO          exit 0   — every lane passed
//   NO-GO       exit 1   — a lane failed (real evidence says no)
//   RUNNER-FAULT exit 2  — the runner itself threw (never a silent pass)
//   BLOCKED     exit 3   — the tier cannot be evaluated (e.g. its keel runners are
//                          not vendored). NOT a pass and NOT a fail — unknown.

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VENDOR = join(ROOT, 'lgwks_verify', 'keel');
const KEEL_SRC = join(VENDOR, 'src');
const PROFILE = 'lgwks.profile.json';
const NODE = process.execPath;
const MAXBUF = 64 * 1024 * 1024;

function keel(file) {
  return join(KEEL_SRC, file);
}

// Commit tier: the always-on floor. Foundation (parse), qualification (the authority
// proves itself on its own known-bad corpus), then the target gate over lgwks.profile.json.
const COMMIT_LANES = [
  {
    id: 'json.parse',
    gate: 'foundation',
    cmd: [NODE, '-e',
      "for (const f of ['lgwks.profile.json','lgwks_verify/keel/schema/atoms.json','lgwks_verify/keel/schema/concepts.json','lgwks_verify/keel/schema/profile.schema.json']) JSON.parse(require('fs').readFileSync(f,'utf8')); console.log('json ok')"],
  },
  { id: 'authority.selftest', gate: 'qualification', cmd: [NODE, keel('selftest.mjs')] },
  { id: 'authority.qualify', gate: 'qualification', cmd: [NODE, keel('qualify.mjs')] },
  { id: 'authority.qualify.selftest', gate: 'qualification', cmd: [NODE, keel('qualify.mjs'), '--self-test'] },
  { id: 'target.gate', gate: 'commit', cmd: [NODE, keel('run.mjs'), '--profile', PROFILE] },
];

// Tiers whose Keel runners are NOT vendored at the pinned SHA. Honest BLOCKED, never
// a fake pass — this is exactly the defect (#235 shipped --tier as a silent no-op)
// that this redesign refuses to reproduce.
const UNVENDORED_TIERS = {
  nightly: ['run-simulate.mjs', 'run-sim.mjs'],
  release: ['run-simulate.mjs', 'run-sim.mjs', 'run-soak.mjs', 'run-latency.mjs'],
};

function sh(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8', maxBuffer: MAXBUF, env: process.env, ...opts });
}

function runId() {
  const head = sh('git', ['rev-parse', '--short', 'HEAD']);
  const sha = head.status === 0 ? head.stdout.trim() : 'nogit';
  const dirty = sh('git', ['status', '--porcelain']).stdout.trim().length > 0;
  return dirty ? `${sha}-dirty` : sha;
}

function hashFile(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function runLane(lane, runDir) {
  const started = process.hrtime.bigint();
  const r = sh(lane.cmd[0], lane.cmd.slice(1));
  const ms = Number((process.hrtime.bigint() - started) / 1000000n);
  const log = join(runDir, `${lane.id}.log`);
  writeFileSync(log, `$ ${lane.cmd.join(' ')}\n\n=== STDOUT ===\n${r.stdout || ''}\n=== STDERR ===\n${r.stderr || ''}\n=== EXIT ${r.status} ===\n`);
  return { id: lane.id, gate: lane.gate, status: r.status === 0 ? 'pass' : 'fail', exit: r.status, ms, log: log.slice(ROOT.length + 1) };
}

function seal(runDir, id, tier, verdict, reports, extra = {}) {
  const manifest = {
    schema: 'lgwks.ci.manifest/v0',
    run: id,
    tier,
    verdict,
    keel_vendor_sha: readFileSync(join(VENDOR, 'VENDORED.txt'), 'utf8').match(/SHA:\s*(\S+)/)?.[1] || 'unknown',
    artifacts: {
      profile: hashFile(join(ROOT, PROFILE)),
      atoms: hashFile(join(VENDOR, 'schema', 'atoms.json')),
      concepts: hashFile(join(VENDOR, 'schema', 'concepts.json')),
    },
    reports,
    ...extra,
  };
  const manifestPath = join(runDir, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  const manifestHash = hashFile(manifestPath);
  writeFileSync(join(runDir, 'seal.json'), JSON.stringify({ schema: 'lgwks.ci.seal/v0', run: id, tier, verdict, manifest_hash: manifestHash }, null, 2) + '\n');
  return { manifestPath, manifestHash };
}

async function main() {
  const args = process.argv.slice(2);
  const tierIdx = args.indexOf('--tier');
  const tier = tierIdx >= 0 ? args[tierIdx + 1] : 'commit';
  if (!['commit', 'nightly', 'release'].includes(tier)) {
    console.error(`unknown tier '${tier}' (commit|nightly|release)`);
    process.exit(2);
  }

  const id = runId();
  const runDir = join(ROOT, '.ci-runs', `${id}-${tier}`);
  mkdirSync(runDir, { recursive: true });

  console.log('============================================================');
  console.log(`lgwks CI — run=${id}  tier=${tier}  (Keel authority, vendored)`);
  console.log('============================================================');

  // Honest BLOCKED: a tier whose runners are not vendored cannot be evaluated.
  if (tier !== 'commit') {
    const missing = (UNVENDORED_TIERS[tier] || []).filter((f) => !existsSync(keel(f)));
    if (missing.length) {
      const { manifestHash } = seal(runDir, id, tier, 'BLOCKED', [], {
        blocked_reason: `tier '${tier}' requires Keel runners not vendored at the pinned SHA: ${missing.join(', ')}. Re-vendor (see lgwks_verify/keel/VENDORED.txt) before this tier can return a verdict.`,
      });
      console.log(`BLOCKED — tier '${tier}' not evaluable; missing vendored runners: ${missing.join(', ')}`);
      console.log(`  seal=${manifestHash.slice(0, 16)}...  record=${runDir.slice(ROOT.length + 1)}`);
      process.exit(3);
    }
  }

  const lanes = COMMIT_LANES; // nightly/release append tier lanes once their runners are vendored
  const reports = [];
  for (const lane of lanes) {
    const rep = runLane(lane, runDir);
    reports.push(rep);
    console.log(`${rep.status === 'pass' ? 'PASS' : 'FAIL'} ${lane.id} (${rep.ms} ms)`);
  }

  const verdict = reports.every((r) => r.status === 'pass') ? 'GO' : 'NO-GO';

  // Maturity scream (report-only, multi-axis): the merge gate above is a 3-axis
  // floor; this surfaces how the product fares across ALL 20 Keel axes + the
  // concept ladder. Never blocks the merge verdict — it makes immaturity LOUD.
  let maturity = null;
  if (tier === 'commit') {
    try {
      const { maturityReport } = await import('./maturity.mjs');
      console.log('');
      maturity = maturityReport();
    } catch (e) {
      console.log(`  (maturity scream unavailable: ${e && e.message ? e.message : e})`);
    }
  }

  const { manifestPath, manifestHash } = seal(runDir, id, tier, verdict, reports,
    maturity ? { maturity: { evidenced: maturity.evidenced, failed: maturity.failed, unmeasured: maturity.unmeasured, highest_tier_cleared: maturity.highest_tier_cleared } } : {});

  console.log('============================================================');
  console.log(`${verdict} — record=${manifestPath.slice(ROOT.length + 1)}  seal=${manifestHash.slice(0, 16)}...`);
  if (verdict !== 'GO') {
    for (const r of reports.filter((x) => x.status !== 'pass')) console.log(`  failed: ${r.id}  log=${r.log}`);
  }
  process.exit(verdict === 'GO' ? 0 : 1);
}

main().catch((e) => {
  console.error('RUNNER FAULT — treat as NO-GO:');
  console.error(e && e.stack ? e.stack : String(e));
  process.exit(2);
});
