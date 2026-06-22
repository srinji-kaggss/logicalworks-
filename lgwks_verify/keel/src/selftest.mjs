#!/usr/bin/env node
// selftest.mjs — deterministic qualification of the concept algebra (docs/05 §5.3,
// in miniature). It is BOTH a test (exit 0/1) and the evidence that instantiates
// `testability_falsifiability` for Keel's self-hosting profile: a falsifiable claim,
// mechanically checked. A precursor to the full ORG.selftest against known-bad
// fixtures (issue ledger).

import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { evalFormula, evalConcept, atomsOf } from './concepts.mjs';
import { Anchor, H, stableStringify } from './anchor.mjs';
import { atomNode, unitFingerprint, policyEnv } from './atoms.mjs';
import { mapPool, singleFlight } from './concurrency.mjs';
import { validate, validateProfile } from './validate.mjs';
import { crossGraded, claimCoherence } from './engine.mjs';
import { qualifyTools } from './toolqual.mjs';
import { verifySafetyRefs } from './safetyrefs.mjs';
import { signSeal, verifySealSig } from './sign.mjs';
import { verifyChain } from './verify-seal.mjs';
import { acceptEnvelope, validateCapacityProfile } from './soak.mjs';
import { enumerateEnvelope, crossOracle, referenceFor, compareToReference, enumerateInterleavings, verifyReferenceSignature } from './simulate.mjs';
import { generateKeyPairSync, sign as cryptoSign, createHash as shaHash } from 'node:crypto';
import { aggregateLatency, acceptLatency } from './latency.mjs';
import { checkConformance } from './conformance.mjs';
import { leanProofNode, proofFingerprint } from './adapters/lean.mjs';

let fails = 0;
const eq = (got, want, msg) => {
  const g = stableStringify(got), w = stableStringify(want);
  if (g !== w) { console.error(`FAIL ${msg}: got ${g}, want ${w}`); fails++; }
};
const ne = (a, b, msg) => {
  if (stableStringify(a) === stableStringify(b)) { console.error(`FAIL ${msg}: expected DIFFERENT, both ${stableStringify(a)}`); fails++; }
};

// Kleene three-valued truth tables (docs/02 §2.6)
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'true' }), 'true', 'all true');
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'false' }), 'false', 'all: false dominates');
eq(evalFormula({ all: ['a', 'b'] }, { a: 'true', b: 'unknown' }), 'unknown', 'all: unknown when no false');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'true' }), 'true', 'any: true dominates');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'unknown' }), 'unknown', 'any: unknown when no true');
eq(evalFormula({ any: ['a', 'b'] }, { a: 'false', b: 'false' }), 'false', 'any all false');
eq(evalFormula({ not: 'a' }, { a: 'true' }), 'false', 'not true');
eq(evalFormula({ not: 'a' }, { a: 'unknown' }), 'unknown', 'not unknown');

// unknown ≠ pass: a gated concept over a missing atom is unknown, never true
eq(evalFormula({ all: ['a'] }, {}), 'unknown', 'missing atom => unknown (never silently true)');

// Hallucinated = ¬CoreGroundedCorrect, computed not judged
const halluc = { id: 'Hallucinated', formula: { not: { all: ['referential_truth', 'type_soundness', 'totality_or_controlled_partiality', 'specification_fidelity'] } } };
eq(evalConcept(halluc, { referential_truth: 'false', type_soundness: 'true', totality_or_controlled_partiality: 'true', specification_fidelity: 'true' }).verdict,
   'true', 'unresolved symbol => Hallucinated=true');

// atomsOf collects references
eq([...atomsOf({ all: ['x', { not: 'y' }] })].sort(), ['x', 'y'], 'atomsOf');

// hashing is deterministic and order-insensitive for object keys
eq(H({ a: 1, b: 2 }) === H({ b: 2, a: 1 }), true, 'stable hash (key order)');

// ── node-id injectivity (C1/C2/C3 regression guard): materially-different evidence MUST get
// different node ids, or a broken/advisory verdict can be reused for a passing one. ──
const A = new Anchor(join(tmpdir(), 'keel-selftest-' + process.pid));
const nid = (binding, meta) => { const n = atomNode({ id: 'referential_truth' }, binding, { id: 'u', root: '.', fingerprint: 'fp' }, meta); return A.nodeId(n.kind, n.params, n.inputs); };
const bind = (ev) => ({ atom: 'referential_truth', evidence: ev });
const base = bind({ tool: 'bash', argv: ['-c', 'true'] });
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c true'] })), 'argv element boundaries change the id (C1)');
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c', 'true'], cwd: 'x' })), 'cwd changes the id (C2)');
ne(nid(base), nid(bind({ tool: 'bash', argv: ['-c', 'true'], env: { K: '1' } })), 'env changes the id (C2)');
ne(nid(base, { source: 'V1' }), nid(base, { source: 'V2' }), 'distinct verifier sources are distinct nodes (C3)');
ne(nid(base, { source: 'V', advisory: true }), nid(base, { source: 'V', advisory: false }), 'advisory channel is namespaced from gated (C3)');
eq(nid(base, { source: 'V' }) === nid(base, { source: 'V' }), true, 'identical evidence+source ⇒ identical id (reuse still works)');

// ── profile load gate (#648 item 1): the RESTRICTIVE validator must reject malformed fills ──
const SCHEMA_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'schema');
const J = (f) => JSON.parse(readFileSync(join(SCHEMA_DIR, f), 'utf8'));
const pSchema = J('profile.schema.json'), pAtoms = J('atoms.json'), pConcepts = J('concepts.json');
const ctx = { schema: pSchema, atomsDoc: pAtoms, conceptsDoc: pConcepts };
// the validator must accept a known-good fill: the live self-hosting profile (if present) must pass
const goodProfile = {
  target: { name: 't', root: '.', ecosystem: 'rust' },
  units: [{ unit: 'crate', discover: { type: 'literal', values: ['.'] } }],
  bindings: [{ atom: 'referential_truth', evidence: { tool: 'bash', argv: ['-c', 'true'], ok_when: 'exit==0' } }],
  gate_concept: 'sound',
  thresholds: { boundary_completeness: 0.8 },
};
eq(validateProfile(goodProfile, ctx), [], 'valid profile passes the load gate');
// structural rejections
const hasErr = (p, needle, msg) => eq(validateProfile(p, ctx).some((e) => e.includes(needle)), true, msg);
hasErr({ ...goodProfile, surprise: 1 }, 'unexpected property', 'extra top-level key rejected (additionalProperties:false)');
hasErr({ units: goodProfile.units, bindings: [], gate_concept: 'sound' }, "missing required 'target'", 'missing required field rejected');
hasErr({ ...goodProfile, target: { name: 't', ecosystem: 'cobol' } }, 'not one of', 'bad enum value rejected');
hasErr({ ...goodProfile, thresholds: { boundary_completeness: 1.5 } }, 'maximum', 'out-of-range threshold rejected');
// referential rejections (the JSON-Schema cannot express these)
hasErr({ ...goodProfile, bindings: [{ atom: 'no_such_atom', evidence: { tool: 'x', argv: [], ok_when: 'exit==0' } }] }, 'not a known atom', 'binding to a nonexistent atom rejected');
hasErr({ ...goodProfile, gate_concept: 'no_such_concept' }, 'not a known concept', 'unknown gate_concept rejected');
hasErr({ ...goodProfile, thresholds: { referential_truth: 0.5 } }, 'BOOLEAN atom', 'threshold on a boolean atom rejected');
// generic validator: enum + range basics
eq(validate('a', { enum: ['a', 'b'] }), [], 'generic validate: enum member passes');
eq(validate(3, { type: 'number', maximum: 2 }).length, 1, 'generic validate: maximum violated');

// ── graded-atom threshold crossing (#648 item 8, docs/02 §2.5) ──
eq(crossGraded(0.92, 0.8), 'true', 'graded: score >= threshold => true');
eq(crossGraded(0.8, 0.8), 'true', 'graded: score == threshold => true (inclusive)');
eq(crossGraded(0.6, 0.8), 'false', 'graded: score < threshold => false');
eq(crossGraded(0.92, undefined), 'unknown', 'graded: no threshold => unknown (auditor must set the bar; blocks, never passes)');
eq(crossGraded(null, 0.8), 'unknown', 'graded: no score => unknown (no measurement)');
eq(crossGraded(NaN, 0.8), 'unknown', 'graded: NaN score => unknown');

// ── soak: envelope-relative acceptance (#643, docs/04 §4.4) ──
const env2 = { target: { calls_per_sec: 2000, inferences_per_sec: 50 }, margin: 1.5 };
// both dimensions hold with margin (3000 >= 2000×1.5; 80 >= 50×1.5=75) => GO
eq(acceptEnvelope({ calls_per_sec: { v_no: 3000 }, inferences_per_sec: { v_no: 80 } }, env2).verdict, 'true', 'soak: V_NO ≥ target×margin on all dims => GO');
// inferences short (70 < 75) => NO-GO, limiting = inferences
const shortfall = acceptEnvelope({ calls_per_sec: { v_no: 3000 }, inferences_per_sec: { v_no: 70 } }, env2);
eq(shortfall.verdict, 'false', 'soak: one dim below target×margin => NO-GO');
eq(shortfall.limiting, 'inferences_per_sec', 'soak: limiting dimension = smallest margin (the spar that gives first)');
// a dimension with no measurement => unknown (BLOCKS, never pass)
eq(acceptEnvelope({ calls_per_sec: { v_no: 3000 }, inferences_per_sec: null }, env2).verdict, 'unknown', 'soak: unmeasured dim => unknown (unknown ≠ pass)');
// no target dimensions => unknown (nothing to accept against)
eq(acceptEnvelope({}, { target: {} }).verdict, 'unknown', 'soak: empty envelope => unknown');
// capacity-profile/v0 validation
eq(validateCapacityProfile({ schema: 'capacity-profile/v0', dimension: 'd', v_no: 48, v_ne: 71 }), [], 'capacity-profile: well-formed passes');
eq(validateCapacityProfile({ schema: 'wrong', dimension: 'd', v_no: 48 }).length >= 1, true, 'capacity-profile: wrong schema rejected');
eq(validateCapacityProfile({ schema: 'capacity-profile/v0', dimension: 'd', v_no: 50, v_ne: 40 }).length >= 1, true, 'capacity-profile: v_ne < v_no rejected');

// ── claim-coherence: the punishing gate — claim must equal evidence (docs/09) ──
const claimF = { all: ['referential_truth', 'testability_falsifiability'] };
eq(claimCoherence(claimF, { referential_truth: 'true', testability_falsifiability: 'true' }).coherent, true, 'claim: all claimed atoms demonstrated (formula holds) => coherent');
// Open Risk #4: a claimed atom measured FALSE breaks the claim's formula. "Measured" is NOT
// "demonstrated" — the claim is REFUTED, not coherent. (The old selftest asserted the bug: it
// called a false-atom claim "coherent" because evidence existed, which let a refuted claim be
// reported as demonstrated whenever the claim was broader than the enforced gate.)
const refuted = claimCoherence(claimF, { referential_truth: 'true', testability_falsifiability: 'false' });
eq(refuted.coherent, false, 'claim: a claimed atom measured FALSE => NOT coherent (claim refuted, not demonstrated)');
eq(refuted.refuted, true, 'claim: false claimed atom => refuted=true (evidence disproves the claim)');
eq(refuted.refutingAtoms, ['testability_falsifiability'], 'claim: names the refuting atom');
const overreach = claimCoherence(claimF, { referential_truth: 'true' }); // testability unknown/unrun
eq(overreach.coherent, false, 'claim: an unrun claimed atom => INCOHERENT (overclaim blocks)');
eq(overreach.refuted, false, 'claim: an UNKNOWN claimed atom is undemonstrated, NOT refuted (distinct honest failure)');
eq(overreach.undemonstrated, ['testability_falsifiability'], 'claim: names the undemonstrated atom');

// ── input-envelope enumeration + oracle crossing (the simulator; docs/09) ──
const env3 = enumerateEnvelope([{ name: 'n', values: [1, 2] }, { name: 'flag', values: [true] }]);
eq(env3.vectors.length, 2, 'enumerate: Cartesian product size (2×1)');
eq(env3.vectors[0].values, { flag: true, n: 1 }, 'enumerate: deterministic vector (sensors sorted by name)');
// numeric range adds boundaries + off-nominal probes (lo,hi,lo-step,hi+step)
const rng = enumerateEnvelope([{ name: 'x', range: [0, 10] }]);
eq(rng.vectors.length, 4, 'enumerate: range yields lo,hi + 2 off-nominal probes');
eq(rng.vectors.some(v => v.off), true, 'enumerate: off-nominal probes flagged');
// cap is honest, never silent
eq(typeof enumerateEnvelope([{ name: 'a', values: [1, 2, 3] }, { name: 'b', values: [1, 2] }], { cap: 4 }).error, 'string', 'enumerate: exceeding the cap BLOCKS (no silent sampling)');
// oracle crossing: one violated vector dominates and is reported as the breaking point
eq(crossOracle([{ label: 'a', value: 'true', off: false }, { label: 'b', value: 'true', off: false }]).value, 'true', 'oracle: all hold => true');
const broke = crossOracle([{ label: 'nominal', value: 'true', off: false }, { label: 'x=11', value: 'false', off: true, reason: 'panic' }]);
eq(broke.value, 'false', 'oracle: one violated vector => false');
eq(broke.breaking.label, 'x=11', 'oracle: reports the breaking input vector');
eq(crossOracle([{ label: 'a', value: 'true', off: false }, { label: 'b', value: 'unknown', off: false }]).value, 'unknown', 'oracle: unmeasured vector => unknown (never silent pass)');

// ── A6: reference-data oracle (truth traces to data, not intuition; docs/10) ──
const ref = { tolerance: 0.5, data: [{ when: { x: 1 }, expect: 10 }, { when: { x: 2 }, expect: 20 }] };
eq(referenceFor(ref, { x: 2 }).expect, 20, 'reference: matches the vector to its datum');
eq(referenceFor(ref, { x: 9 }), null, 'reference: no datum for an unlisted vector (=> unknown, blocks)');
eq(compareToReference(10.3, 10, 0.5), 'true', 'reference: within tolerance => true');
eq(compareToReference(11, 10, 0.5), 'false', 'reference: beyond tolerance => false (regression caught by data)');
eq(compareToReference('ok', 'ok'), 'true', 'reference: non-numeric strict-equal => true');
eq(compareToReference('bad', 'ok'), 'false', 'reference: non-numeric mismatch => false');
// A6 provenance: an inline reference with no source_ref is untraceable => refused at validation
const simProf = { ...goodProfile, simulate: [{ name: 's', atom: 'specification_fidelity', sensors: [{ name: 'x', values: [1] }], harness: { tool: 'bash', argv: ['-c', 'echo 1'] }, reference: { data: [{ when: { x: 1 }, expect: 1 }] } }] };
eq(validateProfile(simProf, ctx).some(e => e.includes('untraceable')), true, 'A6: inline reference without source_ref is refused (truth must trace to a source)');
const simOk = { ...simProf, simulate: [{ ...simProf.simulate[0], reference: { source_ref: 'golden f(x)=x', data: [{ when: { x: 1 }, expect: 1 }] } }] };
eq(validateProfile(simOk, ctx).some(e => e.includes('untraceable')), false, 'A6: inline reference WITH source_ref is accepted');

// ── A5: latency aggregation + budget acceptance (docs/10) ──
const agg = aggregateLatency([12, 10, 11, 14, 10]);
eq([agg.max, agg.min, agg.jitter, agg.p99], [14, 10, 4, 14], 'latency: max/min/jitter/p99 aggregation');
eq(acceptLatency(agg, { max_ms: 20, jitter_ms: 5 }).value, 'true', 'latency: within budget => true');
eq(acceptLatency(agg, { max_ms: 13 }).value, 'false', 'latency: max over budget => false');
eq(acceptLatency(agg, { jitter_ms: 3 }).value, 'false', 'latency: jitter over budget => false');
eq(acceptLatency({ n: 0 }, { max_ms: 20 }).value, 'unknown', 'latency: no samples => unknown (blocks)');
eq(acceptLatency(agg, {}).value, 'unknown', 'latency: no budget bound => unknown (cannot gate on uncited threshold)');
// validator: a latency budget must cite a source_ref
const latNoCite = { ...goodProfile, latency: [{ name: 'l', atom: 'algorithmic_efficiency', harness: { tool: 'bash', argv: ['-c', 'echo 1'] }, budget: { max_ms: 20 } }] };
eq(validateProfile(latNoCite, ctx).some(e => e.includes('uncited latency budget')), true, 'A5: latency budget without source_ref is refused');

// ── safety_case gate: standards-inspired CI cannot overclaim DAL/ASIL rigor without process evidence ──
const highCriticalBase = {
  ...goodProfile,
  safety_case: {
    standards: ['DO-178C', 'DO-331', 'ISO-26262'],
    certification_intent: 'internal-assurance',
    aviation_level: 'A',
    automotive_asil: 'D',
    safety_plan_ref: 'docs/safety/plan.md',
    hazard_analysis_ref: 'docs/safety/hazards.md',
    requirements_traceability_ref: 'docs/safety/trace.csv',
    verification_plan_ref: 'docs/safety/verification.md',
    configuration_index_ref: 'docs/safety/config-index.json',
    independence: { verifier: 'safety-reviewer', reviewer: 'qa', evidence_ref: 'docs/safety/independence.md' },
    structural_coverage: { statement: true, decision: true, mcdc: true, source_ref: 'reports/coverage/mcdc.json' },
    tool_qualification: [
      { tool: 'bash', role: 'shell', standard: 'self-qualified', qualification_ref: 'fixtures/known-bad',
        fixture: { detects: { argv: ['-c', 'exit 1'] }, accepts: { argv: ['-c', 'exit 0'] } } },
    ],
    model_based: {
      model_ref: 'models/control.slx',
      model_verification_ref: 'reports/model-check.json',
      model_code_trace_ref: 'reports/model-code-trace.csv',
      simulation_correlation_ref: 'reports/model-sim-correlation.json',
    },
  },
};
eq(validateProfile(highCriticalBase, ctx), [], 'safety_case: complete high-criticality fill passes');
const noHazard = JSON.parse(JSON.stringify(highCriticalBase));
delete noHazard.safety_case.hazard_analysis_ref;
eq(validateProfile(noHazard, ctx).some(e => e.includes('hazard_analysis_ref')), true, 'safety_case: high intent requires hazard analysis source');
const noMcdc = JSON.parse(JSON.stringify(highCriticalBase));
noMcdc.safety_case.structural_coverage.mcdc = false;
eq(validateProfile(noMcdc, ctx).some(e => e.includes('Level A')), true, 'safety_case: DO-178 Level A requires MC/DC under Keel floor');
const noDo178c = JSON.parse(JSON.stringify(highCriticalBase));
noDo178c.safety_case.standards = ['DO-331'];
eq(validateProfile(noDo178c, ctx).some(e => e.includes('DO-331 without DO-178C')), true, 'safety_case: DO-331 cannot stand alone');
	const missingTool = JSON.parse(JSON.stringify(highCriticalBase));
	missingTool.safety_case.tool_qualification = [];
	eq(validateProfile(missingTool, ctx).some(e => e.includes("evidence tool 'bash'")), true, 'safety_case: every evidence-producing tool must be qualified/listed');
	// Open Risk #2: self-qualified under high intent must carry an EXECUTABLE fixture, not a declaration.
	const selfQualNoFixture = JSON.parse(JSON.stringify(highCriticalBase));
	delete selfQualNoFixture.safety_case.tool_qualification[0].fixture;
	eq(validateProfile(selfQualNoFixture, ctx).some(e => e.includes('no executable fixture')), true, 'R#2: self-qualified under high intent without a fixture is refused (declaration ≠ qualification)');
	// qualifyTools executor: the fixture must actually prove the tool catches a planted defect.
	const goodFix = { tool_qualification: [{ tool: 'bash', fixture: { detects: { argv: ['-c', 'exit 1'] }, accepts: { argv: ['-c', 'exit 0'] } } }] };
	eq(qualifyTools(goodFix)[0].ok, true, 'R#2: a tool that flags the planted defect and passes clean input => qualified');
	const blindFix = { tool_qualification: [{ tool: 'bash', fixture: { detects: { argv: ['-c', 'exit 0'] }, accepts: { argv: ['-c', 'exit 0'] } } }] };
	eq(qualifyTools(blindFix)[0].ok, false, 'R#2: a tool that does NOT flag the planted defect => NOT qualified (missed the defect)');
	const trigger = { tool_qualification: [{ tool: 'bash', fixture: { detects: { argv: ['-c', 'exit 1'] }, accepts: { argv: ['-c', 'exit 1'] } } }] };
	eq(qualifyTools(trigger)[0].ok, false, 'R#2: a tool that rejects the clean input => NOT qualified (flags everything)');
	eq(qualifyTools({ tool_qualification: [{ tool: 'bash', standard: 'self-qualified' }] })[0].skipped, true, 'R#2: no fixture => skipped (never a silent pass)');

	// ── Open Risk #1: safety-case reference verification (existence / hash / signature) ──
	const refDir = mkdtempSync(join(tmpdir(), 'keel-refs-'));
	const refBody = 'safety plan body';
	writeFileSync(join(refDir, 'plan.md'), refBody, 'utf8');
	const refHash = shaHash('sha256').update(Buffer.from(refBody)).digest('hex');
	eq(verifySafetyRefs({ safety_plan_ref: 'nope.md' }, { root: refDir, highIntent: true })[0].ok, false, 'R#1: missing required ref under high intent => NO-GO');
	eq(verifySafetyRefs({ safety_plan_ref: 'plan.md', reference_integrity: { safety_plan_ref: { hash: refHash } } }, { root: refDir })[0].ok, true, 'R#1: matching content hash => verified');
	eq(verifySafetyRefs({ safety_plan_ref: 'plan.md', reference_integrity: { safety_plan_ref: { hash: 'deadbeef' } } }, { root: refDir })[0].ok, false, 'R#1: content hash mismatch => NO-GO (reference altered)');
	const kp = generateKeyPairSync('ed25519');
	writeFileSync(join(refDir, 'plan.pub'), kp.publicKey.export({ type: 'spki', format: 'pem' }), 'utf8');
	writeFileSync(join(refDir, 'plan.sig'), cryptoSign(null, Buffer.from(refBody), kp.privateKey));
	const signedSC = { safety_plan_ref: 'plan.md', trust_anchor: { public_key_file: 'plan.pub' }, reference_integrity: { safety_plan_ref: { signature_file: 'plan.sig' } } };
	eq(verifySafetyRefs(signedSC, { root: refDir })[0].ok, true, 'R#1: valid ed25519 signature against the trust anchor => attested');
	eq(verifySafetyRefs({ ...signedSC, trust_anchor: undefined }, { root: refDir })[0].ok, false, 'R#1: signature with no trust_anchor => NO-GO (unverifiable)');
	writeFileSync(join(refDir, 'plan.md'), refBody + ' TAMPERED', 'utf8');
	eq(verifySafetyRefs(signedSC, { root: refDir })[0].ok, false, 'R#1: tampered file fails signature verification => NO-GO');

	// ── Open Risk #3: confinement — tool allowlist + hermetic env ──
	hasErr({ ...goodProfile, execution_policy: { allow: ['cargo'] } }, "does not permit evidence tool 'bash'", 'R#3: a tool not on execution_policy.allow is refused at load');
	eq(validateProfile({ ...goodProfile, execution_policy: { allow: ['bash'] } }, ctx), [], 'R#3: an allow-listed tool passes the load gate');
	// hermetic env: only passthrough vars survive; a host secret is scrubbed.
	process.env.KEEL_TEST_SECRET = 'do-not-leak';
	process.env.KEEL_TEST_OK = 'fine';
	const scrubbed = policyEnv({ env_passthrough: ['KEEL_TEST_OK'] });
	eq(scrubbed.KEEL_TEST_SECRET, undefined, 'R#3: a non-passthrough host var is ABSENT from the evidence env (no secret leak)');
	eq(scrubbed.KEEL_TEST_OK, 'fine', 'R#3: an explicitly passed-through var IS present');
	eq(typeof scrubbed.PATH, 'string', 'R#3: PATH base is always provided so tools resolve');
	eq(Object.keys(policyEnv(null)).length > Object.keys(scrubbed).length, true, 'R#3: with no policy the full (larger) env is used (back-compatible)');
	delete process.env.KEEL_TEST_SECRET; delete process.env.KEEL_TEST_OK;

	// ── Open Risk #5: signed seals + append-only transparency chain ──
	const kp5 = generateKeyPairSync('ed25519');
	const privPem = kp5.privateKey.export({ type: 'pkcs8', format: 'pem' });
	const pubPem5 = kp5.publicKey.export({ type: 'spki', format: 'pem' });
	const sig5 = signSeal('h1', privPem);
	eq(verifySealSig('h1', sig5, pubPem5), true, 'R#5: a seal signature verifies against the release public key');
	eq(verifySealSig('tampered', sig5, pubPem5), false, 'R#5: signature does not verify over a different manifest hash (tamper-evident)');
	eq(verifySealSig('h1', sig5, generateKeyPairSync('ed25519').publicKey.export({ type: 'spki', format: 'pem' })), false, 'R#5: signature does not verify against the wrong key (forgery-evident)');
	const chain5 = [
		{ run: 'r1', manifest_hash: 'h1', prev: null, sig: signSeal('h1', privPem) },
		{ run: 'r2', manifest_hash: 'h2', prev: 'h1', sig: signSeal('h2', privPem) },
	];
	eq(verifyChain(chain5, pubPem5).ok, true, 'R#5: an intact, signed chain verifies');
	eq(verifyChain([chain5[0], { ...chain5[1], prev: 'WRONG' }], pubPem5).ok, false, 'R#5: a broken prev-link (rewritten/reordered history) fails');
	eq(verifyChain([chain5[0], { ...chain5[1], sig: 'deadbeef' }], pubPem5).ok, false, 'R#5: a forged/invalid signature fails');
	const unsignedChain = [{ run: 'r1', manifest_hash: 'h1', prev: null }];
	eq(verifyChain(unsignedChain, pubPem5).ok, true, 'R#5: an unsigned chain is intact (self-asserted), not a failure');
	eq(verifyChain(unsignedChain, pubPem5).unsigned, 1, 'R#5: unsigned seals are counted, never silently passed as signed');
	// Anchor actually emits a verifiable signature when given a release key.
	const sealAnchor = new Anchor(mkdtempSync(join(tmpdir(), 'keel-seal-')), { signingKeyPem: privPem });
	const sealed = sealAnchor.seal('runX', { gate: 'g', verdict: 'true' });
	eq(verifySealSig(sealed.manifest_hash, sealed.sig, pubPem5), true, 'R#5: Anchor.seal with a key produces a signature that verifies');
	const iecMissingSil = JSON.parse(JSON.stringify(highCriticalBase));
	iecMissingSil.safety_case.standards = ['IEC-61508'];
	delete iecMissingSil.safety_case.aviation_level;
	delete iecMissingSil.safety_case.automotive_asil;
	eq(validateProfile(iecMissingSil, ctx).some(e => e.includes('iec_sil')), true, 'safety_case: IEC 61508 requires SIL');
	const learnedCoverageLie = JSON.parse(JSON.stringify(highCriticalBase));
	learnedCoverageLie.safety_case.structural_coverage.scope = ['learned_model'];
	eq(validateProfile(learnedCoverageLie, ctx).some(e => e.includes('neural/model coverage cannot be counted as MC/DC')), true, 'learning-enabled: learned_model scope cannot satisfy source MC/DC');
	const mlDalCNoBasis = JSON.parse(JSON.stringify(highCriticalBase));
	mlDalCNoBasis.safety_case.aviation_level = 'C';
	mlDalCNoBasis.safety_case.learning_enabled = {
	  present: true,
	  certification_position: 'safety-case-with-assumptions',
	  components: [{ id: 'vision-net', model_type: 'neural-network', safety_role: 'guarded' }],
	  ml_lifecycle_ref: 'docs/ml/lifecycle.md',
	  data_requirements_ref: 'docs/ml/data-reqs.md',
	  data_collection_ref: 'docs/ml/data-collection.md',
	  data_preprocessing_ref: 'docs/ml/preprocess.md',
	  training_process_ref: 'docs/ml/training.md',
	  validation_dataset_ref: 'docs/ml/validation-data.md',
	  test_oracle_ref: 'docs/ml/oracle.md',
	  operational_design_domain_ref: 'docs/ml/odd.md',
	  ood_detection_ref: 'docs/ml/ood.md',
	  uncertainty_calibration_ref: 'docs/ml/calibration.md',
	  robustness_ref: 'docs/ml/robustness.md',
	  runtime_monitor_ref: 'docs/ml/monitor.md',
	  fallback_safe_state_ref: 'docs/ml/fallback.md',
	  post_deployment_monitoring_ref: 'docs/ml/post-deploy.md',
	  assumptions_ref: 'docs/ml/assumptions.md',
	};
	eq(validateProfile(mlDalCNoBasis, ctx).some(e => e.includes('DAL C+ requires')), true, 'learning-enabled: DO-178 DAL C+ requires accepted means of compliance');
	const mlAccepted = JSON.parse(JSON.stringify(mlDalCNoBasis));
	mlAccepted.safety_case.learning_enabled.certification_position = 'accepted-means-of-compliance';
	mlAccepted.safety_case.learning_enabled.accepted_means_of_compliance_ref = 'docs/ml/authority-issue-paper.md';
	eq(validateProfile(mlAccepted, ctx).some(e => e.includes('DAL C+ requires')), false, 'learning-enabled: DAL C+ can proceed only with accepted means of compliance cited');
	const mlNoMonitor = JSON.parse(JSON.stringify(mlAccepted));
	delete mlNoMonitor.safety_case.learning_enabled.runtime_monitor_ref;
	eq(validateProfile(mlNoMonitor, ctx).some(e => e.includes('runtime_monitor_ref')), true, 'learning-enabled: guarded/direct-control ML requires a runtime monitor');

// ── #644: multi-actor interleaving enumeration (docs/04 §4.5) ──
const il = enumerateInterleavings([{ id: 'A', steps: ['init'] }, { id: 'B', steps: ['use'] }]);
eq(il.schedules.length, 2, 'interleavings: 2 actors × 1 step => 2 schedules (multinomial)');
eq(il.schedules.map(s => s.label).sort(), ['A:init>B:use', 'B:use>A:init'], 'interleavings: both order-preserving merges enumerated');
const il2 = enumerateInterleavings([{ id: 'A', steps: ['a1', 'a2'] }, { id: 'B', steps: ['b1'] }]);
eq(il2.schedules.length, 3, 'interleavings: (2,1) => 3 = 3!/(2!1!)');
eq(il2.schedules.every(s => s.steps.findIndex(x => x.op === 'a1') < s.steps.findIndex(x => x.op === 'a2')), true, 'interleavings: each actor internal order preserved');
eq(typeof enumerateInterleavings([{ id: 'A', steps: ['1', '2', '3', '4'] }, { id: 'B', steps: ['1', '2', '3', '4'] }], { cap: 10 }).error, 'string', 'interleavings: exceeding cap BLOCKS (no silent sampling)');

// ── A6 authenticity: ed25519 reference signature verification (external trust root) ──
{
  const { publicKey, privateKey } = generateKeyPairSync('ed25519');
  const pub = publicKey.export({ type: 'spki', format: 'pem' });
  const content = Buffer.from('{"data":[{"when":{"x":1},"expect":2}]}');
  const goodSig = cryptoSign(null, content, privateKey);
  eq(verifyReferenceSignature(content, goodSig, pub), true, 'A6: valid signature verifies against the trust anchor');
  eq(verifyReferenceSignature(Buffer.from('tampered'), goodSig, pub), false, 'A6: tampered content fails verification (no false authentication)');
  const { publicKey: otherPub } = generateKeyPairSync('ed25519');
  eq(verifyReferenceSignature(content, goodSig, otherPub.export({ type: 'spki', format: 'pem' })), false, 'A6: a different key fails verification (signature is bound to the real key)');
}

// ── concept↔Lean conformance (#645 item 7, docs/02 §2.4): the three framework concepts in
//    concepts.json MUST equal lean/ExcellentCode/Framework.lean (structural — Lean not run here) ──
const leanText = readFileSync(join(SCHEMA_DIR, '..', 'lean', 'ExcellentCode', 'Framework.lean'), 'utf8');
const conf = checkConformance({ conceptsDoc: pConcepts, leanText, atomsDoc: pAtoms });
eq(conf.ok, true, 'conformance: concepts.json matches Framework.lean (no drift): ' + conf.discrepancies.join('; '));
eq(conf.checked.sort(), ['CoreGroundedCorrect', 'Excellent', 'Hallucinated'], 'conformance: all three framework concepts checked');
// negative meta-test (auditor-of-the-auditor): a drifted JSON formula MUST be caught
const drift = JSON.parse(JSON.stringify(pConcepts));
const cg = drift.concepts.find((c) => c.id === 'CoreGroundedCorrect');
cg.formula.all = cg.formula.all.filter((a) => a !== 'specification_fidelity');
eq(checkConformance({ conceptsDoc: drift, leanText, atomsDoc: pAtoms }).ok, false, 'conformance: a dropped atom in a framework formula is caught (not a blind pass)');
// a phantom atom (not in atoms.json) is caught
const phantom = JSON.parse(JSON.stringify(pConcepts));
phantom.concepts.find((c) => c.id === 'Excellent').formula.all[0] = 'no_such_atom';
eq(checkConformance({ conceptsDoc: phantom, leanText, atomsDoc: pAtoms }).ok, false, 'conformance: a phantom atom in a framework formula is caught');

// ── Lean proof-term node (item 6 / #646, docs/05 §5.2): the `tool: lean` seam grafts a proof
//    onto the anchor DAG, content-addressed by the proof SOURCE. These assert the IDENTITY law
//    (no toolchain needed; deterministic) — the lake build itself is gated in qualify.mjs. ──
const leanPkg = (frameworkSrc, toolchain = 'leanprover/lean4:v4.31.0') => {
  const dir = mkdtempSync(join(tmpdir(), 'keel-leanpkg-'));
  mkdirSync(join(dir, 'ExcellentCode'), { recursive: true });
  writeFileSync(join(dir, 'ExcellentCode', 'Framework.lean'), frameworkSrc);
  writeFileSync(join(dir, 'lean-toolchain'), toolchain + '\n');
  return dir;
};
const leanNid = (dir, theorems = ['excellent_not_hallucinated']) => {
  const n = leanProofNode({ packageDir: dir, modules: ['ExcellentCode/Framework.lean'], theorems });
  return A.nodeId(n.kind, n.params, n.inputs);
};
const pkgA = leanPkg('theorem t : True := trivial\n');
const pkgA2 = leanPkg('theorem t : True := trivial\n');           // identical content, different dir
const pkgB = leanPkg('theorem t : True := by trivial\n');         // a DIFFERENT proof term
eq(leanNid(pkgA) === leanNid(pkgA2), true, 'lean proof node: identical proof source ⇒ identical id (cache reuse works)');
ne(leanNid(pkgA), leanNid(pkgB), 'lean proof node: a changed proof term changes the id (staleness spine)');
ne(leanNid(pkgA), leanNid(leanPkg('theorem t : True := trivial\n', 'leanprover/lean4:v4.30.0')), 'lean proof node: a changed toolchain pin changes the id');
ne(leanNid(pkgA), leanNid(pkgA, ['some_other_theorem']), 'lean proof node: a changed grafted-theorem set changes the id');
// a missing proof source hashes to '∅' deterministically (never a silent skip)
eq(proofFingerprint(mkdtempSync(join(tmpdir(), 'keel-leanempty-')), ['ExcellentCode/Framework.lean']).sources[0].hash, '∅', 'lean proof node: a missing source is ∅, not silently absent');

// ── binding scope → symbol-granular staleness (item 2 / #647, docs/01 §1.3): a binding's `scope`
//    narrows the fingerprint to the declared globs, so an edit OUTSIDE the scope must NOT change the
//    node id (no recompute), while an edit INSIDE it must. Verdict-invariant; deterministic. ──
const scopeDir = mkdtempSync(join(tmpdir(), 'keel-scope-'));
writeFileSync(join(scopeDir, 'a.rs'), 'fn a() {}\n');
writeFileSync(join(scopeDir, 'b.rs'), 'fn b() {}\n');
const unit = { id: 'u', root: scopeDir };
const fpScopedA = unitFingerprint(unit, ['a.rs']);          // depends on a.rs only
const fpAll = unitFingerprint(unit, ['**/*.rs']);           // depends on both
writeFileSync(join(scopeDir, 'b.rs'), 'fn b() { /* edited */ }\n');   // edit OUTSIDE scope ['a.rs']
eq(unitFingerprint(unit, ['a.rs']), fpScopedA, 'scope: an edit outside the scope does NOT change the fingerprint (no recompute)');
ne(unitFingerprint(unit, ['**/*.rs']), fpAll, 'scope: the wider whole-unit fingerprint DOES see the same edit (granularity is real, not a no-op)');
writeFileSync(join(scopeDir, 'a.rs'), 'fn a() { /* edited */ }\n');   // edit INSIDE scope ['a.rs']
ne(unitFingerprint(unit, ['a.rs']), fpScopedA, 'scope: an edit inside the scope DOES change the fingerprint (recompute fires)');

// the scope wires through to the NODE ID (the seam: atomNode inputs). Same proof at function level,
// now proven at identity level so the engine actually reuses/recomputes per scope.
const scopeNid = (scope) => { const n = atomNode({ id: 'type_soundness' }, { atom: 'type_soundness', evidence: { tool: 'true', argv: [], scope } }, unit); return A.nodeId(n.kind, n.params, n.inputs); };
writeFileSync(join(scopeDir, 'a.rs'), 'fn a() {}\n');        // reset a.rs
const nidScoped1 = scopeNid(['a.rs']);
writeFileSync(join(scopeDir, 'b.rs'), 'fn b() { /* edited again */ }\n');   // outside scope
eq(scopeNid(['a.rs']), nidScoped1, 'scope: atomNode id is stable across an out-of-scope edit (the seam wires through to identity)');
writeFileSync(join(scopeDir, 'a.rs'), 'fn a() { changed }\n');             // inside scope
ne(scopeNid(['a.rs']), nidScoped1, 'scope: atomNode id changes on an in-scope edit');

// ── concurrency primitives (docs/07 §7.4): the seam that licenses crossing in parallel ──
async function concurrencyTests() {
  // mapPool resolves in INPUT order regardless of finish order (deterministic aggregation)
  const out = await mapPool([3, 1, 2], 3, async (n) => { await tick(n); return n * 10; });
  eq(out, [30, 10, 20], 'mapPool preserves input order under out-of-order completion');

  // a thrown worker is isolated as __poolError, never aborts the crossing (engine maps → unknown)
  const mixed = await mapPool([1, 2], 2, async (n) => { if (n === 1) throw new Error('boom'); return n; });
  eq(mixed[0] && mixed[0].__poolError instanceof Error, true, 'mapPool isolates a thrown crossing point');
  eq(mixed[1], 2, 'mapPool: a sibling fault does not poison other points');

  // bound is respected: at most `limit` in flight at once
  let live = 0, peak = 0;
  await mapPool([0, 0, 0, 0, 0], 2, async () => { live++; peak = Math.max(peak, live); await tick(1); live--; });
  eq(peak <= 2, true, 'mapPool never exceeds the concurrency bound');

  // singleFlight collapses identical concurrent keys to one computation
  let calls = 0;
  const once = singleFlight();
  const compute = async () => { calls++; await tick(1); return 'v'; };
  const [a, b] = await Promise.all([once('k', compute), once('k', compute)]);
  eq([a, b, calls], ['v', 'v', 1], 'singleFlight computes a concurrent key exactly once');
}
const tick = (n) => new Promise((r) => setImmediate(() => (n > 1 ? tick(n - 1).then(r) : r())));

concurrencyTests().then(() => {
  if (fails) { console.error(`selftest: ${fails} failed`); process.exit(1); }
  console.log('selftest: ok (algebra + hashing + concurrency qualified)');
}).catch((e) => { console.error('selftest harness fault:', e); process.exit(2); });
