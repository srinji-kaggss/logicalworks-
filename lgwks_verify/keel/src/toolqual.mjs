// toolqual.mjs — executable tool qualification (Open Risk #2, docs/15 §15.4).
//
// `safety_case.tool_qualification` entries were DECLARATIVE: a `standard:"self-qualified"` row
// asserted a tool was trustworthy with nothing run to prove it. An evidence tool that does not
// actually catch defects is a hole under every verdict it produces. This module makes the claim
// EXECUTABLE: a fixture declares a planted-DEFECTIVE input the tool MUST flag (`detects`, the tool
// exits non-zero) and a CLEAN input it MUST pass (`accepts`, exit zero). Keel runs both. A tool
// that misses the planted defect, or flags the clean input, is NOT qualified — same known-bad /
// known-good discipline Keel turns on itself in qualify.mjs, applied to a target's evidence tools.
//
// Determinism/confinement: probes run with a scrubbed, minimal env (no host secrets, HOME, or git
// config) — the seam Open Risk #3 (execution_policy) tightens with an allowlist. A needed binary
// that is absent ⇒ `unknown` (skipped, never a false pass).

import { spawnSync } from 'node:child_process';

const MAXBUF = 8 * 1024 * 1024;

/** Minimal hermetic env for a probe — cannot read host secrets/HOME/git. (R#3 narrows further.) */
function probeEnv(cwd) {
  return {
    PATH: process.env.PATH || '/usr/bin:/bin',
    HOME: cwd, TMPDIR: cwd, LANG: process.env.LANG || 'C',
    GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_SYSTEM: '/dev/null', GIT_TERMINAL_PROMPT: '0',
  };
}

function has(bin) {
  return spawnSync('bash', ['-c', `command -v ${bin}`], { encoding: 'utf8' }).status === 0;
}

/** Run one probe; return its exit status (or null on launch failure / absent need). */
function runProbe(tool, probe, cwd) {
  for (const bin of probe.needs || []) if (!has(bin)) return { status: null, absent: bin };
  const r = spawnSync(tool, probe.argv, { cwd, env: probeEnv(cwd), encoding: 'utf8', maxBuffer: MAXBUF, timeout: 60_000 });
  return { status: r.error ? null : r.status, error: r.error };
}

/**
 * Execute the fixtures of a safety_case's tool_qualification entries.
 * Returns one row per entry: { tool, ok, skipped, why }.
 *   - no fixture            => skipped (validation decides whether one was REQUIRED).
 *   - needed binary absent  => skipped (unknown, never a false pass).
 *   - detects exits zero    => NOT ok (the tool missed a planted defect).
 *   - accepts exits non-zero=> NOT ok (the tool flags clean input — useless gate).
 *   - detects!=0 && accepts==0 => ok (qualified by demonstration).
 */
export function qualifyTools(safetyCase, { cwd = '.' } = {}) {
  const rows = [];
  for (const tq of safetyCase?.tool_qualification || []) {
    if (!tq.fixture) { rows.push({ tool: tq.tool, ok: null, skipped: true, why: 'no executable fixture declared' }); continue; }
    const det = runProbe(tq.tool, tq.fixture.detects, cwd);
    if (det.absent) { rows.push({ tool: tq.tool, ok: null, skipped: true, why: `toolchain absent: ${det.absent}` }); continue; }
    const acc = runProbe(tq.tool, tq.fixture.accepts, cwd);
    if (acc.absent) { rows.push({ tool: tq.tool, ok: null, skipped: true, why: `toolchain absent: ${acc.absent}` }); continue; }
    const detectsCaught = det.status !== 0 && det.status !== null; // must FLAG the planted defect
    const acceptsPassed = acc.status === 0;                        // must PASS the clean input
    const ok = detectsCaught && acceptsPassed;
    rows.push({
      tool: tq.tool, ok, skipped: false,
      why: ok ? 'fixture: flagged the planted defect and passed the clean input'
        : !detectsCaught ? `fixture: '${tq.tool}' did NOT flag the planted defect (detects exit ${det.status}) — it cannot be trusted to catch what it claims`
          : `fixture: '${tq.tool}' rejected the clean input (accepts exit ${acc.status}) — a tool that flags everything proves nothing`,
    });
  }
  return rows;
}
