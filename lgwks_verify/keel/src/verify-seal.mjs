#!/usr/bin/env node
// verify-seal.mjs — transparency-record verifier (Open Risk #5, docs/15 §15.4).
//
// Verifies a Keel seal chain (.keel/_chain.jsonl) two ways:
//   INTEGRITY  — the chain is append-only and intact: each entry's `prev` equals the previous
//                entry's `manifest_hash`. A reordered, truncated, or rewritten history fails here.
//   AUTHENTICITY — each SIGNED entry's `sig` verifies against the release public key over its
//                manifest_hash. An unsigned entry is reported `self_asserted` (honest; never a
//                silent pass). A signed entry with a bad/forged signature FAILS.
//
// Exit 0 = chain intact and every signed seal verified · 1 = a broken link or invalid signature ·
// 2 = usage/IO fault. Determinism: pure over the chain bytes + the public key.
//
// Usage:  node src/verify-seal.mjs [--chain <_chain.jsonl>] [--pubkey <ed25519-public.pem>]

import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifySealSig } from './sign.mjs';

/**
 * Verify a parsed chain (array of {run, manifest_hash, prev, sig?}) against an optional public key.
 * Returns { ok, entries, signed, unsigned, problems[] }. Pure — no IO, unit-testable.
 */
export function verifyChain(entries, publicPem = null) {
  const problems = [];
  let signed = 0, unsigned = 0;
  // Append-only DAG, not a strict line: a deterministic (content-addressed) re-seal of unchanged
  // source produces an identical seal whose `prev` is the chain tip when that run STARTED — so two
  // siblings can legitimately share a parent. The integrity invariant is therefore that every
  // non-null `prev` references SOME earlier seal's manifest_hash (a real ancestor), and only the
  // genesis seal has prev=null. A `prev` that points at no earlier seal is a fabricated/dangling
  // link — a rewritten or out-of-order history. (Tail truncation cannot be detected from the chain
  // alone without an external tip witness — the honest residual, like the kernel-trust residual.)
  const earlier = new Set();
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (i === 0) {
      if ((e.prev ?? null) !== null) problems.push(`entry 0 (run ${e.run}): genesis seal must have prev=null, found ${e.prev}`);
    } else if (e.prev == null) {
      problems.push(`entry ${i} (run ${e.run}): prev=null but this is not the genesis seal (a second genesis = a rewritten chain)`);
    } else if (!earlier.has(e.prev)) {
      problems.push(`entry ${i} (run ${e.run}): prev=${e.prev} references no earlier seal — dangling/fabricated link (history rewritten or reordered)`);
    }
    // AUTHENTICITY: a signed entry must verify; an unsigned one is honest-but-unattested.
    if (e.sig) {
      signed++;
      if (!publicPem) problems.push(`entry ${i} (run ${e.run}): signed but no public key supplied to verify it`);
      else if (!verifySealSig(e.manifest_hash, e.sig, publicPem))
        problems.push(`entry ${i} (run ${e.run}): INVALID signature — not produced by the release key (forged or tampered)`);
    } else {
      unsigned++;
    }
    earlier.add(e.manifest_hash);
  }
  return { ok: problems.length === 0, entries: entries.length, signed, unsigned, problems };
}

/** Parse a _chain.jsonl file into entries (skips blank lines). */
export function readChain(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
}

function main() {
  const argv = process.argv.slice(2);
  const arg = (f) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : null; };
  const HERE = dirname(fileURLToPath(import.meta.url));
  const chainPath = arg('--chain') || join(HERE, '..', '.keel', '_chain.jsonl');
  const pubFile = arg('--pubkey') || process.env.KEEL_RELEASE_PUBKEY || null;
  let entries, pub = null;
  try { entries = readChain(chainPath); }
  catch (e) { console.error(`verify-seal: cannot read chain ${chainPath}: ${e.message}`); process.exit(2); }
  if (pubFile) { try { pub = readFileSync(pubFile, 'utf8'); } catch (e) { console.error(`verify-seal: cannot read pubkey ${pubFile}: ${e.message}`); process.exit(2); } }

  const r = verifyChain(entries, pub);
  console.log(`verify-seal: ${r.entries} seal(s) — ${r.signed} signed, ${r.unsigned} self-asserted${pub ? '' : ' (no public key supplied — signatures not checked)'}`);
  if (!r.ok) {
    for (const p of r.problems) console.error(`  ✗ ${p}`);
    console.error('TRANSPARENCY VERIFICATION FAILED — the seal chain is not trustworthy.');
    process.exit(1);
  }
  console.log('✓ chain intact (append-only links verified)' + (r.signed && pub ? ' and every signed seal authenticated.' : '.'));
  process.exit(0);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
