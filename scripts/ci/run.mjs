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
import { dirname, isAbsolute, join } from 'node:path';
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

  // ── Product-behaviour floor ──────────────────────────────────────────────────
  // The Keel lanes above prove the verification ALGEBRA; they say NOTHING about the
  // product's own code. A CI that stands in for GitHub must run EVERY first-party
  // test surface or it is fake-accepting whatever it skips. These lanes are that
  // floor — keep them in lockstep with the Makefile `test` target.
  //
  // Fail-closed notes: a lane is `pass` ONLY on exit 0; a missing tool (uv/cargo/
  // python3) spawns with status null → `fail` (never a silent pass). `cargo test`
  // and `pytest` run WITHOUT -q hiding the counts, and the full output is sealed
  // per-lane under .ci-runs/<id>/ so "0 tests ran" can never masquerade as green.
  //
  // NOT covered, by deliberate decision (stated, not silent): archive/tests/ —
  // archived/orphaned modules (archive/README.md), no active callers; revived code
  // must move out of archive/ to earn coverage.
  // Enforces "fully comprehensive": fails if any tracked test surface is neither run
  // by a lane below nor explicitly excluded. The structural guarantee against a future
  // silent gap (see coverage_guard.mjs).
  { id: 'coverage.completeness', gate: 'commit', cmd: [NODE, join(HERE, 'coverage_guard.mjs')] },
  // schema-registry conformance (#147) is NOT a standalone lane anymore — it is bound as the
  // `specification_fidelity` atom in lgwks.profile.json and gated by lgwks_floor, so it runs through
  // the single Keel authority (target.gate). Folding it here retired the parallel governance.yml
  // job (#242) — one authority, no second copy to drift.
  // Python: the FULL suite (141 files), not a sliver. Hermetic deps via uv; conftest
  // supplies a git-identity floor (a missing one cost 19 silent failures before).
  // `-rs` surfaces every skip + reason into the sealed log — a skip is unmeasured,
  // never a pass, so it must be auditable, not hidden behind a green dot.
  { id: 'pytest.suite', gate: 'commit', cmd: ['uv', 'run', '--python', '3.12',
      '--with', 'pytest', '--with', 'cryptography', '--with', 'pyyaml', '--with', 'networkx',
      'python', '-m', 'pytest', 'tests/', 'axiom/tests/', '-rs'] },
  // Rust: all three first-party crates. crawler/ (core pillar, 34 tests) and tui/
  // were covered by NOTHING before this; the Makefile test-rust ran axiom/rust only.
  // tui currently has 0 tests, so its lane verifies the crate still COMPILES.
  { id: 'rust.crawler', gate: 'commit', cmd: ['cargo', 'test', '--manifest-path', 'crawler/Cargo.toml'] },
  { id: 'rust.axiom', gate: 'commit', cmd: ['cargo', 'test', '--manifest-path', 'axiom/rust/Cargo.toml'] },
  { id: 'rust.tui', gate: 'commit', cmd: ['cargo', 'test', '--manifest-path', 'tui/Cargo.toml'] },
  // Docs gate (Director: "documentation has to be updated before CI is run"). The
  // docs/ knowledge bundle must be OKF-conformant (§9: every concept has a non-empty
  // `type`) AND fresh (generated indexes/frontmatter current — a body changed without
  // re-running gen_okf.py --write fails this). CI does not care WHO ran the generator
  // (human, agent, or eventually the lgwks daemon); only that the bundle is current.
  // See docs/concepts/knowledge-format.md.
  { id: 'docs.okf', gate: 'commit', cmd: ['python3', 'scripts/gen_okf.py', '--verify'] },
];

// Tier-specific Keel runners (now VENDORED at the pinned SHA — #241). Each runs over
// lgwks.profile.json and needs a corresponding profile `block`; the runner FAULTS/BLOCKS if the
// block is absent (it has nothing to drive), so a tier whose evidence lgwks has not yet tailored is
// honestly BLOCKED (unknown ≠ pass), NOT faked green and NOT a runner fault. release ⊇ nightly.
// The runner FILES are required for a tier to be evaluable at all — a missing file => BLOCKED too
// (defensive; #235's silent --tier no-op must never return).
// Each tier lane carries the DYNAMIC concept it actually proves, passed to the runner via
// --concept. Without it the runner falls back to profile.gate_concept (lgwks_floor = the four
// STATIC atoms), which a dynamic scenario never measures → an honest-but-permanent BLOCKED even
// when every driven vector holds (verified 2026-06-22, #311). This is NOT gate-weakening: the
// static floor still runs in full at every tier (lanes = [...COMMIT_LANES, ...tier lanes], and the
// verdict requires EVERY lane to pass). The concept here ADDS a dynamic dimension on top of the
// floor — the simulate lane proves `well_crossed` (the input-envelope concept), the sim lane proves
// `concurrent_safe` (the interleaving concept), latency proves `latency_bounded`. soak takes NO
// concept: it is envelope-relative (acceptEnvelope over envelope.target), not concept-gated.
const TIER_RUNNERS = {
  nightly: [
    { id: 'simulate.envelope', file: 'run-simulate.mjs', block: 'simulate', concept: 'well_crossed' },
    { id: 'sim.interleave', file: 'run-sim.mjs', block: 'sim', concept: 'concurrent_safe' },
  ],
  release: [
    { id: 'simulate.envelope', file: 'run-simulate.mjs', block: 'simulate', concept: 'well_crossed' },
    { id: 'sim.interleave', file: 'run-sim.mjs', block: 'sim', concept: 'concurrent_safe' },
    { id: 'soak.capacity', file: 'run-soak.mjs', block: 'soak' },
    { id: 'latency.budget', file: 'run-latency.mjs', block: 'latency', concept: 'latency_bounded' },
  ],
};
// The target tailoring profile. Overridable via LGWKS_CI_TARGET_PROFILE so the tier-evaluability
// guard (BLOCKED on missing/partial evidence) stays testable against a SYNTHETIC partial profile —
// the guard's correctness must not depend on the real profile being perpetually incomplete. The
// override is a test seam only; production always uses the default.
const TARGET_PROFILE = process.env.LGWKS_CI_TARGET_PROFILE || 'lgwks.profile.json';
const TARGET_PROFILE_PATH = isAbsolute(TARGET_PROFILE) ? TARGET_PROFILE : join(ROOT, TARGET_PROFILE);

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
  // A spawn failure (e.g. tool not installed) sets r.error and leaves r.status null.
  // Record it explicitly and treat it as a FAIL — an unrunnable check is never a pass.
  const spawnErr = r.error ? `\n=== SPAWN ERROR ===\n${r.error.stack || r.error.message || String(r.error)}\n` : '';
  writeFileSync(log, `$ ${lane.cmd.join(' ')}\n\n=== STDOUT ===\n${r.stdout || ''}\n=== STDERR ===\n${r.stderr || ''}${spawnErr}\n=== EXIT ${r.status} ===\n`);
  // pass ONLY on a clean exit 0; null (spawn error) / non-zero → fail (fail-closed).
  const ok = r.status === 0 && !r.error;
  return { id: lane.id, gate: lane.gate, status: ok ? 'pass' : 'fail', exit: r.status, ms, log: log.slice(ROOT.length + 1) };
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

  // Honest BLOCKED for nightly/release. Three distinct unknowns, none a fake pass:
  //   (1) a tier-runner file is missing (un-vendored) — defensive; #241 vendored them all.
  //   (2) lgwks.profile.json declares NONE of the tier's evidence blocks — runners ready, evidence
  //       not yet tailored.
  //   (3) the profile declares SOME but not ALL of the tier's required blocks — a partial tailoring.
  //       The undeclared blocks are unmeasured axes; running only the declared lanes would return a
  //       verdict that SILENTLY OMITS them (release ⊇ {simulate,sim,soak,latency} — declaring only
  //       simulate+sim must not let release GO without soak/latency). unknown ≠ pass, so a partial
  //       tier BLOCKS too, naming exactly which blocks are still missing. (#311)
  const lanes = [...COMMIT_LANES];
  if (tier !== 'commit') {
    const specs = TIER_RUNNERS[tier] || [];
    const missing = specs.filter((s) => !existsSync(keel(s.file))).map((s) => s.file);
    let declared = [];
    let undeclared = [];
    try {
      const profile = JSON.parse(readFileSync(TARGET_PROFILE_PATH, 'utf8'));
      const isDeclared = (s) => Array.isArray(profile[s.block]) && profile[s.block].length;
      declared = specs.filter(isDeclared);
      undeclared = specs.filter((s) => !isDeclared(s)).map((s) => s.block);
    } catch (e) {
      const { manifestHash } = seal(runDir, id, tier, 'BLOCKED', [], { blocked_reason: `cannot read ${TARGET_PROFILE}: ${e.message}` });
      console.log(`BLOCKED — tier '${tier}': cannot read ${TARGET_PROFILE}`);
      console.log(`  seal=${manifestHash.slice(0, 16)}...  record=${runDir.slice(ROOT.length + 1)}`);
      process.exit(3);
    }
    if (missing.length || undeclared.length) {
      const reason = missing.length
        ? `tier '${tier}' runner(s) not vendored: ${missing.join(', ')} (re-vendor — see lgwks_verify/keel/VENDORED.txt).`
        : declared.length
        ? `tier '${tier}' is partially tailored: ${TARGET_PROFILE} declares ${declared.map((s) => s.block).join('/')} but NOT ${undeclared.join('/')} — the missing block(s) are unmeasured axes and running only the declared lanes would silently omit them (unknown ≠ pass). Add a profile.${undeclared[0]} block (and its siblings) with real harnesses.`
        : `tier '${tier}' is vendored and ready, but ${TARGET_PROFILE} declares no ${specs.map((s) => s.block).join('/')} evidence — the tier's evidence is not yet tailored, so it cannot return a verdict (unknown ≠ pass). Add a profile.${specs[0].block} block (or its siblings) with real harnesses.`;
      const { manifestHash } = seal(runDir, id, tier, 'BLOCKED', [], { blocked_reason: reason });
      console.log(`BLOCKED — ${reason}`);
      console.log(`  seal=${manifestHash.slice(0, 16)}...  record=${runDir.slice(ROOT.length + 1)}`);
      process.exit(3);
    }
    // Evidence IS declared → append the tier runner lanes over the target profile, each gated on
    // the dynamic concept it proves (soak is envelope-relative and takes no --concept).
    for (const s of declared)
      lanes.push({ id: s.id, gate: tier, cmd: [NODE, keel(s.file), '--profile', TARGET_PROFILE_PATH,
        ...(s.concept ? ['--concept', s.concept] : [])] });
  }

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
