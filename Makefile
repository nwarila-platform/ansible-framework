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
#   make loader-defaults-convention-check
#                     Assert every loader role's defaults file defines its namespaced key
#   make clean        Remove Python cache artifacts
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help install lint yamllint ansible-lint allowlist-check loader-identity-check loader-defaults-convention-check pre-commit clean

# The deny-all guard scans the whole repository. Only rooted, known local artifacts are excluded:
# Ansible/cache state, the handoff workspace, a root .env, Python caches, and retry files.
# The last alternative covers MATERIALIZED role scripts. A role that executes a first-class
# PowerShell script tracks only files/<Name>.ps1.stub; scripts/materialize-role-scripts.sh copies
# the reviewed source from scripts/ to files/<Name>.ps1 before the role runs. That copy is a build
# artifact, so it is deliberately unallowlistable AND must not fail this guard on a checkout where
# the build step has run. Scoped to the one role that has stubs, so an unreviewed .ps1 dropped into
# any other role's files/ is still caught -- widen it per-role, never to a wildcard.
GUARD_EXCLUDE := ^(_handoff/|\.ansible/|\.cache/|\.env$$|([^/]+/)*(__pycache__|\.cache)/|([^/]+/)*[^/]+\.(py[co]|retry)$$|applications/openvpn_client/files/[^/]+\.ps1$$)

LOADER_PATHS := \
	applications/linux_disk_manager/tasks/main.yml \
	applications/openvpn_client/tasks/main.yml \
	applications/python3_pip/tasks/main.yml \
	applications/wazuh_agent/tasks/main.yml \
	applications/windows_disk_manager/tasks/main.yml \
	roles/domain_member/tasks/main.yml

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
	@echo "  make loader-defaults-convention-check"
	@echo "                     Assert every loader role's defaults file defines its namespaced key"
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
lint: yamllint ansible-lint allowlist-check loader-identity-check loader-defaults-convention-check

yamllint:
	yamllint --config-file .yamllint.yml .

ansible-lint:
	@files=$$(git ls-files --cached --others --exclude-standard -- applications operating_systems \
	  | grep -E '\.ya?ml$$' | sort \
	  | while IFS= read -r file; do [ -f "$$file" ] && printf '%s\n' "$$file"; done); \
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
	    *)  git ls-files --cached --others --exclude-standard -- "$$p" | grep -q . \
	          || echo "$$p" ;; \
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

# The loader (v3.2.3+) treats '<role_name>_defaults' as optional and seeds {} when it is
# undefined, so a role-directory rename that orphans the hand-written key no longer fails at
# runtime. This repository-side check catches that orphan at PR time instead: every role in
# LOADER_PATHS that ships defaults/main.yml must define its own namespaced top-level key.
# Roles outside LOADER_PATHS (empty or flat defaults shapes) are deliberately not covered.
loader-defaults-convention-check:
	@status=0; \
	for path in $(LOADER_PATHS); do \
	  role_dir=$$(dirname $$(dirname $$path)); \
	  role=$$(basename $$role_dir); \
	  defaults=$$role_dir/defaults/main.yml; \
	  if [ -f "$$defaults" ] && ! grep -Eq "^$${role}_defaults:" "$$defaults"; then \
	    printf 'ERROR: %s exists but defines no top-level "%s_defaults:" key.\n' "$$defaults" "$$role"; \
	    printf 'Rename the key to match the role directory, or drop the defaults file.\n'; \
	    status=1; \
	  fi; \
	done; \
	if [ "$$status" -eq 0 ]; then \
	  printf 'loader-defaults-convention-check: OK — every loader role defaults file defines its namespaced key\n'; \
	fi; \
	exit $$status

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
