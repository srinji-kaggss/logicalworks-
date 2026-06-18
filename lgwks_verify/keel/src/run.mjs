#!/usr/bin/env node
// run.mjs — the runner (the thin, swappable operational surface; docs/06 §6.4).
//
// Loads the restrictive ontology (schema/atoms.json, schema/concepts.json) and a
// tailoring profile, enumerates the target's units, AUTO-ACTIVATES each atom the gate
// concept references against each matching unit (docs/01 §1.2), composes the verdict
// with the three-valued concept algebra, projects it for symbolic + AI consumers, and
// seals a content-addressed manifest. No network. Identity is content, not clock.
//
// Usage:  node src/run.mjs --profile <profile.json> [--concept <id>]
// Exit:   0 GO (gate true) · 1 NO-GO/BLOCKED (false/unknown) · 2 runner fault.

import { readFileSync, writeFileSync, globSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H, hashFile } from './anchor.mjs';
import { symbolic, ai, renderAI } from './project.mjs';
import { composeReport, contentFingerprint, collectAtoms } from './engine.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };

/** Enumerate units per the profile's discovery rules. */
function discoverUnits(profile, root) {
  const units = [];
  for (const rule of profile.units) {
    const d = rule.discover;
    if (d.type === 'literal') {
      for (const v of d.values || []) {
        const path = v === '.' ? root : join(root, v);
        units.push({ id: v, unit: rule.unit, path, root: path });
      }
    } else if (d.type === 'manifest' || d.type === 'glob') {
      for (const m of globSync(d.pattern, { cwd: root })) {
        const isManifest = d.type === 'manifest';
        const unitDir = isManifest ? dirname(m) : m;
        units.push({
          id: unitDir, unit: rule.unit,
          path: join(root, unitDir), root: join(root, unitDir),
          manifest: isManifest ? join(root, m) : undefined,
        });
      }
    }
  }
  return units;
}

async function main() {
  const profilePath = arg('--profile');
  if (!profilePath) { console.error('usage: run.mjs --profile <profile.json> [--concept <id>] [--concurrency N]'); process.exit(2); }
  const concurrency = Number(arg('--concurrency')) || undefined;

  const atomsDoc = JSON.parse(readFileSync(join(SCHEMA, 'atoms.json'), 'utf8'));
  const conceptsDoc = JSON.parse(readFileSync(join(SCHEMA, 'concepts.json'), 'utf8'));
  const profile = JSON.parse(readFileSync(profilePath, 'utf8'));

  const root = profile.target?.root || process.cwd();
  const gateId = arg('--concept') || profile.gate_concept || 'sound';
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  const units = discoverUnits(profile, root);
  // pre-compute each unit's content fingerprint once (drives staleness; docs/01 §1.3)
  for (const u of units) u.fingerprint = u.manifest ? hashFile(u.manifest) : contentFingerprint(u.path);

  const anchor = new Anchor(join(process.cwd(), '.keel'));
  const activations = profileActivations(profile, units, atomsDoc, gate);
  const composed = await composeReport({ activations, gate, anchor, concurrency });
  const gateRes = composed.gate;
  const runId = H(units.map(u => [u.id, u.fingerprint]), gateId);
  const report = {
    run: runId, gate: gateRes, atoms: composed.atoms,
    concepts: [gateRes], recomputed: composed.recomputed, reused: composed.reused,
  };

  const sym = symbolic(report);
  const aip = ai(report, atomsDoc.atoms);
  const { manifest } = anchor.seal(runId, { gate: gateId, verdict: gateRes.verdict });
  writeFileSync(join(anchor.dir, `projection-symbolic-${runId}.json`), JSON.stringify(sym, null, 2) + '\n');
  writeFileSync(join(anchor.dir, `projection-ai-${runId}.json`), JSON.stringify(aip, null, 2) + '\n');
  void manifest;

  console.log('═'.repeat(60));
  console.log(`KEEL — gate '${gateId}'  ·  units=${units.length}  ·  recomputed=${anchor.recomputed} reused=${anchor.reused}`);
  console.log(`crossing: ${composed.crossing.points} structural point(s) crossed concurrently (${composed.crossing.failed} failed, ${composed.crossing.unknown} unknown)`);
  console.log('═'.repeat(60));
  console.log(renderAI(aip));
  if (composed.advisories.length) {
    console.log('═'.repeat(60));
    console.log(`⚠ ADVISORY (surfaced, never blocks) — ${composed.advisories.length} signal(s)`);
    for (const a of composed.advisories)
      console.log(`     · ${a.source || a.atom} = ${a.value}${a.reason ? ` — ${a.reason}` : ''}`);
  }
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/manifest-${runId}.json  ·  projections: .keel/projection-{symbolic,ai}-${runId}.json  (all ${report.atoms.length} atom evals in symbolic)`);
  process.exit(gateRes.verdict === 'true' ? 0 : 1);
}

/** Profile front-end: enumerate (atom,unit) activations the gate concept references. */
export function profileActivations(profile, units, atomsDoc, gate) {
  const atomDef = (id) => atomsDoc.atoms.find(a => a.id === id);
  const bindingFor = (id, unit) =>
    (profile.bindings || []).find(b => b.atom === id && (!b.unit || b.unit === unit.unit));
  const acts = [];
  for (const id of collectAtoms(gate.formula)) {
    const def = atomDef(id);
    if (!def) continue; // unbound in the ontology => composeReport fills it unknown
    const matching = units.filter(u => u.unit === (bindingFor(id, u)?.unit || def.unit));
    for (const u of matching) acts.push({ atomId: id, atomDef: def, binding: bindingFor(id, u), unit: u });
  }
  return acts;
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — tool-qualification failure (DO-330); treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
