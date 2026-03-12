# =============================================================================
# Makefile — Developer Convenience Targets
# =============================================================================
# Usage:
#   make install      Install all dev dependencies
#   make lint         Run yamllint + ansible-lint
#   make pre-commit   Run full pre-commit suite against all files
#   make clean        Remove Python cache artifacts
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help install lint yamllint ansible-lint pre-commit clean

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "  make install       Install dev dependencies from requirements-dev.txt"
	@echo "  make lint          Run yamllint and ansible-lint"
	@echo "  make yamllint      Run yamllint only"
	@echo "  make ansible-lint  Run ansible-lint only"
	@echo "  make pre-commit    Run full pre-commit suite against all files"
	@echo "  make clean         Remove Python cache artifacts"
	@echo ""

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install:
	pip install -r requirements-dev.txt
	pre-commit install
	pre-commit install --hook-type commit-msg

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint: yamllint ansible-lint

yamllint:
	yamllint --config-file .yamllint.yml .

ansible-lint:
	ansible-lint

# ---------------------------------------------------------------------------
# Pre-Commit
# ---------------------------------------------------------------------------
pre-commit:
	pre-commit run --all-files

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.retry" -delete 2>/dev/null || true
