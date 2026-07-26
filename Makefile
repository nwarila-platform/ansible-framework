# =============================================================================
# Makefile — Developer Convenience Targets
# =============================================================================
# Usage:
#   make install      Install all dev dependencies
#   make lint         Run yamllint + ansible-lint + allowlist guard
#   make pre-commit   Run full pre-commit suite against all files
#   make allowlist-check
#                     Fail if a deliverable file is silently ignored
#   make clean        Remove Python cache artifacts
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help install lint yamllint ansible-lint allowlist-check pre-commit clean

# The deny-all guard scans the whole repository. Only rooted, known local artifacts are excluded:
# Ansible/cache state, the handoff workspace, a root .env, Python caches, and retry files.
GUARD_EXCLUDE := ^(_handoff/|\.ansible/|\.cache/|\.env$$|([^/]+/)*(__pycache__|\.cache)/|([^/]+/)*[^/]+\.(py[co]|retry)$$)

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "  make install       Install dev dependencies from requirements-dev.txt"
	@echo "  make lint          Run yamllint, ansible-lint, and the allowlist guard"
	@echo "  make yamllint      Run yamllint only"
	@echo "  make ansible-lint  Run ansible-lint only"
	@echo "  make allowlist-check"
	@echo "                     Fail if a deliverable file is silently ignored"
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
lint: yamllint ansible-lint allowlist-check

yamllint:
	yamllint --config-file .yamllint.yml .

ansible-lint:
	@files=$$(git ls-files --cached --others --exclude-standard -- applications operating_systems \
	  | grep -E '\.ya?ml$$' | sort); \
	if [ -z "$$files" ]; then \
	  printf 'ERROR: no cached or visible role YAML files found for ansible-lint\n'; \
	  exit 1; \
	fi; \
	ansible-lint $$files

# Bidirectional deny-all allowlist guard. The forward half catches deliverable files that exist
# on disk but are ignored. The reverse half catches stale !/ entries after a rename or deletion.
allowlist-check:
	@ignored=$$(git ls-files --others --ignored --exclude-standard -- . 2>/dev/null \
	  | grep -vE '$(GUARD_EXCLUDE)' || true); \
	if [ -n "$$ignored" ]; then \
	  printf 'ERROR: repository files are NOT allowlisted in .gitignore:\n'; \
	  printf '%s\n' "$$ignored" | sed 's/^/  /'; \
	  printf 'Add an explicit "!/<path>" line to .gitignore, or remove the non-deliverable artifact.\n'; \
	  exit 1; \
	else \
	  printf 'allowlist-check: OK — every repository file is explicitly allowlisted\n'; \
	fi
	@rootless=$$(grep '^!' .gitignore | grep -v '^!/' || true); \
	if [ -n "$$rootless" ]; then \
	  printf 'ERROR: .gitignore allowlist entries must be rooted as "!/<path>":\n'; \
	  printf '%s\n' "$$rootless" | sed 's/^/  /'; \
	  exit 1; \
	fi; \
	orphans=$$(grep '^!/' .gitignore | sed 's|^!/||; s|/\*\*$$|/|' | while read -r p; do \
	  case "$$p" in \
	    */) git ls-files --cached --others --exclude-standard -- "$${p%/}" | grep -q . \
	          || echo "$$p" ;; \
	    *)  git ls-files --error-unmatch "$$p" >/dev/null 2>&1 || echo "$$p" ;; \
	  esac; \
	done); \
	if [ -n "$$orphans" ]; then \
	  printf 'ERROR: .gitignore allowlists paths without a cached or visible target:\n'; \
	  printf '%s\n' "$$orphans" | sed 's|^|  !/|'; \
	  exit 1; \
	else \
	  printf 'allowlist-orphan-check: OK — every rooted allowlist entry resolves\n'; \
	fi

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
