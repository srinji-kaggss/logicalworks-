// latency.mjs — latency/jitter as a first-order verdict variable (aircraft axiom A5; issue: kernel #657).
//
// A5 (latency_bounded_execution): "transport_delay ≤ qualified_budget; latency and jitter are
// first-order fidelity variables." The honest reconciliation with Keel's determinism: the latency
// MEASUREMENT is an empirical, non-deterministic SENSOR (wall-clock varies); the DECISION RULE
// (aggregate → compare to a cited budget) is deterministic. Determinism lives in the control law,
// not the sensor (cf. the math-vs-embedding-sensor split). The measurement is treated as a property
// of the source version: measured per source fingerprint and reused until the source changes (A8).
//
// A budget is the auditor's CITED parameter — no budget ⇒ 'unknown' (cannot gate; an uncited
// threshold is not law). No samples ⇒ 'unknown' (BLOCKS, never a silent pass).

/** Aggregate latency samples (ms) into the verdict-relevant statistics. jitter = max − min
 *  (the spread the scheduler must keep bounded; A5). p99 by nearest-rank. */
export function aggregateLatency(samples) {
  const s = (samples || []).filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return { n: 0 };
  const max = s[s.length - 1], min = s[0];
  const p99 = s[Math.min(s.length - 1, Math.ceil(0.99 * s.length) - 1)];
  return { n: s.length, min, max, p99, jitter: max - min, mean: s.reduce((a, b) => a + b, 0) / s.length };
}

/** Accept the aggregate against a declared budget. Any breached bound ⇒ 'false' with the reason(s).
 *  No samples or no budget ⇒ 'unknown' (blocks). */
export function acceptLatency(agg, budget) {
  if (!agg || !agg.n) return { value: 'unknown', reasons: ['no latency samples measured (harness unbound or produced no number)'] };
  if (!budget || (budget.max_ms == null && budget.p99_ms == null && budget.jitter_ms == null))
    return { value: 'unknown', reasons: ['no latency budget declared — cannot gate (cite max_ms / p99_ms / jitter_ms; an uncited threshold is not law, docs/10 §10.3)'] };
  const reasons = [];
  if (budget.max_ms != null && agg.max > budget.max_ms) reasons.push(`max ${agg.max}ms > budget ${budget.max_ms}ms`);
  if (budget.p99_ms != null && agg.p99 > budget.p99_ms) reasons.push(`p99 ${agg.p99}ms > budget ${budget.p99_ms}ms`);
  if (budget.jitter_ms != null && agg.jitter > budget.jitter_ms) reasons.push(`jitter ${agg.jitter}ms > budget ${budget.jitter_ms}ms`);
  return { value: reasons.length ? 'false' : 'true', reasons };
}
