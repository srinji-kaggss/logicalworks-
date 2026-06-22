// adapters/registry.mjs — ingest a host CI registry as a Keel tailoring profile.
//
// Keel is the generic authority; a deployment tailors it by FILLING SCHEMA (docs/03).
// logic-os-kernel already ships an ontology of verifiers — `lwks.verify.registry/v0`
// (scripts/ci/registry.json): each verifier runs a real Tier-1 tool and cites a DO-178C
// clause. That registry IS a profile dialect. Rather than generate a second artifact that
// can drift (the staleness Keel exists to kill), this adapter consumes the registry LIVE
// and maps it onto Keel's atom/concept algebra:
//
//   verifier            → an evidence BINDING that instantiates an atom (never asserts it)
//   verifier.atom       → which of the 20 Excellent-Code atoms this evidence speaks to
//   verifier.run        → the tool the atom is instantiated by (exit==0 ⇒ true, else false)
//   absent tool / no atom → 'unknown' (skip, NEVER pass — the honesty upgrade over H0)
//
// The registry stays the host's single source of truth; Keel is the engine that composes
// its verdict. No network. The adapter is PURE (no fs/process): the front-end supplies the
// pre-fingerprinted unit and docker presence.

/**
 * Translate one registry verifier's `run` (or docker-gated `run_no_docker`) spec into a
 * Keel evidence descriptor consumable by atoms.mjs (tool + argv + needs + cwd).
 */
export function verifierEvidence(v, dockerPresent) {
  let spec = v.run, dockerGated = false;
  if (v.run_no_docker && !dockerPresent) { spec = v.run_no_docker; dockerGated = true; }
  // A verifier may declare a crossing matrix (docs/07 §7.2): the same obligation held across
  // N declared points (configs/feature-flags/platforms). Carried straight to atoms.mjs, which
  // crosses every point and holds the atom true only if all hold (Kleene ∧). Absent → 1 point.
  const cross = Array.isArray(v.cross) && v.cross.length ? v.cross : undefined;
  // scope (#647): the file globs this verifier's evidence depends on — narrows the bound atom's
  // staleness fingerprint to those files (atoms.unitFingerprint). Absent ⇒ whole-unit (coarse).
  const scope = Array.isArray(v.scope) && v.scope.length ? v.scope : undefined;
  const base = { needs: v.needs || [], cwd: v.cwd, dockerGated: dockerGated || undefined, cross, scope };
  return spec.type === 'shell'
    ? { tool: 'bash', argv: ['-c', spec.cmd], ...base }
    : { tool: spec.cmd[0], argv: spec.cmd.slice(1), ...base };
}

/**
 * Build Keel activations from a registry document against a single pre-fingerprinted unit
 * (the workspace). Each verifier becomes one (atom, unit, binding) activation; distinct
 * verifiers mapping to the same atom remain distinct nodes (their command differs, so the
 * anchor's bind-version differs) and aggregate via three-valued ∧ in the engine.
 *
 * Returns:
 *   activations — for engine.composeReport
 *   unmapped    — verifier ids carrying no (valid) `atom` annotation: the mapping DEBT. These
 *                 contribute no evidence; reported so coverage is never silently overstated.
 *
 * opts: { atomsDoc, unit, dockerPresent }
 */
export function registryActivations(reg, { atomsDoc, unit, dockerPresent = true }) {
  const atomDef = (id) => atomsDoc.atoms.find(a => a.id === id);
  const activations = [];
  const unmapped = [];
  for (const v of reg.verifiers || []) {
    const advisory = (v.severity || 'block') === 'advisory';
    // ADVISORY verifiers (the propose→dispose dup ladder rungs 2–4, the embedding proposer)
    // carry no atom BY DESIGN — they must not inflate hard coverage (docs/05 §5.5). They are
    // still RUN and SURFACED, but excluded from the gate. So an advisory verifier with no atom
    // is NOT mapping debt; it is a proposer signal bound to a synthetic, non-gating def.
    if (advisory) {
      const def = (v.atom && atomDef(v.atom)) || { id: v.id, name: v.id, evidence: 'advisory signal' };
      activations.push({
        atomId: def.id, atomDef: def, advisory: true, role: v.role,
        binding: { atom: def.id, evidence: verifierEvidence(v, dockerPresent) },
        unit, source: v.id,
      });
      continue;
    }
    if (!v.atom) { unmapped.push({ id: v.id, why: 'no atom annotation (CM/standards-axis or mapping debt)' }); continue; }
    const def = atomDef(v.atom);
    if (!def) { unmapped.push({ id: v.id, why: `atom '${v.atom}' absent from ontology` }); continue; }
    activations.push({
      atomId: v.atom,
      atomDef: def,
      binding: { atom: v.atom, evidence: verifierEvidence(v, dockerPresent) },
      unit,
      source: v.id,
    });
  }
  return { activations, unmapped };
}
