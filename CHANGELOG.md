# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Release-please will insert new entries above this line -->

## [0.1.1](https://github.com/nwarila-platform/ansible-framework/compare/v0.1.0...v0.1.1) (2026-04-24)


### Features

* **framework:** scaffold Ansible automation framework with roles, CI, and tooling ([e1b52f3](https://github.com/nwarila-platform/ansible-framework/commit/e1b52f33d9270b14ba55cdb5810a7a3de0c83b90))

## [0.1.0] - 2026-03-11

### Features

- **framework**: Universal role loader (`tasks/main.yml`) with layered config merging, hierarchical OS task resolution, and secure temp directory management
- **framework**: `__os_candidates__` list drives both variable overlay loading and task file resolution from a single computed set
- **python3_pip**: Security-hardened role for installing, upgrading, and configuring Python3 pip
- **python3_pip**: Dynamic `pip.conf.j2` Jinja2 template with whitelist-based input validation per section
- **python3_pip**: Dict-keyed `package_manager` defaults enabling clean per-platform overlay with `combine(recursive=True)`
- **python3_pip**: Dict-keyed `templates` defaults enabling targeted per-key overrides without full list replacement
- **python3_pip**: pip self-upgrade task with pinned or `latest` version support, idempotent `| bool` guard
- **python3_pip**: Smoke-test validation stage using `failed_when: false` + `ansible.builtin.assert` pattern
- **RedHat_Rocky_10**: Full OS bootstrap role including Python venv at `/opt/ansible`, hostname configuration, and prerequisite package installation

### Build System

- Add `.gitignore` with Ansible, Python, secret, and editor artifact exclusions
- Add `.yamllint.yml` with Ansible-appropriate overrides (160-char line limit, YAML 1.2 truthy enforcement)
- Add `.ansible-lint` with `safety` profile, `loop_var_prefix` enforcement, and offline mode for CI
- Add `.pre-commit-config.yaml` with hygiene, yamllint, ansible-lint, and conventional commit hooks
- Add `release-please-config.json` and `.release-please-manifest.json` for automated changelog and release management

[0.1.0]: https://github.com/HellBomb/ansible-framework/releases/tag/v0.1.0
