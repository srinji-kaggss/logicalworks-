// validate.mjs — the RESTRICTIVE load gate (docs/03 §3.1, issue #648 item 1).
//
// A tailoring profile is mechanically validated BEFORE any verification runs: a
// malformed fill must be refused, not silently half-honoured. This is a purpose-built,
// zero-dep checker for the draft-07 SUBSET that schema/profile.schema.json actually uses
// — the same pattern as the kernel's govlog/repo-map checkers (no ajv, no network, the
// validator itself is auditable in one screen).
//
// Supported keywords: type (object|array|string|number|integer|boolean), enum, required,
// properties, additionalProperties (false | schema), items (schema), minimum, maximum.
// Metadata keywords ($schema/$id/title/description) are ignored. The profile schema uses
// no $ref/allOf/if/then, so those are intentionally unsupported — assertSchemaSupported()
// fails loudly if the schema ever grows a keyword this validator does not interpret, so the
// gate can never silently under-check (no silent caps; docs/02 §2.6).

import { REFERENCE_KEYS } from './safetyrefs.mjs';

const SUPPORTED = new Set([
  '$schema', '$id', 'title', 'description',
  'type', 'enum', 'required', 'properties', 'additionalProperties', 'items',
  'minimum', 'maximum',
]);

const typeOk = (t, v) =>
  t === 'object' ? v != null && typeof v === 'object' && !Array.isArray(v)
  : t === 'array' ? Array.isArray(v)
  : t === 'string' ? typeof v === 'string'
  : t === 'number' ? typeof v === 'number'
  : t === 'integer' ? Number.isInteger(v)
  : t === 'boolean' ? typeof v === 'boolean'
  : true;

/** Guard: refuse to run if the schema uses a keyword this subset-validator can't interpret. */
export function assertSchemaSupported(schema, path = '(schema)') {
  if (!schema || typeof schema !== 'object') return;
  for (const k of Object.keys(schema)) {
    if (!SUPPORTED.has(k)) throw new Error(`validate.mjs: unsupported schema keyword '${k}' at ${path} — extend the validator before relying on it (no silent under-check)`);
  }
  if (schema.properties) for (const [k, s] of Object.entries(schema.properties)) assertSchemaSupported(s, `${path}.properties.${k}`);
  if (schema.items) assertSchemaSupported(schema.items, `${path}.items`);
  if (schema.additionalProperties && typeof schema.additionalProperties === 'object') assertSchemaSupported(schema.additionalProperties, `${path}.additionalProperties`);
}

/** Structural validation of `data` against the (subset) `schema`. Returns an error string[]. */
export function validate(data, schema, path = '') {
  const errs = [];
  const at = path || '(root)';
  if (schema.type && !typeOk(schema.type, data)) { errs.push(`${at}: expected ${schema.type}`); return errs; }
  if (schema.enum && !schema.enum.some((e) => e === data)) errs.push(`${at}: ${JSON.stringify(data)} not one of [${schema.enum.join(', ')}]`);
  if (typeof data === 'number') {
    if (schema.minimum !== undefined && data < schema.minimum) errs.push(`${at}: ${data} < minimum ${schema.minimum}`);
    if (schema.maximum !== undefined && data > schema.maximum) errs.push(`${at}: ${data} > maximum ${schema.maximum}`);
  }
  if (typeOk('object', data)) {
    for (const r of schema.required || []) if (!(r in data)) errs.push(`${at}: missing required '${r}'`);
    const props = schema.properties || {};
    for (const k of Object.keys(data)) {
      const sub = `${path}${path ? '.' : ''}${k}`;
      if (props[k]) errs.push(...validate(data[k], props[k], sub));
      else if (schema.additionalProperties === false) errs.push(`${sub}: unexpected property (additionalProperties is false)`);
      else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') errs.push(...validate(data[k], schema.additionalProperties, sub));
    }
  }
  if (Array.isArray(data) && schema.items) data.forEach((v, i) => errs.push(...validate(v, schema.items, `${path}[${i}]`)));
  return errs;
}

/**
 * Full profile gate: structural (schema) + REFERENTIAL constraints the JSON-Schema cannot
 * express (docs/03 §3.4) —
 *   · every binding/threshold atom id exists in schema/atoms.json,
 *   · the gate_concept exists in schema/concepts.json,
 *   · a threshold may only key a GRADED atom (a boolean atom has no score to cross).
 * Returns an error string[]; empty == the profile may run.
 */
export function validateProfile(profile, { schema, atomsDoc, conceptsDoc }) {
  assertSchemaSupported(schema);
  const errs = validate(profile, schema);
  const atomIds = new Set((atomsDoc?.atoms || []).map((a) => a.id));
  const gradedIds = new Set((atomsDoc?.atoms || []).filter((a) => a.kind === 'graded').map((a) => a.id));
  const conceptIds = new Set((conceptsDoc?.concepts || []).map((c) => c.id));
  for (const [i, b] of (profile.bindings || []).entries()) {
    if (b?.atom && !atomIds.has(b.atom)) errs.push(`bindings[${i}].atom '${b.atom}' is not a known atom (schema/atoms.json)`);
    // a score extractor is meaningful only for a graded atom (a boolean atom has no score)
    if (b?.evidence?.score && b?.atom && atomIds.has(b.atom) && !gradedIds.has(b.atom))
      errs.push(`bindings[${i}].evidence.score is only valid for a GRADED atom; '${b.atom}' is boolean (docs/02 §2.5)`);
  }
  if (profile.gate_concept && !conceptIds.has(profile.gate_concept))
    errs.push(`gate_concept '${profile.gate_concept}' is not a known concept (schema/concepts.json)`);
  if (profile.assurance_claim && !conceptIds.has(profile.assurance_claim))
    errs.push(`assurance_claim '${profile.assurance_claim}' is not a known concept (schema/concepts.json)`);
  // A6 provenance: a reference oracle's truth must TRACE to a source, not be invented inline.
  // A gating reference must load from a file (`from`, content-hashed) OR cite a `source_ref` for its
  // inline data. An untraceable inline table is intuition in a data costume — refused.
  for (const [i, s] of (profile.simulate || []).entries()) {
    if (s?.atom && !atomIds.has(s.atom)) errs.push(`simulate[${i}].atom '${s.atom}' is not a known atom`);
    const ref = s?.reference;
    if (ref && !ref.from && !ref.source_ref)
      errs.push(`simulate[${i}].reference is inline with no source_ref — untraceable (A6: model truth is data, not intuition). Add source_ref or load from a file.`);
  }
  for (const [i, s] of (profile.sim || []).entries())
    if (s?.atom && !atomIds.has(s.atom)) errs.push(`sim[${i}].atom '${s.atom}' is not a known atom`);
  // A5 latency: the budget is the auditor's parameter and must be CITED (no uncited threshold as law).
  for (const [i, s] of (profile.latency || []).entries()) {
    if (s?.atom && !atomIds.has(s.atom)) errs.push(`latency[${i}].atom '${s.atom}' is not a known atom`);
    if (s?.budget && !s.budget.source_ref)
      errs.push(`latency[${i}].budget has no source_ref — an uncited latency budget is not law (docs/10 §10.3). Cite where the budget came from.`);
  }
  for (const [atom] of Object.entries(profile.thresholds || {})) {
    if (!atomIds.has(atom)) errs.push(`thresholds['${atom}'] is not a known atom`);
    else if (!gradedIds.has(atom)) errs.push(`thresholds['${atom}'] keys a BOOLEAN atom — only graded atoms cross a threshold (docs/02 §2.5)`);
  }
  // Open Risk #3: confinement allowlist. When execution_policy.allow is declared, EVERY tool Keel
  // will spawn from this profile must be on it — a command outside the allowlist is refused at load
  // (a runner fault, never run), so a poisoned/typo'd binding cannot execute an unintended binary.
  const allow = profile.execution_policy?.allow;
  if (Array.isArray(allow) && allow.length) {
    const allowed = new Set(allow);
    const spawned = new Set([...evidenceTools(profile), ...(profile.safety_case?.tool_qualification || []).map((t) => t.tool).filter(Boolean)]);
    for (const t of spawned)
      if (!allowed.has(t)) errs.push(`execution_policy.allow does not permit evidence tool '${t}' — every spawned binary must be on the allowlist (confinement; docs/15 §15.4 R#3)`);
  }
  errs.push(...validateSafetyCase(profile));
  return errs;
}

function validateSafetyCase(profile) {
  const sc = profile.safety_case;
  if (!sc) return [];
  const errs = [];
  const standards = new Set(sc.standards || []);
  const intent = sc.certification_intent || 'none';
  const highIntent = intent === 'internal-assurance' || intent === 'certification-support';
  const requiredRefs = [
    'safety_plan_ref',
    'hazard_analysis_ref',
    'requirements_traceability_ref',
    'verification_plan_ref',
    'configuration_index_ref',
  ];

  if (standards.has('DO-331') && !standards.has('DO-178C'))
    errs.push(`safety_case.standards includes DO-331 without DO-178C — DO-331 is a supplement to DO-178C/DO-278A, not a standalone claim`);
	  if ((standards.has('DO-178B') || standards.has('DO-178C') || standards.has('DO-331')) && !sc.aviation_level)
	    errs.push(`safety_case.aviation_level is required when a DO-178 standard or supplement is selected`);
	  if (standards.has('ISO-26262') && !sc.automotive_asil)
	    errs.push(`safety_case.automotive_asil is required when ISO-26262 is selected`);
	  if (standards.has('IEC-61508') && !sc.iec_sil)
	    errs.push(`safety_case.iec_sil is required when IEC-61508 is selected`);

  if (highIntent) {
    for (const k of requiredRefs) if (!sc[k]) errs.push(`safety_case.${k} is required for ${intent}`);
    if (!sc.independence?.evidence_ref)
      errs.push(`safety_case.independence.evidence_ref is required for ${intent} — verification independence must be traceable`);
    if (!sc.structural_coverage?.source_ref)
      errs.push(`safety_case.structural_coverage.source_ref is required for ${intent} — coverage claims must trace to a report`);
    if (!Array.isArray(sc.tool_qualification) || sc.tool_qualification.length === 0)
      errs.push(`safety_case.tool_qualification must list evidence-producing tools for ${intent}`);
  }

	  const cov = sc.structural_coverage || {};
	  if ((cov.scope || []).includes('learned_model') && (cov.statement || cov.decision || cov.mcdc))
	    errs.push(`safety_case.structural_coverage.scope includes learned_model, but statement/decision/MC/DC are source-code control-flow criteria; neural/model coverage cannot be counted as MC/DC`);
	  const level = sc.aviation_level;
  if (level === 'A' && !(cov.statement && cov.decision && cov.mcdc))
    errs.push(`safety_case.structural_coverage for DO-178 Level A must declare statement, decision, and MC/DC coverage`);
  if (level === 'B' && !(cov.statement && cov.decision))
    errs.push(`safety_case.structural_coverage for DO-178 Level B must declare statement and decision coverage`);
  if (level === 'C' && !cov.statement)
    errs.push(`safety_case.structural_coverage for DO-178 Level C must declare statement coverage`);

  const asil = sc.automotive_asil;
  if (asil === 'D' && !(cov.statement && cov.decision && cov.mcdc))
    errs.push(`safety_case.structural_coverage for ISO-26262 ASIL D must declare statement, decision, and MC/DC coverage under Keel's stricter floor`);
  if (asil === 'C' && !(cov.statement && cov.decision))
    errs.push(`safety_case.structural_coverage for ISO-26262 ASIL C must declare statement and decision coverage under Keel's stricter floor`);
	  if ((asil === 'A' || asil === 'B') && !cov.statement)
	    errs.push(`safety_case.structural_coverage for ISO-26262 ASIL ${asil} must declare statement coverage under Keel's stricter floor`);
	  const sil = sc.iec_sil;
	  if ((sil === 'SIL3' || sil === 'SIL4') && !(cov.statement && cov.decision && cov.mcdc))
	    errs.push(`safety_case.structural_coverage for IEC 61508 ${sil} must declare statement, decision, and MC/DC under Keel's stricter floor`);
	  if ((sil === 'SIL1' || sil === 'SIL2') && !cov.statement)
	    errs.push(`safety_case.structural_coverage for IEC 61508 ${sil} must declare statement coverage under Keel's stricter floor`);

  if (standards.has('DO-331')) {
    for (const k of ['model_ref', 'model_verification_ref', 'model_code_trace_ref', 'simulation_correlation_ref']) {
      if (!sc.model_based?.[k]) errs.push(`safety_case.model_based.${k} is required when DO-331 is selected`);
    }
  }

  const qualifiedTools = new Set((sc.tool_qualification || []).map((t) => t.tool));
  for (const t of evidenceTools(profile)) {
    if (!qualifiedTools.has(t))
      errs.push(`safety_case.tool_qualification is missing evidence tool '${t}'`);
  }
	  for (const [i, tq] of (sc.tool_qualification || []).entries()) {
    if (tq.standard === 'DO-330' && !tq.tql)
      errs.push(`safety_case.tool_qualification[${i}] uses DO-330 but has no tql`);
    if (tq.standard === 'ISO-26262-8' && !tq.tcl)
      errs.push(`safety_case.tool_qualification[${i}] uses ISO-26262-8 but has no tcl`);
    if (tq.standard === 'unqualified' && highIntent)
      errs.push(`safety_case.tool_qualification[${i}] lists '${tq.tool}' as unqualified under ${intent}; high-criticality evidence tools must be qualified, self-qualified, or independently justified`);
    // Open Risk #2: a self-qualified claim is a DECLARATION unless it carries an executable
    // fixture Keel can run to prove the tool catches defects. Under high intent, require one.
    if (tq.standard === 'self-qualified' && highIntent && !(tq.fixture?.detects && tq.fixture?.accepts))
      errs.push(`safety_case.tool_qualification[${i}] '${tq.tool}' is self-qualified under ${intent} but has no executable fixture (fixture.detects + fixture.accepts); self-qualification must be demonstrated, not declared`);
	  }

  // Open Risk #1: reference_integrity must name real reference fields, and a declared signature
  // must have a trust anchor to verify against (an unverifiable signature is not trust). The
  // existence/hash/signature checks themselves run against the tree at runtime (safetyrefs.mjs).
  for (const [key, spec] of Object.entries(sc.reference_integrity || {})) {
    if (!REFERENCE_KEYS.includes(key))
      errs.push(`safety_case.reference_integrity['${key}'] is not a known reference field (${REFERENCE_KEYS.join(', ')}) — a typo'd key would be silently unverified`);
    if (spec?.signature_file && !sc.trust_anchor?.public_key_file)
      errs.push(`safety_case.reference_integrity['${key}'] declares a signature_file but safety_case.trust_anchor.public_key_file is absent — a signature with no anchor cannot be verified`);
  }
	  errs.push(...validateLearningEnabled(sc, { standards, highIntent }));

	  return errs;
	}

function validateLearningEnabled(sc, { standards, highIntent }) {
  const le = sc.learning_enabled;
  if (!le) return [];
  const errs = [];
  const present = le.present === true || (Array.isArray(le.components) && le.components.length > 0);
  if (!present) return [];

  if (!Array.isArray(le.components) || le.components.length === 0)
    errs.push(`safety_case.learning_enabled.components must list each learned component when learning_enabled.present is true`);

  const required = [
    'certification_position',
    'ml_lifecycle_ref',
    'data_requirements_ref',
    'data_collection_ref',
    'data_preprocessing_ref',
    'training_process_ref',
    'validation_dataset_ref',
    'test_oracle_ref',
    'operational_design_domain_ref',
    'ood_detection_ref',
    'uncertainty_calibration_ref',
    'robustness_ref',
    'post_deployment_monitoring_ref',
    'assumptions_ref',
  ];
  if (highIntent) for (const k of required) if (!le[k]) errs.push(`safety_case.learning_enabled.${k} is required for learning-enabled ${sc.certification_intent}`);

  const safetyRoles = new Set((le.components || []).map((c) => c.safety_role));
  if (safetyRoles.has('guarded') || safetyRoles.has('direct-control')) {
    if (!le.runtime_monitor_ref)
      errs.push(`safety_case.learning_enabled.runtime_monitor_ref is required when learned logic is guarded or direct-control`);
    if (!le.fallback_safe_state_ref)
      errs.push(`safety_case.learning_enabled.fallback_safe_state_ref is required when learned logic is guarded or direct-control`);
  }

  const aviationHigh = ['A', 'B', 'C'].includes(sc.aviation_level);
  if ((standards.has('DO-178B') || standards.has('DO-178C')) && aviationHigh && le.certification_position !== 'accepted-means-of-compliance')
    errs.push(`learning-enabled DO-178 Level ${sc.aviation_level} cannot rely on Keel's ordinary structural-coverage floor; DAL C+ requires learning_enabled.certification_position='accepted-means-of-compliance' plus accepted_means_of_compliance_ref`);
  if (le.certification_position === 'accepted-means-of-compliance' && !le.accepted_means_of_compliance_ref)
    errs.push(`safety_case.learning_enabled.accepted_means_of_compliance_ref is required when certification_position is accepted-means-of-compliance`);
  if (sc.certification_intent === 'certification-support' && le.certification_position !== 'accepted-means-of-compliance')
    errs.push(`learning-enabled certification-support requires accepted means of compliance; use internal-assurance or lower until an authority-accepted basis exists`);
  if (le.neural_coverage_ref && !(le.assumptions_ref && le.test_oracle_ref))
    errs.push(`safety_case.learning_enabled.neural_coverage_ref requires assumptions_ref and test_oracle_ref; neural coverage is not a substitute for MC/DC or oracle quality`);

  return errs;
}

function evidenceTools(profile) {
  const tools = new Set();
  const add = (ev) => { if (ev?.tool) tools.add(ev.tool); };
  for (const b of profile.bindings || []) add(b?.evidence);
  for (const s of profile.soak || []) add(s?.evidence);
  for (const s of profile.simulate || []) add(s?.harness);
  for (const s of profile.latency || []) add(s?.harness);
  for (const s of profile.sim || []) add(s?.harness);
  return [...tools].sort();
}
