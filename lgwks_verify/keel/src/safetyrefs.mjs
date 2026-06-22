// safetyrefs.mjs — safety-case reference verification (Open Risk #1, docs/15 §15.4).
//
// safety_case references were bare strings: 'docs/safety/plan.md' could point at NOTHING, or at a
// file silently altered after review, and the gate never noticed. A gating reference must resolve.
// Here a reference is checked three ways, reusing the A6 machinery (file bytes + ed25519, builtins
// only):
//   EXISTENCE — under high intent the file must exist (a required artifact that is absent is a hole).
//   HASH      — when reference_integrity[key].hash is declared, sha256(file) must match (no drift).
//   SIGNATURE — when reference_integrity[key].signature_file is declared, a detached ed25519
//               signature over the file bytes must verify against trust_anchor.public_key_file
//               (attested OUTSIDE the AI authoring loop; a signature with no anchor cannot be trusted).
// A failure is NO-GO (run.mjs). Absence of an integrity spec under low intent ⇒ skipped, never a pass.

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { verifyReferenceSignature } from './simulate.mjs';

// The gating reference fields and how to read each from the safety_case (flat + nested).
const REF_PATHS = {
  safety_plan_ref: (sc) => sc.safety_plan_ref,
  hazard_analysis_ref: (sc) => sc.hazard_analysis_ref,
  requirements_traceability_ref: (sc) => sc.requirements_traceability_ref,
  verification_plan_ref: (sc) => sc.verification_plan_ref,
  configuration_index_ref: (sc) => sc.configuration_index_ref,
  independence_evidence_ref: (sc) => sc.independence?.evidence_ref,
  structural_coverage_source_ref: (sc) => sc.structural_coverage?.source_ref,
};

export const REFERENCE_KEYS = Object.keys(REF_PATHS);

function safeRead(p, enc) { try { return readFileSync(p, enc); } catch { return null; } }

/**
 * Verify a safety_case's references against the target tree.
 * Returns one row per declared reference: { key, ok, skipped, why }.
 *   ok === false → NO-GO (missing/mismatched/forged); ok === true → resolved + verified;
 *   skipped === true → not checked (low intent, no integrity spec) — surfaced, never a pass.
 */
export function verifySafetyRefs(sc, { root = '.', highIntent = false } = {}) {
  if (!sc) return [];
  const integ = sc.reference_integrity || {};
  const anchorPem = sc.trust_anchor?.public_key_file
    ? safeRead(join(root, sc.trust_anchor.public_key_file), 'utf8') : null;
  const rows = [];
  for (const [key, get] of Object.entries(REF_PATHS)) {
    const rel = get(sc);
    if (rel == null) continue;                 // reference not declared
    const spec = integ[key];
    const abs = join(root, rel);
    if (!existsSync(abs)) {
      if (highIntent || spec) rows.push({ key, ok: false, why: `referenced file does not exist: ${rel}` });
      else rows.push({ key, ok: null, skipped: true, why: `ref not checked (low intent, no integrity spec): ${rel}` });
      continue;
    }
    const buf = readFileSync(abs);
    if (spec?.hash) {
      const got = createHash('sha256').update(buf).digest('hex');
      if (got !== spec.hash) { rows.push({ key, ok: false, why: `content hash mismatch for ${rel}: declared ${spec.hash.slice(0, 16)}…, actual ${got.slice(0, 16)}… (reference altered after it was recorded)` }); continue; }
    }
    if (spec?.signature_file) {
      if (!anchorPem) { rows.push({ key, ok: false, why: `signature declared for ${rel} but no trust_anchor.public_key_file to verify it against (an unverifiable signature is not trust)` }); continue; }
      const sig = safeRead(join(root, spec.signature_file));
      if (!sig) { rows.push({ key, ok: false, why: `signature file missing: ${spec.signature_file}` }); continue; }
      let valid = false;
      try { valid = verifyReferenceSignature(buf, sig, anchorPem); } catch { valid = false; }
      if (!valid) { rows.push({ key, ok: false, why: `invalid signature for ${rel} — not attested by the trust anchor` }); continue; }
    }
    rows.push({ key, ok: true, why: spec ? 'reference exists and integrity verified' : 'reference exists (self-asserted; no integrity spec)' });
  }
  return rows;
}
