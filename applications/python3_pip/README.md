# python3_pip

Installs, upgrades, and configures Python3 pip with security-hardened defaults.

## What This Role Does

Execution path is controlled by the `state` variable:

| `state`    | Behaviour |
|------------|-----------|
| `present`  | Installs `python3-pip`, optionally self-upgrades pip, deploys `/etc/pip.conf`, validates with `pip3 --version` (default) |
| `absent`   | Uninstalls pip and removes its configuration |
| `clean`    | Removes pip caches and build artefacts without uninstalling |

---

## Supported Platforms

| OS                  | Version | Task Files (prefix `<state>_`) |
|---------------------|---------|--------------------------------|
| Rocky Linux / RHEL  | 10      | `tasks/<state>_redhat_rocky.yml` |
| Debian / Ubuntu     | all     | `tasks/<state>_debian_ubuntu.yml` |

Additional platforms are resolved via the hierarchical task loader. The resolved `state` is prepended to each candidate:

`present_redhat_rocky_10.yml` → `present_redhat_rocky.yml` → `present_redhat.yml`

## Quick Start

```yaml
# Minimal
- name: 'Install and configure pip'
  hosts: all
  become: true
  vars:
    ENV: 'prod'
  roles:
    - role: 'python3_pip'
```

Override individual settings without replacing the entire defaults dict:

```yaml
- name: 'Install pip with customised settings'
  hosts: all
  become: true
  vars:
    ENV: 'prod'
    python3_pip:
      self_upgrade:
        enabled: false
      templates:
        '/etc/pip.conf':
          file:
            mode: '0640'
  roles:
    - role: 'python3_pip'
```

---

## Role Variables

### Required Variables

| Variable | Required | Allowed Values | Description |
|----------|----------|----------------|-------------|
| `ENV` | **Yes** | Alphanumeric, hyphens, underscores — e.g. `prod`, `dev`, `staging` | Selects environment-specific overlay files (e.g. `vars/redhat_prod.yml`). Set via `group_vars`, `host_vars`, or `-e "ENV=prod"`. |
| `state` | No | `present`, `absent`, `clean` | Controls which entrypoint is executed. Defaults to `present`. |

`ENV` is validated on every role entry: it must be defined, non-empty, and match `^[a-zA-Z0-9_-]+$`. Path-traversal sequences such as `../../etc/passwd` are rejected. The role fails immediately with a descriptive error if the variable is missing or invalid.

`state` is validated against the allowed set. An invalid value fails with a descriptive error before any tasks run. Formal validation is also enforced by `meta/argument_specs.yml` (Ansible 2.11+).

---

### `python3_pip_defaults` (`defaults/main.yml`)

User-facing defaults. Override specific keys via `group_vars`, `host_vars`, or the
`python3_pip` role variable passed at invocation. Uses `combine(recursive=True)` so
only the keys you specify are changed — everything else inherits the default.

#### `package_manager`

Dict keyed by `os_family` (`RedHat`, `Debian`). Each entry maps directly to the
corresponding Ansible module parameters.

> **Debian / Ubuntu:** `update_cache` defaults to `false`. On a freshly provisioned image where `apt-get update` has not been run, set `update_cache: true` on first use or run a preceding apt update task to avoid “Unable to locate package” failures.

```yaml
python3_pip_defaults:
  package_manager:
    'RedHat':
      name: 'python3-pip'
      state: 'present'
      best: true
      disable_gpg_check: false
      sslverify: true
      validate_certs: true
      # ... all dnf parameters
    'Debian':
      name: 'python3-pip'
      state: 'present'
      # ... all apt parameters
```

**Overriding a single key:**
```yaml
python3_pip:
  package_manager:
    RedHat:
      lock_timeout: 60
```

#### `self_upgrade`

```yaml
python3_pip_defaults:
  self_upgrade:
    enabled: true
    version: 'latest'    # Or pin: '24.3.1'
```

#### `templates`

Dict keyed by destination path. Enables surgical per-key overrides without
replacing the entire template definition.

```yaml
python3_pip_defaults:
  templates:
    '/etc/pip.conf':
      template: 'pip.conf.j2'
      file:
        path: '/etc/pip.conf'
        owner: 'root'
        group: 'root'
        mode: '0644'
        selinux:
          level: 's0'
          role: 'object_r'
          type: 'etc_t'
          user: 'system_u'
      settings:
        global: { ... }
        install: { ... }
        # ... all pip.conf sections
```

**Overriding a single file attribute:**
```yaml
python3_pip:
  templates:
    '/etc/pip.conf':
      file:
        mode: '0640'
```

### `python3_pip_allowed_keys` (`vars/main.yml`)

Internal whitelist of valid pip.conf keys per section. Stored in `vars/` (not `defaults/`)
so it cannot be overridden via inventory or group_vars. The `pip.conf.j2` template silently
drops any key not present in this whitelist.

> **Not user-extensible.** Because `vars/` has higher Ansible variable precedence than
> `defaults/`, `python3_pip_allowed_keys` cannot be extended or overridden via inventory,
> `group_vars`, `host_vars`, or extra-vars. Any key added to `settings` that is absent
> from the whitelist is silently ignored at render time — it will not appear in
> `/etc/pip.conf` and no error is raised. To add a new pip.conf key, modify
> `vars/main.yml` directly in the role source.

---

## Security Highlights

- **`only_binary: ':all:'`** — prevents arbitrary `setup.py` code execution during install

  > **Compatibility note:** This setting causes `pip install <package>` to fail for any package that does not ship a pre-built wheel for the target platform and Python version. To install a source-only package in a specific environment, override via overlay:
  > ```yaml
  > python3_pip:
  >   templates:
  >     '/etc/pip.conf':
  >       settings:
  >         install:
  >           only_binary: ':none:'
  > ```

- **Whitelist-based template rendering** — unrecognized pip.conf keys are silently dropped, never rendered
- **`break_system_packages: false`** — protects system Python from PEP 668 override
- Deviation rationale is documented inline in `defaults/main.yml` for every non-default value

### Intentionally Omitted pip.conf Keys

The following keys are supported by pip but intentionally excluded from `defaults/main.yml`.
They remain available in the `python3_pip_allowed_keys` whitelist (`vars/main.yml`) and can
be set via overlay or user overrides when required.

| Section | Key | Why It's Omitted |
|---------|-----|------------------|
| `global` | `cache_dir` | Use pip default (`~/.cache/pip`); ensure `0700` permissions if overriding |
| `global` | `cert` | Use system cert store; only set for internal CAs |
| `global` | `client_cert` | Only if mutual TLS required; ensure `0600` permissions on the cert file |
| `global` | `log` | Logs can leak credentials, URLs, and tokens |
| `global` | `proxy` | Only if needed; never embed credentials in the proxy URL |
| `global` | `trusted_host` | **NEVER set** — bypasses TLS verification entirely for listed hosts |
| `global` | `use_deprecated` | **NEVER set** — deprecated features have known weaknesses |
| `global` | `use_feature` | Only enable after evaluating security impact of each feature flag |
| `install` | `extra_index_url` | **NEVER set** — primary vector for dependency confusion attacks |
| `install` | `find_links` | Only set with strict directory permissions (`0700`) |
| `install` | `index_url` | pip default (`https://pypi.org/simple`) is secure; change only for private proxy repos |
| `install` | `no_binary` | **Do NOT set** — source builds execute arbitrary `setup.py` code |
| `install` | `prefix` | Only set in controlled (container/chroot) environments |
| `install` | `report` | Enable in CI/CD pipelines for audit trails |
| `install` | `root` | Only set for container/chroot builds |
| `install` | `src` | Use pip default (`<venv>/src`) |
| `install` | `target` | Only set in controlled environments |
| `download` | `abi` | Set explicitly only if cross-downloading for a different ABI |
| `download` | `dest` | Use a permission-restricted directory (`0700`) if overriding |
| `download` | `implementation` | Set only if cross-downloading for a different Python implementation |
| `download` | `no_binary` | **Do NOT set** — source builds run arbitrary code |
| `download` | `only_binary` | Set to `':all:'` in hardened pipelines |
| `download` | `platform` | Set only if cross-downloading for a different platform |
| `download` | `python_version` | Set only if cross-downloading for a different Python version |
| `download` | `src` | Use pip default; ensure restricted permissions if overriding |
| `freeze` | `exclude` | **Do NOT exclude** — freeze everything for supply chain control |
| `freeze` | `exclude_editable` | Set `true` for production lockfiles |
| `freeze` | `requirement` | Point to canonical requirements file if applicable |
| `list` | `exclude` | **NEVER set** — hiding packages masks security issues |
| `list` | `exclude_editable` | Keep visible for audit transparency |
| `list` | `format` | Use `'json'` for automated security scanning |
| `list` | `include_editable` | Keep visible for audit transparency |
| `wheel` | `no_binary` | **Do NOT set** — source builds run arbitrary code |
| `wheel` | `only_binary` | Set to `':all:'` for dependencies in hardened pipelines |
| `wheel` | `src` | Use pip default; ensure restricted permissions if overriding |
| `wheel` | `wheel_dir` | Use a permission-restricted directory (`0700`) if overriding |

> **`require_hashes`** is set to `false` globally because enabling it breaks bare `pip install`
> commands. Enable per-requirements-file via overlay for reproducible, integrity-verified pipelines.

---

## Known Gaps / TODO

### Molecule Integration Tests (Medium Priority)

The `molecule/` directory is a stub. Integration tests should validate:

- Package installation succeeds on a clean Rocky 10 target
- `pip.conf` renders with expected content (diff against a fixture)
- `pip3 --version` returns the expected version after self-upgrade
- Whitelisted keys render; non-whitelisted keys are silently dropped
- Overlay vars correctly merge and override defaults
- Idempotency: running the role twice produces no changes on the second run

### Template Validation (Low Priority)

`ansible.builtin.template` does not use the `validate` parameter. A validation
command would catch malformed configs before they land on disk:

```yaml
validate: 'pip3 config debug %s'
```

Verify `pip3 config debug` accepts a file path argument on the target OS before
enabling — may require a wrapper script.

### Self-Upgrade Idempotency Reporting (Low Priority)

When `version: 'latest'`, the pip task always reports `changed` even if pip was
already at the latest version. A registered result + debug task could surface
whether an actual upgrade occurred vs. a no-op.

---

## Testing

Integration tests are not yet implemented — the `molecule/` directory is a stub.

To bootstrap a Molecule test suite:

1. Create `molecule/default/molecule.yml` with a Rocky Linux 10 driver (e.g. `docker` or `vagrant`).
2. Create `molecule/default/converge.yml` invoking the role with `ENV: test`.
3. Create `molecule/default/verify.yml` asserting:
   - `/etc/pip.conf` content matches a committed golden fixture
   - `pip3 --version` exits zero and returns the expected version
   - Running the role a second time produces zero changed tasks (idempotency)
4. Add additional scenarios for: `self_upgrade.enabled: false`, pinned version, overlay merge, and ENV validation failure.

See **Known Gaps → Molecule Integration Tests** for the full scenario list.
