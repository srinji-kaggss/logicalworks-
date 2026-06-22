#!/usr/bin/env node
// run-simulate.mjs — the input-envelope simulator front-end (docs/09; docs/04 §4.1; issue #644-adjacent).
//
// Treats the codebase as the airplane and plays with its sensor values. For each `simulate` scenario
// in the profile, Keel ENUMERATES the finite input crossing (nominal→boundary→off-nominal) from the
// declared sensor model, drives each vector through the system-under-test harness as a
// content-addressed node (concurrent, reused on unchanged source+vector), and crosses the oracle (∧)
// over every vector. The scenario's atom is `true` iff the oracle held on EVERY input vector; one
// violated vector ⇒ `false` and the breaking vector is reported; an unmeasured vector ⇒ `unknown`.
// Scenario atoms compose into the gate concept (engine.evalConcept) exactly like the static gate.
//
// The harness (the running system) is deferred behind the tool seam; enumeration + oracle-crossing
// is Keel's deterministic job. Unmeasured ⇒ BLOCKS (unknown ≠ pass; docs/02 §2.6).
//
// Usage:  node src/run-simulate.mjs --profile <profile.json> [--concept <id>] [--concurrency N]
// Exit:   0 GO (oracle held across every driven envelope) · 1 NO-GO/BLOCKED · 2 runner fault.

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Anchor, H } from './anchor.mjs';
import { contentFingerprint, kleeneAll, collectAtoms } from './engine.mjs';
import { evalConcept } from './concepts.mjs';
import { mapPool, defaultConcurrency } from './concurrency.mjs';
import { validateProfile } from './validate.mjs';
import { enumerateEnvelope, crossOracle, referenceFor, compareToReference, verifyReferenceSignature } from './simulate.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCHEMA = join(HERE, '..', 'schema');
const SKIP_EXIT = 77;
const DEFAULT_TIMEOUT_MS = 600_000;

const argv = process.argv.slice(2);
const arg = (k) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };
function has(bin) { return spawnSync('bash', ['-c', `command -v ${bin}`]).status === 0; }

/** Drive ONE input vector through the harness and apply the oracle.
 *  Two oracle modes:
 *   - EXIT (default): exit 0 held · nonzero violated · 77 unknown. The harness author decides
 *     pass/fail — convenient, but intuition-based (A6 warns against trusting this for truth).
 *   - REFERENCE (scenario has `reference`): the harness EMITS the system's output on stdout; Keel
 *     compares it to the declared reference datum within tolerance (A6). Truth traces to the
 *     reference data, not the harness's own judgement. No reference entry for a vector ⇒ unknown
 *     (un-validatable, blocks) — you cannot pass an input you have no reference for. */
function driveVector(harness, vector, root, reference) {
  const env = { ...process.env, ...harness.env, KEEL_VECTOR: JSON.stringify(vector.values) };
  for (const [k, v] of Object.entries(vector.values)) env[`KEEL_SENSOR_${k.toUpperCase()}`] = String(v);
  const cwd = harness.cwd ? join(root, harness.cwd) : root;
  const r = spawnSync(harness.tool, harness.argv, { cwd, env, encoding: 'utf8', timeout: harness.timeout_ms || DEFAULT_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 });
  const base = { label: vector.label, off: vector.off };
  if (r.error) return { ...base, value: 'unknown', reason: `harness failed to launch: ${r.error.message}` };
  if (r.status === SKIP_EXIT) return { ...base, value: 'unknown', reason: (r.stdout || '').trim().split('\n').pop()?.replace(/^SKIP:\s*/, '') || 'harness self-skipped' };

  if (reference) {
    if (r.status !== 0) return { ...base, value: 'unknown', reason: `harness exited ${r.status} — produced no output to validate against reference` };
    const entry = referenceFor(reference, vector.values);
    if (!entry) return { ...base, value: 'unknown', reason: `no reference datum for this vector — cannot validate (A6: truth must trace to reference data, not intuition)` };
    let out = (r.stdout || '').trim();
    const asNum = Number(out);
    if (out !== '' && !Number.isNaN(asNum)) out = asNum;
    const v = compareToReference(out, entry.expect, reference.tolerance || 0);
    return { ...base, value: v, reason: v === 'true' ? undefined : `output ${JSON.stringify(out)} ≠ reference ${JSON.stringify(entry.expect)} (±${reference.tolerance || 0})` };
  }
  return { ...base, value: r.status === 0 ? 'true' : 'false',
    reason: r.status === 0 ? undefined : `oracle violated (exit ${r.status})${(r.stderr || r.stdout) ? ': ' + (r.stderr || r.stdout).trim().split('\n').pop() : ''}` };
}

/** A6 provenance: resolve a scenario's reference to its actual data + a content hash that TRACES to
 *  a source (trace_to_source_data, immutable_record). `from` loads + hashes an external reference
 *  FILE (the trusted golden artifact); inline `data` hashes the table and must carry a `source_ref`
 *  (enforced by validate.mjs). Returns { ref, hash } or { error }. */
function resolveReference(reference, root, trustAnchorPem) {
  if (!reference) return { ref: null, hash: 'none', authenticated: 'n/a' };
  if (reference.from) {
    let rawBuf;
    try { rawBuf = readFileSync(join(root, reference.from)); }
    catch (e) { return { error: `reference file '${reference.from}' unreadable: ${e.message}` }; }
    const raw = rawBuf.toString('utf8');
    let loaded;
    try { loaded = JSON.parse(raw); } catch { return { error: `reference file '${reference.from}' is not valid JSON` }; }
    const data = Array.isArray(loaded) ? loaded : loaded.data;
    if (!Array.isArray(data)) return { error: `reference file '${reference.from}' has no data array` };
    const tolerance = reference.tolerance ?? (Array.isArray(loaded) ? 0 : loaded.tolerance) ?? 0;
    const source_ref = reference.source_ref || (Array.isArray(loaded) ? undefined : loaded.source_ref) || reference.from;
    // A6 AUTHENTICITY: verify a detached signature against the configured external trust anchor.
    let authenticated = 'self_asserted';
    if (reference.signature_file) {
      if (!trustAnchorPem) return { error: `reference declares signature_file but profile has no trust_anchor to verify it (cannot authenticate)` };
      let sigBuf;
      try { sigBuf = Buffer.from(readFileSync(join(root, reference.signature_file), 'utf8').trim(), 'base64'); }
      catch (e) { return { error: `signature file '${reference.signature_file}' unreadable: ${e.message}` }; }
      let ok;
      try { ok = verifyReferenceSignature(rawBuf, sigBuf, trustAnchorPem); }
      catch (e) { return { error: `signature verification errored (malformed key/sig): ${e.message}` }; }
      if (!ok) return { error: `reference signature INVALID — '${reference.from}' does not match its signature under the trust anchor (tampered or wrong key)` };
      authenticated = true;
    }
    return { ref: { tolerance, source_ref, data }, hash: H('ref-file/v1', reference.from, raw), authenticated };
  }
  return { ref: reference, hash: H('ref-inline/v1', reference.data || [], reference.tolerance || 0), authenticated: 'self_asserted' };
}

/** Build a content-addressed node for one scenario: enumerate its envelope, drive every vector,
 *  cross the oracle. The node id folds in source fingerprint + the full scenario spec + the RESOLVED
 *  reference content hash (so a changed/edited reference invalidates the verdict — A8). */
function scenarioNode(scn, root, fingerprint, concurrency, trustAnchorPem) {
  const resolved = resolveReference(scn.reference, root, trustAnchorPem);
  return {
    kind: `sim:${scn.name}`,
    params: { scenario: scn.name, atom: scn.atom },
    inputs: [fingerprint, H('sim-scn/v4', { sensors: scn.sensors, harness: { tool: scn.harness.tool, argv: scn.harness.argv, cwd: scn.harness.cwd || '', env: scn.harness.env || {} }, ref_hash: resolved.hash, authenticated: resolved.authenticated, max: scn.max_vectors || null })],
    async compute() {
      if (resolved.error) return { value: 'unknown', reason: `reference unresolved (A6): ${resolved.error}` };
      for (const bin of scn.harness.needs || []) if (!has(bin)) return { value: 'unknown', reason: `harness toolchain absent: ${bin}` };
      const en = enumerateEnvelope(scn.sensors, { cap: scn.max_vectors });
      if (en.error) return { value: 'unknown', reason: en.error };
      const points = await mapPool(en.vectors, concurrency, async (vec) => driveVector(scn.harness, vec, root, resolved.ref));
      const safe = points.map((p, i) => p && p.__poolError ? { label: en.vectors[i].label, off: en.vectors[i].off, value: 'unknown', reason: `driver fault: ${p.__poolError.message}` } : p);
      const oracle = crossOracle(safe);
      return { value: oracle.value, driven: oracle.driven, offNominal: oracle.offNominal,
        reference: resolved.ref ? { source_ref: resolved.ref.source_ref, hash: resolved.hash, authenticated: resolved.authenticated } : undefined,
        reason: oracle.breaking ? `broke at [${oracle.breaking.label}]${oracle.breaking.off ? ' (off-nominal)' : ''}${oracle.breaking.reason ? ' — ' + oracle.breaking.reason : ''}` : undefined };
    },
  };
}

async function main() {
  const profilePath = arg('--profile');
  if (!profilePath) { console.error('usage: run-simulate.mjs --profile <profile.json> [--concept <id>]'); process.exit(2); }
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

  const scenarios = profile.simulate || [];
  if (!scenarios.length) { console.error('⚠ no simulate scenarios declared — nothing to drive (docs/09). Add a profile.simulate block.'); process.exit(2); }
  for (const s of scenarios) if (!atomsDoc.atoms.find(a => a.id === s.atom)) { console.error(`simulate scenario '${s.name}' binds unknown atom '${s.atom}'`); process.exit(2); }

  const gateId = arg('--concept') || profile.gate_concept || 'sound';
  const gate = conceptsDoc.concepts.find(c => c.id === gateId);
  if (!gate) { console.error(`unknown concept '${gateId}'`); process.exit(2); }

  const root = profile.target?.root || process.cwd();
  const fingerprint = contentFingerprint(root);
  // A6 trust anchor: the external public key against which reference signatures are verified.
  let trustAnchorPem = null;
  if (profile.trust_anchor) {
    try { trustAnchorPem = readFileSync(join(root, profile.trust_anchor), 'utf8'); }
    catch (e) { console.error(`⚠ trust_anchor '${profile.trust_anchor}' unreadable: ${e.message}`); process.exit(2); }
  }
  const anchor = new Anchor(join(process.cwd(), '.keel'));

  const perAtom = {};
  const rows = [];
  for (const scn of scenarios) {
    const res = await anchor.evaluateAsync(scenarioNode(scn, root, fingerprint, concurrency, trustAnchorPem));
    const v = res.verdict || {};
    (perAtom[scn.atom] ||= []).push(v.value);
    rows.push({ name: scn.name, atom: scn.atom, value: v.value, driven: v.driven, offNominal: v.offNominal, authenticated: v.reference?.authenticated, reason: v.reason });
  }
  const atomValues = {};
  for (const id of Object.keys(perAtom)) atomValues[id] = kleeneAll(perAtom[id]);
  for (const id of collectAtoms(gate.formula)) if (!(id in atomValues)) atomValues[id] = 'unknown';
  const gateRes = evalConcept(gate, atomValues);

  const runId = H('simulate', fingerprint, gateId, scenarios.map(s => s.name));
  anchor.seal(runId, { tier: 'simulate', gate: gateId, verdict: gateRes.verdict });
  writeFileSync(join(anchor.dir, `simulate-${runId}.json`), JSON.stringify({ schema: 'keel.simulate-run/v0', run: runId, gate: gateId, verdict: gateRes.verdict, scenarios: rows, atomValues }, null, 2) + '\n');

  const mark = gateRes.verdict === 'true' ? 'GO' : gateRes.verdict === 'false' ? 'NO-GO' : 'BLOCKED';
  console.log('═'.repeat(60));
  console.log(`KEEL — input-envelope simulation  ·  gate '${gateId}'  ·  scenarios=${scenarios.length}  ·  recomputed=${anchor.recomputed} reused=${anchor.reused}`);
  console.log('═'.repeat(60));
  console.log(`${mark} — gate '${gateId}' = ${gateRes.verdict}  (run ${runId})`);
  for (const r of rows) {
    const glyph = r.value === 'true' ? '✓' : r.value === 'false' ? '✗' : '?';
    console.log(`  ${glyph} ${r.name.padEnd(26)} atom=${r.atom}  driven=${r.driven ?? '—'} (off-nominal ${r.offNominal ?? 0})${r.reason ? `  — ${r.reason}` : ''}`);
  }
  console.log('═'.repeat(60));
  console.log(`anchor: .keel/simulate-${runId}.json  ·  enumeration+oracle is Keel's; the harness (the running system) is the per-target seam`);
  process.exit(gateRes.verdict === 'true' ? 0 : 1);
}

main().catch((e) => {
  console.error('⚠ RUNNER FAULT (not a verdict) — treat as NO-GO:');
  console.error('   ' + (e && e.stack ? e.stack : e));
  process.exit(2);
});
