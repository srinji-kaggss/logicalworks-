#!/usr/bin/env node
// Coverage-completeness guard for the local CI authority (scripts/ci/run.mjs).
//
// The point: "fully comprehensive" must be ENFORCED, not a thing someone remembered
// to do once. This lane fails (NO-GO) the moment a first-party test surface exists
// that no CI lane runs and that isn't EXPLICITLY excluded with a reason. So a new
// `tests2/`, a new `foo/Cargo.toml`, or a test file dropped outside the covered
// roots can never silently ride along as fake-accepted, untested green.
//
// Discovery is over `git ls-files` (tracked files only) — vendored trees like
// .venv-models/ and build output under target/ are untracked/ignored and so are
// excluded for free, with no fragile path blocklist.
//
// Keep COVERED_* in lockstep with the lanes in run.mjs. If you add a lane, widen
// the covered set here; if you intentionally skip a surface, add it to EXCLUDED
// with a stated reason. There is no third option — that is the whole point.

import { execSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

// pytest roots actually executed by the pytest.suite lane (dir prefixes).
const COVERED_PYTEST_ROOTS = ['tests/', 'axiom/tests/'];
// Rust crates actually executed by the rust.* lanes.
const COVERED_CRATES = ['crawler/Cargo.toml', 'axiom/rust/Cargo.toml', 'tui/Cargo.toml', 'lgwks-human/Cargo.toml'];

// Deliberate, stated exclusions. A surface here is NOT run — and that is on the record.
const EXCLUDED = {
  'archive/tests/': 'archived/orphaned modules (archive/README.md); no active callers — revive into a covered root to earn coverage',
  'tests/fixtures/crate/Cargo.toml': 'test fixture crate (input data for test_graph_rust), not first-party code',
};

function tracked(...patterns) {
  const out = execSync(`git ls-files -- ${patterns.map((p) => `'${p}'`).join(' ')}`, {
    cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
  });
  return out.split('\n').map((s) => s.trim()).filter(Boolean);
}

function isExcluded(path) {
  return Object.keys(EXCLUDED).some((ex) => path === ex || path.startsWith(ex));
}

const gaps = [];

// 1. Every tracked Python test file must live under a covered pytest root (or be excluded).
for (const f of tracked('*test_*.py')) {
  if (isExcluded(f)) continue;
  if (!COVERED_PYTEST_ROOTS.some((r) => f.startsWith(r))) {
    gaps.push(`pytest: ${f} — not under a covered root (${COVERED_PYTEST_ROOTS.join(', ')})`);
  }
}

// 2. Every tracked Cargo.toml must be a covered crate (or be excluded).
for (const f of tracked('*Cargo.toml')) {
  if (isExcluded(f)) continue;
  if (!COVERED_CRATES.includes(f)) {
    gaps.push(`rust: ${f} — crate not run by any rust.* lane`);
  }
}

// 3. Every covered surface must still exist (a lane pointing at a deleted path is a
//    silent no-op = fake acceptance from the other direction).
for (const r of COVERED_PYTEST_ROOTS) {
  if (tracked(`${r}*test_*.py`).length === 0) gaps.push(`pytest root '${r}' has no tracked test files — stale lane`);
}
for (const c of COVERED_CRATES) {
  if (tracked(c).length === 0) gaps.push(`rust crate '${c}' missing — stale lane`);
}

if (gaps.length) {
  console.error('coverage-completeness FAILED — uncovered first-party test surface:');
  for (const g of gaps) console.error(`  ✗ ${g}`);
  console.error('\nFix: run it in a lane (widen COVERED_* in run.mjs + this guard), or');
  console.error('add it to EXCLUDED here with a stated reason. Silent omission is not an option.');
  process.exit(1);
}

const pyCount = tracked('*test_*.py').filter((f) => !isExcluded(f)).length;
console.log(`coverage-completeness OK — ${pyCount} pytest files under ${COVERED_PYTEST_ROOTS.join(' + ')}; ` +
  `crates ${COVERED_CRATES.join(', ')}; excluded: ${Object.keys(EXCLUDED).join(', ')}`);
