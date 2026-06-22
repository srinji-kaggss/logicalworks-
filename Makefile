.PHONY: install test test-python test-rust check-registry clean doctor models help \
        verify verify-commit verify-nightly verify-release verify-maturity

test: check-registry test-python test-rust

# Verification authority (vendored Keel @ lgwks_verify/keel, pinned SHA in VENDORED.txt).
# Local-first: the CI runner IS the gate; relative paths only (no upstream dependency).
verify: verify-commit

verify-commit:
	@node scripts/ci/run.mjs --tier commit

verify-nightly:
	@node scripts/ci/run.mjs --tier nightly

verify-release:
	@node scripts/ci/run.mjs --tier release

# Multi-axis maturity scream (report-only): all 20 Keel axes + concept ladder.
# IEC 61508 discipline — an unmeasured axis earns no credit. Does not block.
verify-maturity:
	@node scripts/ci/maturity.mjs

check-registry:
	python3 scripts/check_schema_registry.py

install:
	./install.sh

doctor:
	@./bin/lgwks doctor 2>/dev/null || ./.venv/bin/python lgwks doctor

models:
	@./.venv/bin/python scripts/setup_models.py all tiny-bert

# IMPORTANT: `make test` is the command the Keel `testability_falsifiability` atom
# runs (lgwks.profile.json), and that atom is evaluated by maturity.mjs, which is
# itself exercised by tests/test_verify.py::TestMaturityScream — which runs inside
# the full pytest suite. So `make test` MUST stay light and MUST NOT run the whole
# `tests/` tree, or it recurses (test → maturity → make test → test …) and the
# heavy ×2 cross blows the maturity test's timeout. This is exactly what broke main
# after #305. The COMPREHENSIVE first-party gate is the lanes in scripts/ci/run.mjs
# (`make verify`): pytest.suite (full tests/), rust.crawler/axiom/tui, schema,
# coverage.completeness. Comprehensiveness lives THERE, not here.
test-python:
	uv run --with pytest python -m pytest axiom/tests/ tests/test_axiom_cli.py tests/test_research_stack.py::TestManifest -q

test-rust:
	cargo test --manifest-path axiom/rust/Cargo.toml -q

clean:
	rm -rf .venv bin __pycache__ .pytest_cache axiom/rust/target
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "Targets:"
	@echo "  make install     run ./install.sh (one-time setup)"
	@echo "  make doctor      run lgwks doctor (verify health)"
	@echo "  make models      download/convert ML models"
	@echo "  make verify          commit-tier Keel gate (alias: verify-commit)"
	@echo "  make verify-commit   local CI floor — sealed verdict in .ci-runs/"
	@echo "  make verify-nightly  envelope+concurrency tier (BLOCKED until runners vendored)"
	@echo "  make verify-release  soak+evidence tier (BLOCKED until runners vendored)"
	@echo "  make test        run Python and Rust tests"
	@echo "  make test-python run Axiom Python tests"
	@echo "  make test-rust   run Axiom Rust tests"
	@echo "  make clean       remove venv and build artifacts"
