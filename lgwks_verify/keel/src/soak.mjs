// soak.mjs — the endurance tier core (docs/04 §4.3–4.4, §4.6; issue #643).
//
// The break-and-revert loop (escalate→bracket→revert→soak) is a NATIVE HARNESS, not the
// thin orchestrator's job (docs/04 §4.2): the heavy sustained load runs in compiled per-target
// code, which emits a content-addressed `capacity-profile/v0` artifact PER load dimension. Keel's
// job here is the deterministic part: parse that artifact and decide ENVELOPE-RELATIVE acceptance
// (§4.4) — GO iff measured V_NO ≥ target × margin on EVERY dimension; the limiting dimension is the
// argmin margin (tropical reduction, §1.6). Keel never prices anything (§4.6) — it emits/consumes
// the physical characterization; the cost model is a separate downstream projection.
//
// This module is the FINAL seam: the harness that produces a capacity profile is deferred behind
// the soak binding's tool (run-soak.mjs), exactly as a graded atom's score is. A dimension with no
// measurement is `unknown` (BLOCKS, never a silent pass; docs/02 §2.6).

/** Validate one `capacity-profile/v0` artifact emitted by a soak harness. Returns errors[]. */
export function validateCapacityProfile(p) {
  const errs = [];
  if (p == null || typeof p !== 'object') return ['capacity-profile: not an object'];
  if (p.schema !== 'capacity-profile/v0') errs.push(`capacity-profile: schema must be 'capacity-profile/v0' (got ${JSON.stringify(p.schema)})`);
  if (typeof p.dimension !== 'string' || !p.dimension) errs.push('capacity-profile: missing dimension');
  if (typeof p.v_no !== 'number' || !(p.v_no >= 0)) errs.push('capacity-profile: v_no must be a number ≥ 0 (sustained-safe limit)');
  if (p.v_ne !== undefined && (typeof p.v_ne !== 'number' || p.v_ne < p.v_no)) errs.push('capacity-profile: v_ne (never-exceed) must be ≥ v_no');
  if (p.samples !== undefined && !Array.isArray(p.samples)) errs.push('capacity-profile: samples must be an array');
  return errs;
}

/**
 * Envelope-relative acceptance (§4.4). Given per-dimension measured profiles and the declared
 * envelope, decide the soak verdict.
 *   required(dim) = envelope.target[dim] × (envelope.margin ?? 1)
 *   margin_ratio  = v_no / required               (headroom; ≥1 means the dimension holds)
 *   GO iff every targeted dimension has a measurement AND margin_ratio ≥ 1.
 *   A targeted dimension with no measurement ⇒ verdict 'unknown' (blocks; unknown ≠ pass).
 *   limiting = the dimension with the smallest margin_ratio (the spar that gives first).
 *
 * @param profiles  Map<dimension, {v_no:number}|null>  (null = harness ran/absent, no measurement)
 * @param envelope  { target:{[dim]:number}, slo?, margin?:number }
 * returns { verdict:'true'|'false'|'unknown', dimensions:[…], limiting }
 */
export function acceptEnvelope(profiles, envelope) {
  const target = envelope?.target || {};
  const marginFactor = typeof envelope?.margin === 'number' ? envelope.margin : 1;
  const dims = Object.keys(target);
  if (!dims.length) return { verdict: 'unknown', dimensions: [], limiting: null, reason: 'envelope declares no target dimensions — nothing to accept against' };

  const rows = dims.map((dim) => {
    const required = target[dim] * marginFactor;
    const prof = profiles[dim];
    const v_no = prof && typeof prof.v_no === 'number' ? prof.v_no : null;
    if (v_no == null) return { dimension: dim, v_no: null, required, margin: null, value: 'unknown', reason: `no capacity measurement for '${dim}' (soak harness unbound or did not report) — unknown ≠ pass` };
    const ratio = required > 0 ? v_no / required : (v_no > 0 ? Infinity : 0);
    return { dimension: dim, v_no, required, margin: ratio, value: ratio >= 1 ? 'true' : 'false',
      reason: ratio >= 1 ? undefined : `holds ${v_no} but needs ${required} (target ${target[dim]} × margin ${marginFactor}) — ${(ratio).toFixed(2)}× of required` };
  });

  // limiting dimension = smallest margin among MEASURED dims (unknown dims are reported separately)
  const measured = rows.filter((r) => r.margin != null);
  const limiting = measured.length ? measured.reduce((a, b) => (b.margin < a.margin ? b : a)) : null;
  const verdict = rows.some((r) => r.value === 'false') ? 'false'
    : rows.some((r) => r.value === 'unknown') ? 'unknown'
    : 'true';
  return { verdict, dimensions: rows, limiting: limiting ? limiting.dimension : null };
}
