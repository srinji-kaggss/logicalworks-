#!/bin/bash
# Generate the code review graph for the repository.
# Requires 'uv' to be installed.

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "Building code review graph..."
uvx code-review-graph build --data-dir .code-review-graph

echo "Generating wiki..."
uvx code-review-graph wiki --data-dir .code-review-graph

echo "Generating visualization..."
uvx code-review-graph visualize --data-dir .code-review-graph

echo "Done! The graph is stored in .code-review-graph/"
