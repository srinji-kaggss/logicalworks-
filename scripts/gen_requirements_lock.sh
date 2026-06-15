#!/usr/bin/env bash
# gen_requirements_lock.sh — regenerate the hash-pinned dependency lockfiles.
#
# Supply-chain hardening (#154 H13): the committed *-lock.txt files pin every
# transitive dependency to an exact version + SHA-256 hash set. install.sh then
# installs with `pip install --require-hashes`, so a compromised or typosquatted
# PyPI release cannot be silently pulled in.
#
# Run this whenever requirements.txt / requirements-dev.txt change, then commit
# the regenerated lockfiles alongside the source requirement edits.
#
# Requires: uv (https://docs.astral.sh/uv/). `--python-version 3.10` makes the
# lock universal across the supported range (3.10+), so conditional deps gated
# on `python_version < "3.13"` (leidenalg/igraph) are captured with markers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="${UV:-uv}"

if ! command -v "$UV" >/dev/null 2>&1; then
    echo "error: uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

echo "→ runtime: requirements.txt → requirements-lock.txt"
"$UV" pip compile --generate-hashes --universal --python-version 3.10 \
    "$REPO_ROOT/requirements.txt" -o "$REPO_ROOT/requirements-lock.txt"

echo "→ dev:     requirements-dev.txt → requirements-dev-lock.txt"
"$UV" pip compile --generate-hashes --universal --python-version 3.10 \
    "$REPO_ROOT/requirements-dev.txt" -o "$REPO_ROOT/requirements-dev-lock.txt"

echo "✓ lockfiles regenerated. Review the diff and commit both *-lock.txt files."
