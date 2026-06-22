// simulate.mjs — the INPUT-ENVELOPE simulator (docs/04 §4.1 "envelope faults"; docs/09; issue #644-adjacent).
//
// The gap this closes (root cause of the weak gate, 2026-06-18): the rest of Keel verifies the
// code AT REST (resolve/compile/lint/dup/reproduce) and, where it exercises the running system,
// pushes only the LOAD scalar (soak.mjs). It has no model of the system's INPUT/SENSOR surface and
// never drives that surface through its envelope. §4.1 names three dynamic axes — time, interaction,
// envelope — and the "one bad afternoon from collapse" sentence is about THIS one. Treating the
// codebase as the airplane: this is the flight simulator that plays with the sensor values.
//
// Keel's deterministic job: from a declared sensor model, ENUMERATE the finite input crossing
// (nominal ∪ boundary ∪ off-nominal — boundary-value analysis, the DO-178C robustness substance),
// drive each vector through the system-under-test harness, and ∧ the oracle over every point (the
// system holds across its driven envelope iff EVERY input vector holds). On failure, report the
// exact breaking vector — "the sensor value where the bridge fails" (the finite-outcome crossing
// thesis, docs/07, applied to INPUTS instead of platforms). The harness is deferred behind the tool
// seam (per-target compiled code); enumeration + oracle-crossing is Keel's. Unmeasured ⇒ unknown
// (BLOCKS, never a silent pass; docs/02 §2.6). No RNG: enumeration is deterministic, so a fuzz-like
// sweep stays content-addressable and reproducible (it is systematic, not random).

import { verify as cryptoVerify, createPublicKey } from 'node:crypto';

const DEFAULT_MAX_VECTORS = 1024;

/** ed25519 detached-signature verification (A6 authenticity). Builtin crypto only. */
function verifyEd25519(contentBuf, signatureBuf, publicKeyPem) {
  const key = createPublicKey(publicKeyPem);
  return cryptoVerify(null, contentBuf, key, signatureBuf);
}

/** Build one sensor's value list: explicit `values`, plus numeric `range` boundary points
 *  (lo, hi, and — when probe_outside — lo-step / hi+step as off-nominal), plus explicit
 *  `offNominal`. Each entry is { v, off } where off marks an off-nominal/boundary-exceeding input. */
function sensorPoints(s) {
  const pts = [];
  for (const v of s.values || []) pts.push({ v, off: false });
  if (Array.isArray(s.range) && s.range.length === 2) {
    const [lo, hi] = s.range;
    const step = typeof s.step === 'number' ? s.step : 1;
    pts.push({ v: lo, off: false }, { v: hi, off: false });
    if (s.probe_outside !== false) pts.push({ v: lo - step, off: true }, { v: hi + step, off: true });
  }
  for (const v of s.offNominal || []) pts.push({ v, off: true });
  // de-dup by value while preserving "off" if any occurrence is off-nominal
  const seen = new Map();
  for (const p of pts) {
    const k = JSON.stringify(p.v);
    if (!seen.has(k)) seen.set(k, p);
    else if (p.off) seen.get(k).off = true;
  }
  return [...seen.values()];
}

/**
 * Enumerate the finite input crossing = the Cartesian product of every sensor's points, in
 * DETERMINISTIC order (sensors sorted by name; each sensor's points in declared order). Returns
 * { vectors } or { error } when the product exceeds the cap — NEVER a silent truncation (no silent
 * caps; the cap is honest and blocks). Each vector = { values:{name:v}, off:bool, label }.
 */
export function enumerateEnvelope(sensors, { cap = DEFAULT_MAX_VECTORS } = {}) {
  if (!Array.isArray(sensors) || !sensors.length) return { error: 'scenario declares no sensors — nothing to drive' };
  const names = sensors.map((s) => s.name).sort();
  const byName = Object.fromEntries(sensors.map((s) => [s.name, sensorPoints(s)]));
  for (const n of names) if (!byName[n].length) return { error: `sensor '${n}' enumerates to zero points (declare values / range / offNominal)` };

  const total = names.reduce((acc, n) => acc * byName[n].length, 1);
  if (total > cap) return { error: `input crossing is ${total} vectors > cap ${cap} — narrow the sensor model or raise max_vectors (refusing to silently sample)` };

  let vectors = [{ values: {}, off: false, parts: [] }];
  for (const n of names) {
    const next = [];
    for (const base of vectors)
      for (const p of byName[n]) next.push({ values: { ...base.values, [n]: p.v }, off: base.off || p.off, parts: [...base.parts, `${n}=${JSON.stringify(p.v)}${p.off ? '!' : ''}`] });
    vectors = next;
  }
  return { vectors: vectors.map((v) => ({ values: v.values, off: v.off, label: v.parts.join(' ') })) };
}

/**
 * Cross the oracle over the driven vectors (Kleene ∧): the scenario atom is `true` only if EVERY
 * vector held the oracle; one violated vector dominates to `false`; an unmeasured vector (harness
 * absent / self-skip / fault) is `unknown` (blocks). Reports the FIRST breaking vector — the input
 * at which the bridge fails — and counts how many of the driven points were off-nominal.
 *
 * points = [{ label, value:'true'|'false'|'unknown', off:bool, reason? }]
 */
export function crossOracle(points) {
  if (!points.length) return { value: 'unknown', breaking: null, driven: 0, offNominal: 0, reason: 'no vectors driven' };
  const violated = points.find((p) => p.value === 'false');
  const unmeasured = points.find((p) => p.value === 'unknown');
  const value = violated ? 'false' : unmeasured ? 'unknown' : 'true';
  const breaking = violated || (value === 'unknown' ? unmeasured : null);
  return {
    value,
    breaking: breaking ? { label: breaking.label, off: breaking.off, reason: breaking.reason } : null,
    driven: points.length,
    offNominal: points.filter((p) => p.off).length,
  };
}

/** Multi-actor interleaving enumeration (docs/04 §4.5; axioms A1 closed-loop / A7 repeatable):
 *  the order-preserving merges of N concurrent actors' step sequences — the finite SCHEDULE space
 *  (the interaction analogue of the input crossing). The system is concurrency-correct iff the
 *  consistency oracle holds on EVERY interleaving; the breaking one is the race. Deterministic order;
 *  the count is the multinomial (Σnᵢ)!/∏nᵢ! — bounded by `cap` (no silent sampling). */
export function enumerateInterleavings(actors, { cap = 1024 } = {}) {
  if (!Array.isArray(actors) || !actors.length) return { error: 'scenario declares no actors' };
  const seqs = actors.map((a) => (a.steps || []).map((op) => ({ actor: a.id, op })));
  if (seqs.some((s) => !s.length)) return { error: 'an actor declares no steps' };
  const fact = (n) => { let r = 1; for (let i = 2; i <= n; i++) r *= i; return r; };
  const total = seqs.reduce((a, s) => a + s.length, 0);
  const count = fact(total) / seqs.reduce((a, s) => a * fact(s.length), 1);
  if (count > cap) return { error: `${count} interleavings > cap ${cap} — reduce actors/steps or raise max_interleavings (refusing to silently sample)` };
  const out = [];
  (function rec(remaining, acc) {
    if (remaining.every((r) => r.length === 0)) { out.push(acc); return; }
    for (let i = 0; i < remaining.length; i++) {
      if (!remaining[i].length) continue;
      rec(remaining.map((r, j) => (j === i ? r.slice(1) : r)), [...acc, remaining[i][0]]);
    }
  })(seqs, []);
  return { schedules: out.map((steps) => ({ steps, label: steps.map((s) => `${s.actor}:${s.op}`).join('>') })) };
}

/** A6 (validated_aircraft_correlation): the oracle's truth must trace to REFERENCE DATA, not to
 *  developer/AI intuition. A `reference` block is a table of {when:{sensor:val,…}, expect:value}.
 *  This is the deterministic key for one vector's reference lookup. */
function refKey(values) {
  return JSON.stringify(Object.keys(values).sort().map((k) => [k, values[k]]));
}

/** Find the reference entry whose `when` matches a driven vector exactly (every declared sensor). */
export function referenceFor(reference, values) {
  if (!reference || !Array.isArray(reference.data)) return null;
  const want = refKey(values);
  return reference.data.find((e) => refKey(e.when || {}) === want) || null;
}

/** Compare a system output to its reference within tolerance (A6). Numbers: |out-expect| ≤ tol.
 *  Anything else: strict deep-equal. Returns 'true' | 'false'. The verdict's truth is the REFERENCE,
 *  so it cannot be an author's intuition about pass/fail. */
export function compareToReference(output, expect, tolerance = 0) {
  if (typeof expect === 'number' && typeof output === 'number')
    return Math.abs(output - expect) <= tolerance ? 'true' : 'false';
  return JSON.stringify(output) === JSON.stringify(expect) ? 'true' : 'false';
}

/** A6 AUTHENTICITY (the external trust root): verify a detached ed25519 signature over the reference
 *  bytes against a configured public key. A valid signature means the reference was attested by
 *  whoever holds the private key — a party OUTSIDE the AI authorship loop. That externality is the
 *  independence the gate otherwise lacks. Returns true|false; throws only on malformed key/sig input
 *  (caller treats a throw as a hard block, never a pass). Uses node:crypto (builtin, zero-dep). */
export function verifyReferenceSignature(contentBuf, signatureBuf, publicKeyPem) {
  return verifyEd25519(contentBuf, signatureBuf, publicKeyPem);
}

export { DEFAULT_MAX_VECTORS };
