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
import { composeReport, contentFingerprint, collectAtoms, claimCoherence } from './engine.mjs';
import { validateProfile } from './validate.mjs';
import { qualifyTools } from './toolqual.mjs';
import { verifySafetyRefs } from './safetyrefs.mjs';

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
  const profileSchema = JSON.parse(readFileSync(join(SCHEMA, 'profile.schema.json'), 'utf8'));
  const profile = JSON.parse(readFileSync(profilePath, 'utf8'));

  // RESTRICTIVE load gate (#648 item 1): validate the fill before any run. A malformed
  // profile is refused as a runner fault (exit 2), never silently half-honoured (docs/03).
  const profileErrs = validateProfile(profile, { schema: profileSchema, atomsDoc, conceptsDoc });
  if (profileErrs.length) {
    console.error(`⚠ PROFILE INVALID (${profileErrs.length}) — refusing to run (RESTRICTIVE; docs/03 §3.1):`);
    for (const e of profileErrs) console.error('   · ' + e);
    process.exit(2);
  }

  const root = profile.target?.root || process.cwd();

  // EXECUTABLE tool qualification (Open Risk #2, docs/15 §15.4): a safety_case's evidence tools
  // claim trustworthiness; here Keel RUNS each declared fixture (planted defect it must flag +
  // clean input it must pass). A tool that fails its own fixture cannot be trusted to catch what
  // it claims — NO-GO. Skipped tools (no fixture / toolchain absent) are surfaced, never a pass;
  // whether a fixture was REQUIRED is enforced at validation (self-qualified under high intent).
  if (profile.safety_case) {
    const tqRows = qualifyTools(profile.safety_case, { cwd: root });
    const failed = tqRows.filter((r) => r.ok === false);
    if (failed.length) {
      console.error('═'.repeat(60));
      console.error(`⛔ NO-GO — TOOL QUALIFICATION FAILED: ${failed.length} evidence tool(s) did not pass their own fixture:`);
      for (const r of failed) console.error(`     · ${r.tool} — ${r.why}`);
      console.error(`   A tool that cannot demonstrate it catches defects must not produce gating evidence. (tool unqualified ⇒ NO-GO)`);
      console.error('═'.repeat(60));
      process.exit(1);
    }
    for (const r of tqRows.filter((x) => x.skipped)) console.log(`○ tool-qualification SKIPPED (not a pass): ${r.tool} — ${r.why}`);

    // REFERENCE VERIFICATION (Open Risk #1, docs/15 §15.4): a safety-case reference must RESOLVE —
    // exist (under high intent), match its declared content hash, and (if signed) verify against the
    // trust anchor. A string ref pointing at nothing/altered/forged content is NO-GO.
    const intent = profile.safety_case.certification_intent || 'none';
    const highIntent = intent === 'internal-assurance' || intent === 'certification-support';
    const refRows = verifySafetyRefs(profile.safety_case, { root, highIntent });
    const refFailed = refRows.filter((r) => r.ok === false);
    if (refFailed.length) {
      console.error('═'.repeat(60));
      console.error(`⛔ NO-GO — SAFETY-CASE REFERENCE(S) UNVERIFIED: ${refFailed.length} reference(s) did not resolve:`);
      for (const r of refFailed) console.error(`     · ${r.key} — ${r.why}`);
      console.error(`   A safety-case reference must point at real, unaltered, attested evidence. (unresolved reference ⇒ NO-GO)`);
      console.error('═'.repeat(60));
      process.exit(1);
    }
  }

  const gateId = arg('--concept') || profile.gate_concept || 'sound';
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  const units = discoverUnits(profile, root);
  // pre-compute each unit's content fingerprint once (drives staleness; docs/01 §1.3)
  for (const u of units) u.fingerprint = u.manifest ? hashFile(u.manifest) : contentFingerprint(u.path);

  // assurance_claim (docs/09): the concept the profile ASSERTS it meets. Its atoms are activated
  // and evaluated alongside the enforced gate, so an honest claim can be demonstrated — and a claim
  // that outruns its evidence is BLOCKED below (claim-coherence). Defaults to the gate concept.
  const claimId = profile.assurance_claim || null;
  const claim = claimId ? conceptsDoc.concepts.find(c => c.id === claimId) : null;
  if (claimId && !claim) { console.error(`unknown assurance_claim concept '${claimId}'`); process.exit(2); }
  const atomIds = new Set([...collectAtoms(gate.formula), ...(claim ? collectAtoms(claim.formula) : [])]);

  const anchor = new Anchor(join(process.cwd(), '.keel'));
  const activations = profileActivations(profile, units, atomsDoc, atomIds);
  const composed = await composeReport({ activations, gate, anchor, concurrency, thresholds: profile.thresholds || {}, policy: profile.execution_policy || null });
  const gateRes = composed.gate;

  // CLAIM-COHERENCE GATE: you may claim only what you demonstrated (docs/09). Fires only when a
  // claim is asserted; blocks on the gap between assertion and evidence, never on un-claimed unknowns.
  let claimVerdict = null;
  if (claim) {
    claimVerdict = claimCoherence(claim.formula, composed.atomValues);
    // REFUTED: the claimed concept's evidence is FALSE. The claim is disproven, not merely
    // unproven — measured ≠ demonstrated (Open Risk #4). A refuted claim is NO-GO even when the
    // narrow enforced gate would pass.
    if (claimVerdict.refuted) {
      console.error('═'.repeat(60));
      console.error(`⛔ NO-GO — CLAIM REFUTED: profile asserts '${claimId}', but the evidence DISPROVES it:`);
      for (const a of claimVerdict.refutingAtoms) console.error(`     · ${a} = false (measured and failed)`);
      console.error(`   A claimed concept whose evidence is FALSE is refuted — "measured" is not "demonstrated". (claim refuted ⇒ NO-GO)`);
      console.error('═'.repeat(60));
      process.exit(1);
    }
    // UNDEMONSTRATED: the claim outran its evidence (a claimed atom is unrun/unbound ⇒ unknown).
    if (!claimVerdict.coherent) {
      console.error('═'.repeat(60));
      console.error(`⛔ CLAIM NOT DEMONSTRATED — profile asserts '${claimId}' but ${claimVerdict.undemonstrated.length} atom(s) have NO evidence (unrun/unbound):`);
      for (const a of claimVerdict.undemonstrated) console.error(`     · ${a} = ${composed.atomValues[a] || 'unknown'}`);
      console.error(`   A claim that outruns its evidence is overclaim. Demonstrate these atoms or drop the claim to one you can prove. (claim ≠ evidence ⇒ NO-GO)`);
      console.error('═'.repeat(60));
      process.exit(1);
    }
  }
  const runId = H(units.map(u => [u.id, u.fingerprint]), gateId, claimId || '');
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
  if (claim) {
    console.log('═'.repeat(60));
    console.log(`✓ claim '${claimId}' DEMONSTRATED — its formula HOLDS on the evidence (all ${claimVerdict.claimedAtoms.length} claimed atom(s) measured true; claim = evidence).`);
  }
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/manifest-${runId}.json  ·  projections: .keel/projection-{symbolic,ai}-${runId}.json  (all ${report.atoms.length} atom evals in symbolic)`);
  process.exit(gateRes.verdict === 'true' ? 0 : 1);
}

/** Profile front-end: enumerate (atom,unit) activations for the given atom-id set (the union of the
 *  gate concept's atoms and any assurance_claim's atoms). */
export function profileActivations(profile, units, atomsDoc, atomIds) {
  const atomDef = (id) => atomsDoc.atoms.find(a => a.id === id);
  const bindingFor = (id, unit) =>
    (profile.bindings || []).find(b => b.atom === id && (!b.unit || b.unit === unit.unit));
  const acts = [];
  for (const id of atomIds) {
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
