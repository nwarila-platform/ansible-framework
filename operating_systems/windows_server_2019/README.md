# `windows_server_2019` role

Brings a newly launched Windows Server 2019 host to the minimum state the ansible-framework suite assumes: PowerShell served over the transport, an elevated session token, and the computer name set before anything tries to join a directory.

> **Scope:** bootstrap only. This role repairs the conditions other roles take for granted; it installs no product and configures no service. It is called explicitly by the deploying playbook and never by the shared loader.

## Composition and prerequisites

Call it once, before every other play against the Windows group:

```yaml
- name: 'Bootstrap | Windows Server 2019 minimum requirements'
  hosts: 'windows'
  gather_facts: false
  tasks:
    - name: 'Bootstrap | Windows Server 2019'
      ansible.builtin.include_role:
        name: 'windows_server_2019'
        tasks_from: 'bootstrap'
```

`operating_systems` must be on `roles_path`; the framework's `ansible.cfg` declares it, and a consuming product that overrides that file must re-add it.

Three call conditions are load-bearing, and each exists because its absence has failed:

- **`gather_facts` must be false.** Implicit gathering runs a PowerShell module before this role can repair the shell, over whatever shell type the inventory guessed — the exact failure the role exists to prevent. It loads the facts it needs itself, after the gate.
- **Pass no `vars:` to the include.** Include-role params outrank the connection scoping this role sets, so a stray `ansible_shell_type` on the include defeats the repair.
- **Exactly one invocation, first.** A deployment path once reached the agent stage without this having run, and the first file push died on a cmd-ism.

There is deliberately no generic entry point: `tasks/main.yml` is a guard that fails loudly, because a missing `main.yml` would let an accidental call report success having done nothing.

## What the caller supplies

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `windows_bootstrap_hostname` | No | `inventory_hostname` | The computer name to set. Declared as a **play** variable, never as `vars:` on the include. An empty value skips the rename entirely. |

## Configuration

The role has no `defaults/` inputs beyond the variable above and reads no merged configuration dictionary; it is not a loader role.

## State

The role is re-runnable. The shell flip is skipped when DefaultShell already serves PowerShell, and the rename is skipped when the declared name already matches the machine. A rename restarts the host once and waits for it to answer.

## Design invariants

- **The transport is repaired before any fact is gathered.** OpenSSH on a fresh image serves `cmd`; a module run over `cmd` fails in ways that do not name the cause. The role flips `DefaultShell`, resets the connection so the new shell takes effect, and verifies the shell before proceeding.
- **An elevated token is required, not requested.** A filtered token cannot elevate itself in-session, so the role reads the token and refuses early with the reason rather than failing later inside unrelated work.
- **The name is set before any directory join.** Renaming after a join needs directory credentials the bootstrap does not hold, and Windows answers "Access is denied". The role refuses that ordering explicitly rather than letting it surface as a permission error.
- **The release is asserted, not inferred.** Windows Server 2019 is NT 10.0 build 17763, and the product type is asserted as well, so the role states what it supports rather than relying on a build number being unambiguous.

## Verification

Every mutation is followed by a read-back: the shell is re-queried after the flip, and the computer name is read from the machine after the restart and compared with what the playbook declared. The role fails on a mismatch rather than reporting success.
