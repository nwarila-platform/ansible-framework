# =============================================================================
# Makefile — Developer Convenience Targets
# =============================================================================
# Usage:
#   make install      Install all dev dependencies
#   make lint         Run yamllint + ansible-lint + allowlist guard
#   make pre-commit   Run full pre-commit suite against all files
#   make allowlist-check
#                     Fail if a deliverable file is silently ignored
#   make loader-identity-check
#                     Assert every framework application loader is byte-identical
#   make clean        Remove Python cache artifacts
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help install lint yamllint ansible-lint allowlist-check loader-identity-check pre-commit clean

# The deny-all guard scans the whole repository. Only rooted, known local artifacts are excluded:
# Ansible/cache state, the handoff workspace, a root .env, Python caches, and retry files.
GUARD_EXCLUDE := ^(_handoff/|\.ansible/|\.cache/|\.env$$|([^/]+/)*(__pycache__|\.cache)/|([^/]+/)*[^/]+\.(py[co]|retry)$$)

LOADER_PATHS := \
	applications/linux_disk_manager/tasks/main.yml \
	applications/python3_pip/tasks/main.yml \
	applications/wazuh_agent/tasks/main.yml

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
	@echo "  make loader-identity-check"
	@echo "                     Assert every framework application loader is byte-identical"
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
lint: yamllint ansible-lint allowlist-check loader-identity-check

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

# The application loader is intentionally copied into each role so every role is standalone.
# Compare the current bytes to one another; no expected digest is stored because legitimate
# loader changes must not require maintaining a second version value in CI.
loader-identity-check:
	@digest_count=$$(sha256sum $(LOADER_PATHS) | cut -d' ' -f1 | sort -u | wc -l); \
	if [ "$$digest_count" -ne 1 ]; then \
	  printf 'ERROR: application role loaders are not byte-identical:\n'; \
	  sha256sum $(LOADER_PATHS); \
	  exit 1; \
	fi; \
	digest=$$(sha256sum $(firstword $(LOADER_PATHS)) | cut -d' ' -f1); \
	printf 'loader-identity-check: OK — all framework copies share sha256 %s\n' "$$digest"

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
