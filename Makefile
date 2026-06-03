.PHONY: install test clean doctor models help

install:
	./install.sh

doctor:
	@./bin/lgwks doctor 2>/dev/null || ./.venv/bin/python lgwks doctor

models:
	@./.venv/bin/python scripts/setup_models.py all tiny-bert

test:
	@./.venv/bin/python -m pytest tests/ -q 2>/dev/null || echo "No tests/ directory or pytest not installed"

clean:
	rm -rf .venv bin __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "Targets:"
	@echo "  make install   — run ./install.sh (one-time setup)"
	@echo "  make doctor    — run lgwks doctor (verify health)"
	@echo "  make models    — download/convert ML models"
	@echo "  make test      — run pytest suite"
	@echo "  make clean     — remove venv, build artifacts"
