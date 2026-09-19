# `redhat_rocky_9` role

Brings a newly provisioned RHEL or Rocky Linux 9 host to the minimum state the ansible-framework suite assumes.

> **Scope:** bootstrap only. This role installs no product and configures no service. It has one named entry point and no generic one, so it is always called explicitly. It carries no `hardening` entry point: see the note in `tasks/bootstrap.yml`.

## Composition and prerequisites

```yaml
- name: 'Bootstrap | RHEL or Rocky 9 minimum'
  hosts: 'linux'
  gather_facts: false
  tasks:
    - name: 'Bootstrap | RHEL or Rocky 9'
      ansible.builtin.include_role:
        name: 'redhat_rocky_9'
        tasks_from: 'bootstrap'
```

`operating_systems` must be on `roles_path`; the framework's `ansible.cfg` declares it, and a consuming product that overrides that file must re-add it.

`tasks/main.yml` is a guard that fails loudly rather than a loader. The shared application loader is not valid here: its `ENV` contract is unrelated to bootstrap, and it can execute a remote module before `tasks/bootstrap.yml` has established the caller-configured remote-tmp base. With no `main.yml` at all, ansible-core would treat an accidental generic call as an empty task list and report success.

## What the caller supplies

Nothing is required. Every input has a default in `defaults/main.yml`; the ones a caller most often sets are below.

| Variable | Default | Purpose |
|---|---|---|
| `rhel9_bootstrap_remote_tmp_base` | the shell plugin's `remote_tmp` | Where AnsiballZ stages modules. Must be writable by the login user and exec-capable. |
| `rhel9_bootstrap_prerequisite_roles` | `[]` | Roles to run before the package work. Empty by default; nothing is enabled out of the box. |
| `rhel9_bootstrap_manage_hostname` | `false` | Whether the role sets the system hostname and updates the hosts file. |

## Entry points

| `tasks_from` | What it does |
|---|---|
| `bootstrap` | Remote-tmp base, prerequisite packages, python3.12, the `/opt/ansible` virtualenv with pinned boto3, fapolicyd trust, and optionally the hostname. |

## State

The `bootstrap` entry point is re-runnable. The virtualenv is probed for drift — a wrong Python version or a missing `--system-site-packages` flag — and rebuilt only when it has drifted. Package and pip work is idempotent.

## Design invariants

- **The remote-tmp base is created before anything else in the main stage**, and in two passes. Pass one creates it without an SELinux context, because the host does not yet have the `python3-libselinux` binding that a context request needs; pass two applies the context immediately after `dnf` installs that binding.
- **Prerequisite package installation is not error-tolerant.** Everything below it depends on python3.12 existing, and masking a failure there resurfaces as a confusing venv error several tasks later.
- **Venv drift is detected structurally, not by message text.** The probe reads `lineinfile`'s documented `found` counter rather than its undocumented `msg` string, so an upstream rewording cannot silently disable drift detection and leave stale virtualenvs in place forever.
- **fapolicyd trust is applied both before and after the pip work**, and the database is refreshed inline each time, because trust that takes effect later does not help an install happening now.

## Verification

The OS is asserted by family, distribution and major version before any work begins, from identity operands in `vars/main.yml` rather than `defaults/`, so a caller cannot override the check into uselessness. The python3.12 version is read back for drift detection, and the hostname is confirmed against what the playbook declared.
