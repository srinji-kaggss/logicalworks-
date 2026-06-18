.PHONY: install test test-python test-rust check-registry clean doctor models help

test: check-registry test-python test-rust

verify:
	@node /Users/srinji/keel/src/run.mjs --profile keel.profile.json

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
	@echo "  make test        run Python and Rust tests"
	@echo "  make test-python run Axiom Python tests"
	@echo "  make test-rust   run Axiom Rust tests"
	@echo "  make clean       remove venv and build artifacts"
