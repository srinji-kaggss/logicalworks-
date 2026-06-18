// atoms.mjs — instantiate evidence atoms from real Tier-1 tools.
//
// An atom is NEVER asserted true by Keel. It is instantiated by running the tool
// bound to it (docs/02 §2.2, docs/03 §3.4) and reading a three-valued result
// (docs/02 §2.6):
//   true    — tool ran and ok_when held
//   false   — tool ran and ok_when did not hold
//   unknown — no binding, a needed binary is absent, or the tool self-skipped (exit 77)
//
// Evidence gathering is wrapped as content-addressed nodes so re-running on an
// unchanged unit reuses the verdict (anchor.mjs). The tool process is the heavy
// work; the orchestrator only collects its result (docs/04 §4.2).
//
// CROSSING (docs/07 §7.2). A binding's evidence may declare a `cross` matrix: a list of
// points (platform, config, …) that the SAME obligation must hold across. The atom is
// `true` only if every crossed point is `true` (Kleene ∧). One point that goes red, or is
// unknown, dominates — exactly the "cross 100%, find where the bridge fails" model. With no
// matrix the cross is a single point (back-compatible). Heavy enumerations (mutants, fuzz
// inputs) are crossed INSIDE the bound tool, which reports one exit; Keel's matrix is the
// declarable config/platform axis layered on top.

import { spawn, spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { H, hashFile, hashPathMeta } from './anchor.mjs';

const PATH_WITH_CARGO = `${process.env.PATH || ''}:${join(process.env.CARGO_HOME || join(process.env.HOME || '', '.cargo'), 'bin')}`;
const RUN_ENV = { ...process.env, PATH: PATH_WITH_CARGO };

// Exit code a tool uses to self-report "namespace real, evidence harness not wired here"
// (the automake skip convention). Distinct from a needed-binary being absent: the tool RAN
// and declined. Maps to 'unknown' (skip, NEVER pass) with the tool's own reason.
const SKIP_EXIT = 77;
const MAXBUF = 64 * 1024 * 1024;
// Per-point wall-clock bound so a tool that hangs (reads stdin, deadlocks) can never stall the
// gate forever (H1). Generous by default — real suites take minutes; override with ev.timeout_ms.
// A timeout is 'unknown' (we did not learn the answer), never a pass.
const DEFAULT_TIMEOUT_MS = 600_000;

function has(bin) {
  return spawnSync('bash', ['-c', `command -v ${bin}`], { env: RUN_ENV }).status === 0;
}

/** Non-blocking spawn → Promise<{status, stdout, stderr, error, timedOut}>. The async sibling of
 *  spawnSync so the pool (concurrency.mjs) can keep K tools running at once. stdin is closed
 *  (`ignore`) so an interactive tool reads EOF instead of hanging; a hard timeout (H1) kills a
 *  tool that hangs anyway and is reported as a timeout (→ unknown, never pass). */
function spawnAsync(tool, argv, opts) {
  const timeout = opts.timeout || DEFAULT_TIMEOUT_MS;
  return new Promise((resolve) => {
    let stdout = '', stderr = '', launchError = null;
    const child = spawn(tool, argv, { ...opts, stdio: ['ignore', 'pipe', 'pipe'], timeout });
    // bound RETAINED output ~MAXBUF (parent heap); destroy the stream once capped so a chatty
    // child cannot keep us busy forever (M3). The verdict reads only exit status, not full output.
    const cap = (s, add, stream) => { if (s.length >= MAXBUF) { stream?.destroy?.(); return s; } return s + add; };
    child.stdout?.on('data', (d) => { stdout = cap(stdout, d.toString(), child.stdout); });
    child.stderr?.on('data', (d) => { stderr = cap(stderr, d.toString(), child.stderr); });
    child.on('error', (e) => { launchError = e; resolve({ status: null, stdout, stderr, error: e }); });
    // on timeout Node kills the child → close fires with code=null, signal='SIGTERM'.
    child.on('close', (code, signal) => {
      if (launchError) return;
      resolve({ status: code, stdout, stderr, error: null, timedOut: code === null && signal != null });
    });
  });
}

/** Hash a unit's content so a node id changes when the unit changes (staleness spine). */
export function unitFingerprint(unit) {
  if (unit.fingerprint) return unit.fingerprint;
  return unit.manifest ? hashFile(unit.manifest) : hashPathMeta(unit.path || unit.id);
}

/** The crossing matrix for a binding: explicit points, or a single default point. */
function crossPoints(ev) {
  return Array.isArray(ev.cross) && ev.cross.length ? ev.cross : [{ label: 'base' }];
}

/** Three-valued ∧ over crossed-point values: false dominates, then unknown. */
function crossAnd(vs) {
  return vs.includes('false') ? 'false' : vs.includes('unknown') ? 'unknown' : 'true';
}

/**
 * Build the DAG node that instantiates one (atom, unit) pair. The verdict is
 * { value, reason, points:[…] }. compute() is ASYNC (await-able) so the engine pool can
 * run many atom nodes concurrently; the node id folds in the FULL evidence spec (tool, argv
 * structurally, cwd, env, every crossed point) so any change that affects compute() changes
 * the id (staleness spine, docs/01 §1.3).
 *
 * `meta` carries { advisory, source }: the node id is NAMESPACED by them so an advisory /
 * proposer node can never share a content-addressed verdict with a gated atom node, and two
 * distinct verifiers mapping to the same atom stay distinct nodes even if their commands
 * happen to coincide (C1/C3 defence-in-depth).
 */
export function atomNode(atomDef, binding, unit, meta = {}) {
  const ev = binding?.evidence;
  const points = ev ? crossPoints(ev) : [{ label: 'base' }];
  // C3: the channel an advisory verdict lives in is part of its identity — a gated reuse of an
  // advisory node (or vice-versa) is impossible by construction, independent of command text.
  const channel = meta.advisory ? `advisory:${meta.source || ''}` : (meta.source ? `gated:${meta.source}` : 'gated');
  const inputs = [
    unitFingerprint(unit),
    binding ? evidenceFingerprint(ev, points) : 'nobind',
    channel,
  ];
  return {
    kind: `atom:${atomDef.id}`,
    params: { unit: unit.id, atom: atomDef.id, channel },
    inputs,
    async compute() {
      if (!binding) return { value: 'unknown', reason: `no binding for ${atomDef.id} (evidence source unbound)` };
      // H2: ok_when is only meaningful as exit==0; an author who declares anything else is
      // silently misled today. Surface it as unknown (blocks, never passes) rather than ignore.
      if (ev.ok_when && ev.ok_when !== 'exit==0')
        return { value: 'unknown', reason: `unsupported ok_when '${ev.ok_when}' (only exit==0 is interpreted) — reword the evidence` };
      for (const bin of ev.needs || []) {
        if (!has(bin)) return { value: 'unknown', reason: `toolchain absent: ${bin}` };
      }
      // cross every declared point; the atom holds only if all hold (Kleene ∧)
      const results = [];
      for (const pt of points) {
        const argv = pt.argv || ev.argv;
        if (!Array.isArray(argv)) { results.push({ label: pt.label || 'base', value: 'unknown', reason: 'no argv (malformed binding/point — refusing to spawn a bare tool)' }); continue; }
        const cwd = (pt.cwd ?? ev.cwd) ? join(unit.root || '.', pt.cwd ?? ev.cwd) : (unit.root || '.');
        const env = (pt.env || ev.env) ? { ...RUN_ENV, ...ev.env, ...pt.env } : RUN_ENV;
        const r = await spawnAsync(ev.tool, argv, { cwd, env, encoding: 'utf8', timeout: pt.timeout_ms || ev.timeout_ms });
        results.push(readPoint(pt, ev, r));
      }
      const value = crossAnd(results.map(p => p.value));
      const failed = results.filter(p => p.value !== 'true');
      return {
        value,
        points: results,
        reason: value === 'true' ? undefined
          : failed.map(p => `[${p.label}] ${p.reason}`).join(' · '),
        log: value === 'true' ? undefined : failed.map(p => p.log).filter(Boolean).join('\n---\n').slice(-2000),
      };
    },
  };
}

/** Read one crossed point's three-valued result from a finished process. */
function readPoint(pt, ev, r) {
  const label = pt.label || 'base';
  if (r.error) return { label, value: 'unknown', reason: `tool failed to launch: ${r.error.message}` };
  if (r.timedOut) return { label, value: 'unknown', reason: `timed out (${(pt.timeout_ms || ev.timeout_ms || DEFAULT_TIMEOUT_MS) / 1000}s) — treated as unknown, never pass` };
  if (r.status === SKIP_EXIT) {
    const last = (r.stdout || '').trim().split('\n').filter(Boolean).pop() || 'self-reported skip';
    return { label, value: 'unknown', exit: 77, reason: last.replace(/^SKIP:\s*/, '') };
  }
  const ok = r.status === 0; // ok_when is enforced to exit==0 in compute() (H2)
  return {
    label, value: ok ? 'true' : 'false', exit: r.status,
    reason: ok ? undefined : `${ev.tool} ${(pt.argv || ev.argv).join(' ')} exited ${r.status}`,
    log: ok ? undefined : (r.stderr || r.stdout || '').slice(-2000),
  };
}

/**
 * C1/C2: content fingerprint of the FULL evidence spec, hashed STRUCTURALLY (not space-joined).
 * Argv element boundaries, cwd, env, and every crossed point are preserved, so two materially
 * different commands (`["-c","true"]` vs `["-c true"]`, or same command in a different cwd/env)
 * can never collide on a node id and inherit one another's cached verdict.
 */
function evidenceFingerprint(ev, points) {
  return H('evidence/v1', {
    tool: ev.tool,
    argv: ev.argv || [],
    cwd: ev.cwd || '',
    env: ev.env || {},
    ok_when: ev.ok_when || 'exit==0',
    points: points.map(p => ({
      label: p.label || '', argv: p.argv || ev.argv || [],
      cwd: p.cwd ?? ev.cwd ?? '', env: { ...(ev.env || {}), ...(p.env || {}) },
    })),
  });
}
