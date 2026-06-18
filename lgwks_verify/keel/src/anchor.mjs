// anchor.mjs — the content-addressed verdict graph (the ANCHOR).
//
// One source of truth: a Merkle DAG of verification nodes. A node's id is the hash
// of its kind, params, and its inputs' hashes; its verdict is a pure function of
// those inputs. This file implements (docs/01-architecture.md):
//   - content hashing (H)                                                 §1.1
//   - the stale-proof cache: a cached verdict is valid iff its node id     §1.3
//     still matches the recomputed id (changed input => new id => miss)
//   - the append-only run manifest (the verification tape)                 §1.5
//
// Determinism: no wall-clock, no randomness. Identity is content. Standalone:
// only Node builtins. The principle is borrowed from content-addressed fact
// stores; the runtime is NOT imported (docs/01 §1.8).

import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, writeFileSync, existsSync, statSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import { singleFlight } from './concurrency.mjs';

/** H — the hash primitive. Stable JSON (sorted keys) so equal content => equal id. */
export function H(...parts) {
  const h = createHash('sha256');
  for (const p of parts) h.update(typeof p === 'string' ? p : stableStringify(p));
  return h.digest('hex').slice(0, 40);
}

/** Deterministic JSON matching JSON.stringify semantics: sorted keys, undefined
 *  object-keys omitted, undefined/array-holes => null. Round-trips through JSON.parse. */
export function stableStringify(v) {
  if (v === null) return 'null';
  if (typeof v !== 'object') { const s = JSON.stringify(v); return s === undefined ? 'null' : s; }
  if (Array.isArray(v)) return '[' + v.map(stableStringify).join(',') + ']';
  const keys = Object.keys(v).filter(k => v[k] !== undefined).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + stableStringify(v[k])).join(',') + '}';
}

/** Content hash of a file on disk; '∅' if absent (referential-truth-friendly). */
export function hashFile(path) {
  try { return H(readFileSync(path)); } catch { return '∅'; }
}

/** Content hash of a directory's tracked shape — cheap structural fingerprint. */
export function hashPathMeta(path) {
  try { const s = statSync(path); return H(path, String(s.size), s.isDirectory() ? 'd' : 'f'); }
  catch { return '∅'; }
}

/**
 * The Anchor: a content-addressed store of node verdicts under <dir>.
 * - nodeId(kind, params, inputHashes) computes the deterministic id.
 * - evaluate(node) returns the cached verdict if the id matches (stale-proof),
 *   else computes via node.compute(), stores, and returns it.
 */
export class Anchor {
  constructor(dir) {
    this.dir = dir;
    this.store = join(dir, 'nodes');
    mkdirSync(this.store, { recursive: true });
    this.touched = [];        // node ids visited this run (for the manifest)
    this.recomputed = 0;
    this.reused = 0;
    this._flight = singleFlight();  // collapse identical nodes computed concurrently
  }

  nodeId(kind, params, inputHashes) {
    return H(kind, params || {}, [...inputHashes].sort().join('|'));
  }

  /**
   * node = { kind, params, inputs:[hash...], compute: () => verdict }
   * verdict is any JSON-serializable value; it is stored keyed by the node id.
   * A changed input changes the id => the old verdict is a different file =>
   * structural staleness: we never read a verdict that does not belong to the
   * current inputs.
   */
  evaluate(node) {
    const id = this.nodeId(node.kind, node.params, node.inputs);
    const path = join(this.store, id + '.json');
    if (existsSync(path)) {
      this.reused++;
      this.touched.push(id);
      return { id, ...JSON.parse(readFileSync(path, 'utf8')), cached: true };
    }
    const verdict = node.compute();
    const record = { kind: node.kind, params: node.params, inputs: node.inputs, verdict };
    writeFileSync(path, stableStringify(record) + '\n');
    this.recomputed++;
    this.touched.push(id);
    return { id, ...record, cached: false };
  }

  /**
   * Async sibling of evaluate(): identical content-addressed semantics, but awaits a
   * node whose compute() returns a Promise (the spawn-based evaluator, atoms.mjs). Wrapped
   * in single-flight on the node id so two crossings that resolve to the SAME node compute
   * once — the second awaits the first rather than racing a duplicate subprocess + write.
   * Determinism is unchanged: identity is content, and side-effects run exactly once per id.
   */
  async evaluateAsync(node) {
    const id = this.nodeId(node.kind, node.params, node.inputs);
    const path = join(this.store, id + '.json');
    if (existsSync(path)) {
      this.reused++;
      this.touched.push(id);
      return { id, ...JSON.parse(readFileSync(path, 'utf8')), cached: true };
    }
    return this._flight(id, async () => {
      // re-check inside the flight: a sibling caller may have just written it
      if (existsSync(path)) {
        this.reused++;
        this.touched.push(id);
        return { id, ...JSON.parse(readFileSync(path, 'utf8')), cached: true };
      }
      const verdict = await node.compute();
      const record = { kind: node.kind, params: node.params, inputs: node.inputs, verdict };
      writeFileSync(path, stableStringify(record) + '\n');
      this.recomputed++;
      this.touched.push(id);
      return { id, ...record, cached: false };
    });
  }

  /**
   * Seal the run: write an append-only manifest referencing the touched nodes.
   * runId is content-derived (caller passes the codebase fingerprint), never a clock.
   */
  seal(runId, summary) {
    // tape-binding (docs/01 §1.5): each seal is a hash-chained fact. prev = the manifest
    // hash of the previous seal on this anchor's chain. A verdict you cannot place on the
    // chain is a verdict you cannot trust — the chain is the append-only verification tape.
    const prev = this._chainTip();
    const manifest = {
      schema: 'keel.manifest/v0',
      run: runId,
      nodes: this.touched,
      recomputed: this.recomputed,
      reused: this.reused,
      prev,                       // null for the genesis seal
      ...summary,
    };
    const path = join(this.dir, `manifest-${runId}.json`);
    const body = stableStringify(manifest) + '\n';
    writeFileSync(path, body);
    const manifest_hash = H(body);
    appendFileSync(join(this.dir, '_chain.jsonl'),
      stableStringify({ run: runId, manifest_hash, prev }) + '\n');
    return { path, manifest, manifest_hash, prev };
  }

  /** The manifest hash of the latest seal on this anchor's chain, or null at genesis. */
  _chainTip() {
    const chain = join(this.dir, '_chain.jsonl');
    if (!existsSync(chain)) return null;
    const lines = readFileSync(chain, 'utf8').split('\n').filter(Boolean);
    if (!lines.length) return null;
    try { return JSON.parse(lines[lines.length - 1]).manifest_hash; } catch { return null; }
  }
}
