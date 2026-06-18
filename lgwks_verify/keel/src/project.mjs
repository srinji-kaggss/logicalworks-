// project.mjs — the three projections of the one anchor (docs/01 §1.5).
//
// AI and humans never share a representation; each reads a projection of the same
// content-addressed truth, derived live, so they cannot drift. Emit by SURPRISE,
// not by volume: a passing atom costs ~nothing; detail is spent on the anomalous.

/** Symbolic projection — the exact record, for audit/proofs/the tape. Loss-less. */
export function symbolic(report) {
  return {
    schema: 'keel.projection.symbolic/v0',
    run: report.run,
    gate_concept: report.gate.concept,
    verdict: report.gate.verdict,
    atoms: report.atoms,        // every (atom,unit) value + evidence pointer
    concepts: report.concepts,  // every concept verdict
    cache: { recomputed: report.recomputed, reused: report.reused },
  };
}

/**
 * AI projection — the decision digest. Conventional structure, meaningful names,
 * surprise-weighted: only non-true atoms are detailed, with a targeted fix. This is
 * what an orchestrating AI reads to act, and the input to a downstream cost model.
 */
export function ai(report, atomDefs) {
  const offenders = report.gate.offenders.map(o => ({
    atom: o.atom,
    value: o.value,
    units: report.atoms.filter(a => a.atom === o.atom && a.value !== 'true').map(a => a.unit),
    fix: fixFor(o.atom, o.value, atomDefs),
  }));
  return {
    schema: 'keel.projection.ai/v0',
    run: report.run,
    verdict: report.gate.verdict,        // true | false | unknown
    gate: report.gate.concept,
    // emit-by-surprise: nothing about the passing atoms
    offenders: report.gate.verdict === 'true' ? [] : offenders,
    note: report.gate.verdict === 'unknown'
      ? 'blocked: a gated atom is unknown (no evidence) — bind a tool or run the tier'
      : undefined,
  };
}

function fixFor(atom, value, atomDefs) {
  const def = (atomDefs || []).find(d => d.id === atom);
  if (value === 'unknown') return `bind/run the evidence source for ${atom} (${def?.evidence || 'tool'}); unknown ≠ pass`;
  return `${atom} is false — ${def?.formal || 'predicate unmet'}; address via ${def?.evidence || 'the bound tool'}`;
}

/** Human projection — DEFERRED. Interface only (docs/01 §1.5); see issue ledger. */
export function human() {
  return { schema: 'keel.projection.human/v0', deferred: true,
    note: 'narrative + headroom/cost rendering not implemented in first pass' };
}

/** Terse one-line render of the AI projection for a terminal. */
export function renderAI(p) {
  const mark = p.verdict === 'true' ? 'GO' : p.verdict === 'unknown' ? 'BLOCKED' : 'NO-GO';
  const lines = [`${mark} — gate '${p.gate}' = ${p.verdict}  (run ${p.run})`];
  for (const o of p.offenders) {
    lines.push(`  ✗ ${o.atom} = ${o.value}${o.units.length ? `  [${o.units.join(', ')}]` : ''}`);
    lines.push(`     fix: ${o.fix}`);
  }
  if (p.note) lines.push(`  note: ${p.note}`);
  return lines.join('\n');
}
