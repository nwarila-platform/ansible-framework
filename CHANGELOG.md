# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Release-please will insert new entries above this line -->

## [0.1.1](https://github.com/nwarila-platform/ansible-framework/compare/v0.1.0...v0.1.1) (2026-07-30)


### Features

* add linux_disk_manager role + adopt v3.1.0 loader in application roles ([#30](https://github.com/nwarila-platform/ansible-framework/issues/30)) ([5e85501](https://github.com/nwarila-platform/ansible-framework/commit/5e85501ae968345f449aaee6c2ed1f2e5fb90c07))
* add Rocky Linux 9 hardening role ([#20](https://github.com/nwarila-platform/ansible-framework/issues/20)) ([1fac537](https://github.com/nwarila-platform/ansible-framework/commit/1fac537adef9ebbb8261ecbae931f83060896f1f))
* **framework:** scaffold Ansible automation framework with roles, CI, and tooling ([5d9972e](https://github.com/nwarila-platform/ansible-framework/commit/5d9972e188f3476b01b840e5fabcc1d2543957e7))
* **loader:** Windows-safe shared loader, os_bootstrap dispatcher, dev tier ([#34](https://github.com/nwarila-platform/ansible-framework/issues/34)) ([94d280e](https://github.com/nwarila-platform/ansible-framework/commit/94d280e1bc7e0c3f6e56d1b807fd3b0a931cd7ae))
* **os:** RHEL/Rocky 8 + Windows Server 2025 bootstrap roles, and a lint gate that runs ([#33](https://github.com/nwarila-platform/ansible-framework/issues/33)) ([6335fcb](https://github.com/nwarila-platform/ansible-framework/commit/6335fcb3a90e231195c7b2fd49174eccb26c1356))
* **s3_artifact_delivery:** add a controller-download entry point ([#45](https://github.com/nwarila-platform/ansible-framework/issues/45)) ([b6258af](https://github.com/nwarila-platform/ansible-framework/commit/b6258af3abf0c34e521f0383e51776478f1c5533))
* **s3_artifact_delivery:** fetch artifacts with a presigned URL so no target holds AWS authority ([#40](https://github.com/nwarila-platform/ansible-framework/issues/40)) ([c3ba9d4](https://github.com/nwarila-platform/ansible-framework/commit/c3ba9d44fc47d73b26af11dc762790616edc5d29))
* **s3_artifact_delivery:** fetch artifacts with a presigned URL so no target holds AWS authority ([#42](https://github.com/nwarila-platform/ansible-framework/issues/42)) ([cb3bea3](https://github.com/nwarila-platform/ansible-framework/commit/cb3bea3e329ac22f08118bdc4960d22aa74a1cb6))
* seamless agent reconnect + AWS disk provider + audit hardening ([#32](https://github.com/nwarila-platform/ansible-framework/issues/32)) ([ff30927](https://github.com/nwarila-platform/ansible-framework/commit/ff30927b944aa0fea4c92fcf36f9ebc32a95189a))
* wazuh_agent endpoint role + linux_disk_manager growfs ([#31](https://github.com/nwarila-platform/ansible-framework/issues/31)) ([3fad00a](https://github.com/nwarila-platform/ansible-framework/commit/3fad00a07bde6ac89f4c889a25067b49b8e37bf3))
* **wazuh_agent:** stamp a trigger timestamp so a FIM proof cannot be satisfied by an older alert ([#35](https://github.com/nwarila-platform/ansible-framework/issues/35)) ([94844aa](https://github.com/nwarila-platform/ansible-framework/commit/94844aa46520d31489af6c94c137943900b96956))
* **windows_disk_manager:** Windows disk-provisioning role (sibling of linux_disk_manager) ([#39](https://github.com/nwarila-platform/ansible-framework/issues/39)) ([2b088fa](https://github.com/nwarila-platform/ansible-framework/commit/2b088faeb949459a22e52d9a8f75b7c9ba81e754))


### Bug Fixes

* **loader:** fail when a role's defaults namespace stops matching its directory ([#44](https://github.com/nwarila-platform/ansible-framework/issues/44)) ([55c85c5](https://github.com/nwarila-platform/ansible-framework/commit/55c85c5ec8fa03bacd81c9cfcade81a27945036d))
* normalize line endings to LF and clean ansible-lint/YAML config ([#14](https://github.com/nwarila-platform/ansible-framework/issues/14)) ([0cdea94](https://github.com/nwarila-platform/ansible-framework/commit/0cdea945222c36377f4bcef956dcbd6bdd3bfbe2))
* **s3_artifact_delivery:** let the contract guard say which input is wrong ([#43](https://github.com/nwarila-platform/ansible-framework/issues/43)) ([dcb3b5d](https://github.com/nwarila-platform/ansible-framework/commit/dcb3b5df6b94781a3f213cf62308d1015509cc0b))
* **s3_artifact_delivery:** make redaction the module's own property, and say why a fetch failed ([#46](https://github.com/nwarila-platform/ansible-framework/issues/46)) ([a9f4451](https://github.com/nwarila-platform/ansible-framework/commit/a9f44519778dbd156e7607560a78dbf9f7c9cca4))
* **wazuh_agent:** derive agent-name uniqueness from the play, not a consumer's inventory groups ([#36](https://github.com/nwarila-platform/ansible-framework/issues/36)) ([587899e](https://github.com/nwarila-platform/ansible-framework/commit/587899ef7ab000e8f2f547852b55edec09566f59))


### Reverts

* 40 — the squash carried three unrelated WDM stages ([#41](https://github.com/nwarila-platform/ansible-framework/issues/41)) ([65500d7](https://github.com/nwarila-platform/ansible-framework/commit/65500d7228dbbb34390becbb4600ad50cd208337))


### Documentation

* reconcile role namespaces between ansible.cfg, README, and on-disk layout ([#19](https://github.com/nwarila-platform/ansible-framework/issues/19)) ([c510e26](https://github.com/nwarila-platform/ansible-framework/commit/c510e26e30d60cb4138ab004f28db17d5ed2304d))


### CI/CD

* add security scanning via nwarila-platform reusable workflows ([#18](https://github.com/nwarila-platform/ansible-framework/issues/18)) ([1fca724](https://github.com/nwarila-platform/ansible-framework/commit/1fca724e3c7643382abc5b2008961ea4957f13a8))
* run CI on main and drop broken pip cache ([#16](https://github.com/nwarila-platform/ansible-framework/issues/16)) ([4cd88ff](https://github.com/nwarila-platform/ansible-framework/commit/4cd88ff5122f9c5bd054961acbe242118b3dade9))


### Miscellaneous

* clean up .gitignore comments and remove Claude-specific entries ([81b7792](https://github.com/nwarila-platform/ansible-framework/commit/81b7792a81cf45a48e21dcc3142638d029d9d5b3))
* **codeowners:** sync CODEOWNERS via terraform ([2a72297](https://github.com/nwarila-platform/ansible-framework/commit/2a722976eed9d561ec6fc1c645436834443998aa))
* **codeowners:** sync CODEOWNERS via terraform ([051a85f](https://github.com/nwarila-platform/ansible-framework/commit/051a85f1e427889b56d8ba8cbce2dd07c5f15d69))
* **codeowners:** sync CODEOWNERS via terraform ([68c0095](https://github.com/nwarila-platform/ansible-framework/commit/68c0095234b9e44e6cac1c758db7f7bbe657640e))
* **deps-dev:** bump pre-commit from 4.0.1 to 4.6.1 ([#38](https://github.com/nwarila-platform/ansible-framework/issues/38)) ([658c6cc](https://github.com/nwarila-platform/ansible-framework/commit/658c6cce425022d08027c31801473df929abbd37))
* **deps-dev:** bump the dev toolchain as one coherent set (supersedes [#29](https://github.com/nwarila-platform/ansible-framework/issues/29), [#27](https://github.com/nwarila-platform/ansible-framework/issues/27)) ([#47](https://github.com/nwarila-platform/ansible-framework/issues/47)) ([bf0ca6b](https://github.com/nwarila-platform/ansible-framework/commit/bf0ca6b4c241f6deec5987cea4eb29073064dd2b))
* **deps:** bump actions/checkout from 4.3.1 to 7.0.1 ([#37](https://github.com/nwarila-platform/ansible-framework/issues/37)) ([7ba5e1a](https://github.com/nwarila-platform/ansible-framework/commit/7ba5e1a26028c91598c2ae5bfec7c11bcf3d8fe1))
* **deps:** bump actions/setup-python from 5.6.0 to 7.0.0 ([#28](https://github.com/nwarila-platform/ansible-framework/issues/28)) ([45543f7](https://github.com/nwarila-platform/ansible-framework/commit/45543f7813f14049c5990844caccdd20ad8a205a))

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
