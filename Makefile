.PHONY: install test test-python test-rust check-registry clean doctor models help \
        verify verify-commit verify-nightly verify-release

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

check-registry:
	python3 scripts/check_schema_registry.py

install:
	./install.sh

doctor:
	@./bin/lgwks doctor 2>/dev/null || ./.venv/bin/python lgwks doctor

models:
	@./.venv/bin/python scripts/setup_models.py all tiny-bert

test-python:
	uv run --with pytest python -m pytest axiom/tests/ tests/test_axiom_cli.py tests/test_research_stack.py::TestManifest -q

test-rust:
	cd axiom/rust && cargo test -q

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
