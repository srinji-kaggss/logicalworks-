.PHONY: test test-python test-rust

test: test-python test-rust

test-python:
	uv run --with pytest python -m pytest axiom/tests/ tests/test_axiom_cli.py tests/test_research_stack.py::TestManifest -q

test-rust:
	cd axiom/rust && cargo test -q
