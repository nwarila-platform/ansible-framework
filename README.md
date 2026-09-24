# ansible-framework

A professional, security-hardened Ansible automation framework for standardized, repeatable infrastructure and application deployments.

[![CI](https://github.com/nwarila-platform/ansible-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/nwarila-platform/ansible-framework/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Architecture

The framework is organized into namespaces, each mapped as an Ansible `roles_path` entry in `ansible.cfg`:

| Namespace            | Purpose                                                       |
|----------------------|---------------------------------------------------------------|
| `applications/`      | Application-specific roles (e.g., `python3_pip`, `wazuh_agent`) |
| `operating_systems/` | Per-OS bootstrap and hardening roles                          |
| `utilities/`         | Helper roles a play calls; they carry no lifecycle loader     |
| `host_roles/`        | What a host IS, not what it runs                              |

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
tasks/present_redhat_rocky_10.yml   ← most specific (state + family + distro + version)
tasks/present_redhat_rocky.yml      ← distro-level fallback
tasks/present_redhat.yml            ← family-level fallback
```

The resolved `state` is prefixed to every candidate. A role can ship a single `present_redhat.yml` that works across the RedHat family, while roles with distribution- or version-specific logic provide `present_redhat_rocky.yml` or `present_redhat_rocky_10.yml` (`python3_pip` ships family-level `present_redhat.yml` and `clean_redhat.yml`).

### 4. Secure Temp Directory
After the required OS facts are verified, an enabled temp directory is created as `0700
root:root` on non-Windows hosts and cleaned up in an `always:` block — even on failure.
Its parent location is configurable per role via `<role_name>.temp_dir_path` for hosts
whose default temp location is mounted `noexec` (STIG hardening); the parent must be a
dedicated, root-controlled absolute path, and an existing parent is validated but never
modified.

---

## Roles

### Applications

| Role                   | Description                                                                                                                              |
|------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| `linux_disk_manager`   | Step-0 storage initializer: selects disks by stable by-id identity, then partitions, formats, and mounts by UUID (VMware, Proxmox, AWS)   |
| `openvpn_client`       | OpenVPN community client for Windows, installed at a pinned version from S3 through the controller and verified against a pinned digest  |
| `python3_pip`          | Installs, upgrades, and configures Python3 pip with a security-hardened `pip.conf`                                                       |
| `wazuh_agent`          | Installs and enrolls the Wazuh agent: a standalone RPM on RedHat, an MSI on Windows, both fetched from S3                                |
| `windows_disk_manager` | Windows NTFS disk provisioning (initialize, partition, format) with stable disk identity and a drive-letter contract for VMware and AWS  |

### Operating Systems

| Role              | Description                                          | Status      |
|-------------------|------------------------------------------------------|-------------|
| `redhat_rocky_8`  | RHEL / Rocky Linux 8 bootstrap and STIG hardening    | In Progress |
| `windows_server_2022` | Windows Server 2022 bootstrap                  | In Progress |
| `windows_server_2025` | Windows Server 2025 bootstrap                  | In Progress |

### Utilities

| Role             | Description                                                          | Status |
|------------------|----------------------------------------------------------------------|--------|
| `credential_resolver` | Tries declared credential profiles and publishes the first working identity | In Progress |
| `host_readiness` | Proves the transport answers before anything that assumes it runs     | Stable |
| `os_bootstrap`   | Detects the OS and includes that role's `bootstrap.yml` entry point   | Stable |

### Host Roles

| Role            | Description                                                             | Status |
|-----------------|-------------------------------------------------------------------------|--------|
| `domain_member` | Joins a host to an Active Directory realm and proves its secure channel | Stable |
| `remote_client` | Site policy for the private network, handed to `openvpn_client`         | Stable |

---

## Getting Started

### Prerequisites

- ansible-core >= 2.21.3, < 2.22 (the range pinned in `requirements-dev.txt`; `domain_member` declares a 2.20 floor)
- Python >= 3.12
- `pre-commit` (for local hook enforcement)

### Development Setup

```bash
# Run once after cloning: installs the dev toolchain (requirements-dev.txt), the
# pinned runtime collections (requirements.yml, force-installed into your default
# Ansible collections path, ~/.ansible/collections unless configured otherwise),
# and the git hooks
make install

# Lint all files: every guard target, then the full pre-commit suite
make lint
make pre-commit
```

### Usage

```yaml
- hosts: all
  vars:
    ENV: prod
  roles:
    - python3_pip
```

Credential-changing deployments use the resolver as a play-level caller contract. Candidate
inputs, elevation requirements and `ssh_trusted_principals` are play variables, never role
parameters; resolving plays retain the `linear` strategy, and later plays declare no identity:

```yaml
roles:
  - { role: 'credential_resolver', tags: ['always'] }
  - role: 'host_readiness'
  - role: 'os_bootstrap'
  - role: 'domain_member'
  - role: 'credential_resolver'
    tags: ['always']
    when: __domain_member_boot_time__ is defined
    vars:
      credential_resolver_boot_time_after: "{{ __domain_member_boot_time__ }}"
  - role: 'host_readiness'
    when: __domain_member_boot_time__ is defined
  - role: 'domain_member'
    when: __domain_member_boot_time__ is defined
```

The play supplies `credential_resolver_candidates` and optional
`credential_resolver_require_elevated`. `os_bootstrap` consumes `ssh_trusted_principals`; the
first `domain_member` call uses `restart_wait: false`. The second resolver call proves an identity
on the new boot before readiness and membership are proved again.

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

Types:  feat | fix | docs | style | refactor | test | chore | perf | ci | build | revert
Scope:  role name or 'framework'
```

### Examples

```
feat(python3_pip): add Debian apt task file
fix(redhat_rocky_8): correct Python venv version comparison
chore(ci): pin ansible-lint to 25.2.0
```

---

## License

MIT — see [LICENSE](LICENSE).
