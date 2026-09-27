# OS bootstrap dispatcher

`os_bootstrap` selects and runs the bootstrap role for each host. It does one thing: detect the
operating system, then include the applicable role's `tasks/bootstrap.yml` entry point. It
converges nothing itself, which is why it lives under `utilities/` rather than
`operating_systems/`: it is a helper a play calls, not something a host has deployed to it, and
this one's `tasks/main.yml` is the dispatcher rather than the shared loader. It resolves by bare
name through `roles_path = applications:operating_systems:utilities:host_roles`.

## Usage

```yaml
- name: Bootstrap every target
  hosts: all
  gather_facts: false
  become: false
  tasks:
    - name: Bootstrap this host
      ansible.builtin.include_role:
        name: 'os_bootstrap'
```

`gather_facts: false` is required. Play-level implicit gathering runs before role tasks and would
try a PowerShell module before a fresh Windows host's OpenSSH DefaultShell has been changed from
`cmd.exe`. Do not pass connection or privilege variables through `vars:` on the include; keep
those as inventory variables so the selected bootstrap role can apply its own task-scoped
transport and privilege settings.

No play-level privilege escalation is required. Each selected OS role scopes its own privilege
settings, and a dynamic role include does not replace them.

## Detection and routing

The dispatcher reads the host directly and needs no inventory hint. Both probes disable SSH TTY
allocation so their return codes remain trustworthy:

1. A POSIX `raw` probe reads the lower-case `ID` and major `VERSION_ID` from `/etc/os-release`.
2. If that probe exits nonzero, a `raw` PowerShell probe reads the Windows product type and
   build.

Windows hosts need the elevated identity the Windows roles themselves require
(`BEGIN | Require An Elevated Session Token`).

Only Windows product types 2 (domain controller) and 3 (server) proceed. The dispatcher refuses a
workstation before a server role can change its OpenSSH configuration.

The nested map in `vars/main.yml` routes Linux by distribution and major release, and Windows by
build:

- RHEL and Rocky Linux 8, 9 and 10 route to their matching `redhat_rocky_*` roles.
- Windows builds 14393, 17763, 20348 and 26100 route to Server 2016, 2019, 2022 and 2025 roles.

Server 2016 is routed; the live proof of 2026-09-26 exercised Server 2019, 2022 and 2025 only.

The probes run under `--check`, so routing can still be inspected. A fresh EL8 host cannot
complete in check mode because its selected role's Python installation remains skipped.

## Failure contract

If neither probe can read the host, the Windows probe fails with its return code and diagnostic.
Malformed probe output fails when its required lines are indexed. A Windows workstation fails the
server guard before a role is included.

An unknown distribution, release or build fails the direct nested-map lookup at
`BEGIN | Record The Selected Bootstrap Role`, and the native error names the missing key. A
mapped role that is absent or lacks an explicitly named role file is a framework defect that
`include_role` fails loudly.

## Adding an OS

Ship the new role under `operating_systems/<role>/` — an OS role converges a host, so it stays
in that namespace — with a named `tasks/bootstrap.yml` entry point and its own strict OS support
assertion. The role must also ship `defaults/main.yml`, `vars/main.yml` and `handlers/main.yml`,
because the include names them explicitly. Then add its lower-case `/etc/os-release` ID and major
release, or its Windows build, to the corresponding nested map in `vars/main.yml`. Add any new
paths to the repository-rooted
`.gitignore` allowlist and run the repository checks.

## Design invariants

1. `[INV-01]` Raw is the one primitive every target runs before bootstrap. Fresh EL8 ships Python
   3.6, below ansible-core 2.21's 3.9 floor, and fresh Windows OpenSSH serves `cmd.exe` (measured
   2026-09-26); therefore detection uses `raw`, never fact gathering.
2. `[INV-02]` The POSIX probe succeeds on a POSIX host with `/etc/os-release` and exits nonzero
   when a shell cannot source the file (POSIX.1-2024 XCU 2.19 and 2.8.1) or a Windows shell
   rejects it.
   Nonzero was measured 2026-09-26 for `cmd.exe` over fresh Server 2019 SSH, and for Windows
   PowerShell over SSH and WinRM on Server 2019, 2022 and 2025; therefore the probe uses
   `failed_when: false`, and its return code selects the Windows probe.
3. `[INV-03]` The probes run without an SSH TTY. A TTY made Windows OpenSSH report the failed
   POSIX probe as rc 0 (measured 2026-09-26); therefore the return code stays trustworthy.
4. `[INV-04]` The probes run without privilege escalation. With inventory `ansible_become: true`,
   their commands ran without sudo (measured 2026-09-26); therefore each selected role keeps its
   own privilege boundary.
5. `[INV-05]` The BEGIN stage's block variables never reach the selected role. Block variables
   on a block that encloses `include_role` reach the included role and outrank its
   `vars/main.yml` (ansible-core 2.21.4, measured 2026-09-27), so the include sits in a sibling
   PROCESS stage. The two probe registers and `__os_bootstrap_selected_role__` are host-scoped
   and stay visible to the selected role; their `__os_bootstrap_` prefix keeps them from
   colliding with its variables.
