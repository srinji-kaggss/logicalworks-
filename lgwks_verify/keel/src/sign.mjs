// sign.mjs — release-key signing for seals (Open Risk #5, docs/15 §15.4).
//
// A seal's manifest hash proves INTEGRITY (the content has not changed). It does not prove
// AUTHENTICITY (that this factory produced it) nor that history was not rewritten. R#5 adds a
// detached ed25519 signature over the seal's manifest hash, verified against a release public key
// held outside the run — so a consumer can tell a genuine release seal from a forged or replayed
// one. ed25519 is deterministic (no RNG): signing the same hash with the same key is reproducible,
// so this does not break Keel's content-addressed determinism.

import { sign as edSign, verify as edVerify, createPrivateKey, createPublicKey } from 'node:crypto';
import { readFileSync } from 'node:fs';

/** The release signing key (PEM) from KEEL_RELEASE_KEY (a file path), or null when unset/unreadable.
 *  Absent key ⇒ seals are unsigned (honest, self-asserted) — signing is opt-in for release runs. */
export function releaseSigningKey() {
  const p = process.env.KEEL_RELEASE_KEY;
  if (!p) return null;
  try { return readFileSync(p, 'utf8'); } catch { return null; }
}

/** Sign a seal's manifest hash with an ed25519 private key (PEM). Returns hex signature. */
export function signSeal(manifestHash, privatePem) {
  return edSign(null, Buffer.from(String(manifestHash)), createPrivateKey(privatePem)).toString('hex');
}

/** Verify a seal's signature against an ed25519 public key (PEM). Never throws — bad input is false. */
export function verifySealSig(manifestHash, sigHex, publicPem) {
  try {
    return edVerify(null, Buffer.from(String(manifestHash)), createPublicKey(publicPem), Buffer.from(sigHex, 'hex'));
  } catch {
    return false;
  }
}
