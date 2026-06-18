#!/usr/bin/env node
// run-registry.mjs — run a host CI registry THROUGH the Keel authority (the wiring).
//
// This is the second front-end onto the shared engine (engine.mjs). It ingests a
// `lwks.verify.registry/v0` document (e.g. logic-os-kernel's scripts/ci/registry.json),
// maps every verifier onto a Keel atom via adapters/registry.mjs, evaluates each as a
// content-addressed node (re-runs that touch nothing REUSE — the 171s test does not
// re-execute on byte-identical source), composes the gate concept in three-valued logic,
// and reports atom-COVERAGE — the honest H1 measurement of how much of the 20-atom
// Excellent-Code space the host's CI actually exercises with evidence (unknown ≠ pass).
//
// Standalone: a git repo gets a fast/sound git fingerprint; anything else falls back to a
// pure content fingerprint. No network. Identity is content, not clock.
//
// Usage:  node src/run-registry.mjs --registry <file> [--root <dir>] [--concept <id>] [--tier commit|nightly|release]
// Exit:   0 GO (gate true) · 1 NO-GO/BLOCKED (gate false/unknown) · 2 runner fault.

import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H, hashFile } from './anchor.mjs';
import { composeReport, coverage, contentFingerprint, collectAtoms } from './engine.mjs';
import { registryActivations } from './adapters/registry.mjs';
import { symbolic, ai, renderAI } from './project.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };

/** Sound, fast staleness fingerprint of a git working tree; null if not a git repo. */
function gitFingerprint(root) {
  const tree = spawnSync('git', ['-C', root, 'rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' });
  if (tree.status !== 0) return null;
  const st = spawnSync('git', ['-C', root, 'status', '--porcelain', '--untracked-files=all'],
    { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  // Exclude Keel's OWN output (.keel/) and build noise from the dirty set: writing the anchor
  // would otherwise dirty the tree and change the next run's fingerprint, defeating reuse
  // (Keel invalidating itself). These paths never constitute the code under verification.
  const IGNORE = ['.keel/', '.git/', 'node_modules/', 'target/', '.ci-runs/'];
  const lines = (st.stdout || '').split('\n')
    .filter(Boolean)
    .filter(l => !IGNORE.some(x => l.slice(3).trim().replace(/^"|"$/g, '').startsWith(x)));
  if (!lines.length) return H('git-tree', tree.stdout.trim());
  // working tree is dirty: fold in the porcelain status AND the content of every changed
  // path, so any uncommitted edit changes the fingerprint (no stale reuse of a pre-edit pass).
  const parts = ['git-tree', tree.stdout.trim(), 'dirty', lines.join('\n')];
  for (const line of lines) {
    let p = line.slice(3).trim();
    if (p.includes(' -> ')) p = p.split(' -> ').pop();           // rename: hash the new path
    p = p.replace(/^"|"$/g, '');
    if (p) parts.push(p, hashFile(join(root, p)));
  }
  return H(...parts);
}

function fingerprintRoot(root) {
  return gitFingerprint(root) || contentFingerprint(root);
}

async function main() {
  const registryPath = arg('--registry');
  if (!registryPath) {
    console.error('usage: run-registry.mjs --registry <file> [--root <dir>] [--concept <id>] [--tier commit]');
    process.exit(2);
  }
  const root = arg('--root', process.cwd());
  const tier = arg('--tier', 'commit');
  const concurrency = Number(arg('--concurrency')) || undefined; // undefined → engine default

  const atomsDoc = JSON.parse(readFileSync(join(SCHEMA, 'atoms.json'), 'utf8'));
  const conceptsDoc = JSON.parse(readFileSync(join(SCHEMA, 'concepts.json'), 'utf8'));
  const reg = JSON.parse(readFileSync(registryPath, 'utf8'));

  const gateId = arg('--concept', reg.gate_concept || 'sound');
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  // tier-scoped verifiers (the host's registry tiers map straight through)
  const verifiers = (reg.verifiers || []).filter(v => (v.tier || 'commit') === tier);
  const dockerPresent = spawnSync('bash', ['-c', '[ -S /var/run/docker.sock ]']).status === 0;

  // one workspace unit, fingerprinted once: sound staleness (reuse only on identical source)
  const fingerprint = fingerprintRoot(root);
  const unit = { id: 'workspace', unit: 'workspace', path: root, root, fingerprint };

  const { activations, unmapped } =
    registryActivations({ ...reg, verifiers }, { atomsDoc, unit, dockerPresent });

  const anchor = new Anchor(join(root, '.keel'));
  const composed = await composeReport({ activations, gate, anchor, concurrency });
  const cov = coverage(atomsDoc, composed.atomValues);
  const runId = H('registry', reg.schema || 'reg', fingerprint, gateId, tier);

  const report = {
    run: runId, gate: composed.gate, atoms: composed.atoms,
    concepts: [composed.gate], recomputed: composed.recomputed, reused: composed.reused,
  };
  const sym = symbolic(report);
  const aip = ai(report, atomsDoc.atoms);

  anchor.seal(runId, { gate: gateId, verdict: composed.gate.verdict, tier, coverage: cov });
  writeFileSync(join(anchor.dir, `projection-symbolic-${runId}.json`), JSON.stringify(sym, null, 2) + '\n');
  writeFileSync(join(anchor.dir, `projection-ai-${runId}.json`), JSON.stringify(aip, null, 2) + '\n');
  // stable-named latest result for the host CI wrapper to consume
  writeFileSync(join(anchor.dir, 'latest-registry.json'), JSON.stringify({
    schema: 'keel.registry-run/v0', run: runId, root, tier, gate: gateId,
    verdict: composed.gate.verdict, coverage: cov, crossing: composed.crossing,
    advisories: composed.advisories.map(a => ({ source: a.source, atom: a.atom, value: a.value, role: a.role })),
    unmapped: unmapped.map(u => u.id), ai: aip,
  }, null, 2) + '\n');

  // ── render ──
  const bar = '═'.repeat(64);
  console.log(bar);
  console.log(`KEEL ⇐ registry '${reg.schema}'  ·  tier=${tier}  ·  gate='${gateId}'`);
  console.log(`verifiers=${activations.length} mapped${unmapped.length ? ` (+${unmapped.length} UNMAPPED)` : ''}  ·  recomputed=${composed.recomputed} reused=${composed.reused}  ·  docker=${dockerPresent ? 'present' : 'absent'}`);
  console.log(`crossing: ${composed.crossing.points} structural point(s) crossed concurrently (${composed.crossing.failed} failed, ${composed.crossing.unknown} unknown)`);
  console.log(bar);
  console.log(renderAI(aip));
  if (composed.advisories.length) {
    console.log(bar);
    console.log(`⚠ ADVISORY (surfaced, never blocks the verdict) — ${composed.advisories.length} signal(s):`);
    for (const a of composed.advisories)
      console.log(`     · ${a.source || a.atom} = ${a.value}${a.role ? ` [${a.role}]` : ''}${a.reason ? ` — ${a.reason}` : ''}`);
  }
  console.log(bar);
  // coverage — the H1 instrument. Covered = an atom with a DEFINITE (true|false) verdict.
  console.log(`ATOM COVERAGE — ${cov.covered}/${cov.total} atoms exercised with evidence (${(cov.ratio * 100).toFixed(0)}%); ${cov.uncovered} unknown (unbound/tool-absent — NOT counted)`);
  console.log(`  covered:   ${cov.covered_atoms.join(', ') || '(none)'}`);
  console.log(`  uncovered: ${cov.uncovered_atoms.join(', ') || '(none)'}`);
  if (unmapped.length) {
    console.log(`  ⚠ unmapped verifiers (evidence not yet wired to an atom — mapping debt):`);
    for (const u of unmapped) console.log(`     · ${u.id} — ${u.why}`);
  }
  // which gated atoms (if any) are blocking the verdict
  const gatedUnknown = [...collectAtoms(gate.formula)].filter(a => composed.atomValues[a] === 'unknown');
  if (composed.gate.verdict !== 'true' && gatedUnknown.length) {
    console.log(`  gate '${gateId}' blocked-by-unknown: ${gatedUnknown.join(', ')}  (bind evidence; unknown ≠ pass)`);
  }
  console.log(bar);
  console.log(`anchor: ${join(root, '.keel')}/manifest-${runId}.json  ·  latest: .keel/latest-registry.json`);

  process.exit(composed.gate.verdict === 'true' ? 0 : 1);
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — tool-qualification failure (DO-330); treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
