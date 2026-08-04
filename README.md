# ansible-framework

A professional, security-hardened Ansible automation framework for standardized, repeatable infrastructure and application deployments.

[![CI](https://github.com/HellBomb/ansible-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/HellBomb/ansible-framework/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Architecture

The framework is organized into namespaces, each mapped as an Ansible `roles_path` entry in `ansible.cfg`:

| Namespace            | Purpose                                                    |
|----------------------|------------------------------------------------------------|
| `applications/`      | Application-specific roles (e.g., `python3_pip`, `nginx`)  |
| `operating_systems/` | OS bootstrap and hardening roles                           |

Roles are referenced directly by name — no path prefix required. Ansible resolves them via `roles_path`.

---

## Role Loader Pattern

Reusable application roles ship a shared `tasks/main.yml` loader that provides a consistent
execution contract. Bootstrap roles may instead guard the generic entry point and require callers
to select a named task file explicitly with `tasks_from`.

### 1. Validation
- Requires a mandatory `ENV` variable (e.g., `dev`, `staging`, `prod`)
- Enforced regex: alphanumeric, hyphens, underscores only

### 2. Layered Configuration Merging
Config is built from least to most specific, merged with `combine(recursive=True)`:

```
<role_name>_defaults variable when defined; otherwise {}
  → vars/<os_family>.yml
  → vars/<os_family>_<env>.yml
  → vars/<os_family>_<dist>.yml
  → vars/<os_family>_<dist>_<env>.yml
  → vars/<os_family>_<dist>_<ver>.yml
  → vars/<os_family>_<dist>_<ver>_<env>.yml
  → caller-supplied role var overrides
```

The seed variable may come from any normal Ansible variable source. Merely shipping
`defaults/main.yml` does not make that variable mandatory.

### 3. Hierarchical Task Resolution
The loader selects the **most specific** matching task file that exists:

```
tasks/redhat_rocky_10.yml   ← most specific (family + distro + version)
tasks/redhat_rocky.yml      ← distro-level fallback
tasks/redhat.yml            ← family-level fallback
```

A role like `python3_pip` can ship a single `redhat.yml` that works across all RedHat-family systems, while roles with version-specific logic provide `redhat_rocky_10.yml`.

### 4. Secure Temp Directory
After the required OS facts are verified, an enabled temp directory is created as `0700
root:root` on non-Windows hosts and cleaned up in an `always:` block — even on failure.

---

## Roles

### Applications

| Role          | Description                                                                              | Status |
|---------------|------------------------------------------------------------------------------------------|--------|
| `python3_pip` | Installs, upgrades, and configures Python3 pip with a security-hardened `pip.conf`      | Stable |

### Operating Systems

| Role              | Description                                          | Status      |
|-------------------|------------------------------------------------------|-------------|
| `RedHat_Rocky_10` | Full OS bootstrap: Ansible venv, packages, hostname  | In Progress |
| `RedHat_Rocky_9`  | Rocky Linux 9 bootstrap                              | Planned     |
| `RedHat_Rocky_8`  | RHEL / Rocky Linux 8 bootstrap                       | In Progress |
| `Windows_Server_2025` | Windows Server 2025 bootstrap                  | In Progress |

---

## Getting Started

### Prerequisites

- Ansible >= 2.17, < 2.19
- Python >= 3.12
- `pre-commit` (for local hook enforcement)

### Development Setup

```bash
# Install pre-commit hooks (run once after cloning)
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# Lint all files
pre-commit run --all-files
ansible-lint
yamllint --config-file .yamllint.yml .
```

### Usage

```yaml
- hosts: all
  vars:
    ENV: prod
  roles:
    - python3_pip
```

### Overriding Defaults

Shared-loader application roles conventionally define a `<role_name>_defaults` mapping in
`defaults/main.yml`. This is a repository convention, not a loader prerequisite: when the
variable is undefined, the loader seeds an empty mapping before applying overlays and caller
overrides. Override specific settings without replacing the entire structure:

```yaml
# group_vars/prod.yml
python3_pip:
  self_upgrade:
    version: '24.3.1'
  templates:
    '/etc/pip.conf':
      file:
        mode: '0640'
```

---

## Contributing

This project uses [Conventional Commits](https://www.conventionalcommits.org/), enforced by pre-commit. Merging to `main` triggers release-please, which opens a Release PR and eventually creates a tagged GitHub Release.

### Commit Format

```
<type>(<scope>): <description>

Types:  feat | fix | docs | refactor | test | chore | perf | ci | build | revert
Scope:  role name or 'framework'
```

### Examples

```
feat(python3_pip): add Debian apt task file
fix(RedHat_Rocky_10): correct Python venv version comparison
chore(ci): pin ansible-lint to 25.2.0
```

---

## License

MIT — see [LICENSE](LICENSE).
