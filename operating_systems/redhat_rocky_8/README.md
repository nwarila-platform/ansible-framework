# `redhat_rocky_8` role

Brings a newly provisioned RHEL or Rocky Linux 8 host to the minimum state the ansible-framework suite assumes, and optionally applies the STIG hardening this platform is deployed under.

> **Scope:** bootstrap and hardening only. This role installs no product and configures no service. It has two named entry points and no generic one, so it is always called explicitly.

## Composition and prerequisites

```yaml
- name: 'Bootstrap | RHEL or Rocky 8 minimum'
  hosts: 'linux'
  gather_facts: false
  tasks:
    - name: 'Bootstrap | RHEL or Rocky 8'
      ansible.builtin.include_role:
        name: 'redhat_rocky_8'
        tasks_from: 'bootstrap'
```

`operating_systems` must be on `roles_path`; the framework's `ansible.cfg` declares it, and a consuming product that overrides that file must re-add it.

`tasks/main.yml` is a guard that fails loudly rather than a loader. The shared application loader is not valid here: its `ENV` contract is unrelated to bootstrap, and it can execute a remote module before `tasks/bootstrap.yml` has established the caller-configured remote-tmp base. With no `main.yml` at all, ansible-core would treat an accidental generic call as an empty task list and report success.

## What the caller supplies

Nothing is required. Every input has a default in `defaults/main.yml`; the ones a caller most often sets are below.

| Variable | Default | Purpose |
|---|---|---|
| `rhel8_bootstrap_remote_tmp_base` | the shell plugin's `remote_tmp` | Where AnsiballZ stages modules. Must be writable by the login user and exec-capable. |
| `rhel8_bootstrap_prerequisite_roles` | `[]` | Roles to run before the package work. Empty by default; nothing is enabled out of the box. |
| `rhel8_bootstrap_manage_hostname` | `false` | Whether the role sets the system hostname and updates the hosts file. |
| `rhel8_hardening_*` | see `defaults/main.yml` | Per-control switches for the STIG entry point. |

## Entry points

| `tasks_from` | What it does |
|---|---|
| `bootstrap` | Remote-tmp base, prerequisite packages, python3.12, the `/opt/ansible` virtualenv with pinned boto3, fapolicyd trust, and optionally the hostname. |
| `hardening` | STIG kernel parameters, SSH daemon directives, local package signature enforcement, Ctrl-Alt-Del behaviour, and PAM `nullok` removal. |

## State

Both entry points are re-runnable. The virtualenv is probed for drift — a wrong Python version or a missing `--system-site-packages` flag — and rebuilt only when it has drifted. Package and pip work is idempotent.

## Design invariants

- **Python 3.12 is installed before any module runs.** The raw install command first refuses any host other than RHEL or Rocky 8, and every role module is pinned to `rhel8_bootstrap_python_bin`.
- **The remote-tmp base is created in one pass before packaged prerequisites and venv work.** Ownership, mode and SELinux context are applied together.
- **Prerequisite package installation is not error-tolerant.** A repository or package failure is reported at that task instead of surfacing later during venv work.
- **Venv drift is detected structurally, not by message text.** The probe reads `lineinfile`'s documented `found` counter rather than its undocumented `msg` string, so an upstream rewording cannot silently disable drift detection and leave stale virtualenvs in place forever.
- **fapolicyd trust is applied both before and after the pip work**, and the database is refreshed inline each time, because trust that takes effect later does not help an install happening now.

## Verification

The raw Python install refuses the wrong distribution or major release before changing it. The module-based guard then asserts family, distribution and major version from identity operands in `vars/main.yml` rather than `defaults/`, so a caller cannot override the check into uselessness. The python3.12 version is read back for drift detection, and the hostname is confirmed against what the playbook declared.
