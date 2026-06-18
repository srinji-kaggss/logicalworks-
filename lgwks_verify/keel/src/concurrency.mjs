// concurrency.mjs — the bounded execution pool (docs/07 §7.4).
//
// Keel's verdict is a pure function of CONTENT (anchor.mjs): a node's id is the hash
// of its inputs, and its verdict is computed once and cached by that id. Nothing about
// the VERDICT depends on the order in which nodes are evaluated. That is exactly the
// property that licenses concurrency: the finite structural-outcome space (docs/07 §7.1)
// can be crossed in any order, in parallel, and the composed verdict is identical.
//
// So this file owns ONE seam — "evaluate N independent nodes with at most K running at
// once" — and nothing else. No randomness, no wall-clock; only ordering of side-effects,
// which the content-addressed store is immune to. Standalone: zero dependencies.

import { cpus } from 'node:os';

/**
 * Default crossing width. Concurrency changes throughput, NEVER the verdict, so the
 * default is a performance choice, not a correctness one. Bounded below by 1 and kept
 * a little under core count so a verification run never starves the host it runs on.
 * Override with --concurrency N or KEEL_CONCURRENCY for reproducible logs/timing.
 */
export function defaultConcurrency() {
  const env = Number(process.env.KEEL_CONCURRENCY);
  if (Number.isInteger(env) && env > 0) return env;
  let n = 4;
  try { n = cpus().length; } catch { /* sandboxed: fall back */ }
  return Math.max(1, n - 2);
}

/**
 * mapPool — run `fn` over `items` with at most `limit` in flight; resolve to results in
 * INPUT ORDER (so the caller's aggregation is deterministic regardless of finish order).
 *
 * A worker that throws does NOT reject the pool: the slot's result is `{ __poolError: e }`
 * so one failed crossing point cannot abort the whole crossing (the engine decides how a
 * fault maps to a verdict — a thrown evaluator is 'unknown', never a silent pass).
 */
export async function mapPool(items, limit, fn) {
  const list = [...items];
  const results = new Array(list.length);
  const width = Math.max(1, Math.min(limit | 0 || 1, list.length || 1));
  let next = 0;
  async function worker() {
    while (true) {
      const i = next++;
      if (i >= list.length) return;
      try { results[i] = await fn(list[i], i); }
      catch (e) { results[i] = { __poolError: e }; }
    }
  }
  await Promise.all(Array.from({ length: width }, () => worker()));
  return results;
}

/**
 * dedupe — guarantee a key is computed at most once even if requested concurrently.
 * Two parallel crossings that resolve to the SAME content-addressed node id must not
 * both run the (possibly expensive, possibly file-writing) compute; the second awaits
 * the first. Returns a function with the same signature as `compute`.
 */
export function singleFlight() {
  const inflight = new Map();
  return async function once(key, compute) {
    if (inflight.has(key)) return inflight.get(key);
    const p = (async () => compute())().finally(() => inflight.delete(key));
    inflight.set(key, p);
    return p;
  };
}
