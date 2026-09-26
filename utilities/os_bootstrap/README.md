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
2. If that probe fails, a `raw` PowerShell probe reads the Windows product type and build. The
   ignored POSIX failure is expected on every Windows host.

Only Windows product types 2 (domain controller) and 3 (server) proceed. The dispatcher refuses a
workstation before a server role can change its OpenSSH configuration.

The nested map in `vars/main.yml` routes Linux by distribution and major release, and Windows by
build:

- RHEL and Rocky Linux 8, 9 and 10 route to their matching `redhat_rocky_*` roles.
- Windows builds 14393, 17763, 20348 and 26100 route to Server 2016, 2019, 2022 and 2025 roles.

Server 2016 is routed but has not been live-proven by this change.

The probes run under `--check`, so routing can still be inspected. A fresh EL8 host cannot
complete in check mode because its selected role's Python installation remains skipped.

## Failure contract

If neither probe can read the host, the Windows probe fails with its return code and diagnostic.
Malformed probe output fails when its required lines are indexed. A Windows workstation fails the
server guard before a role is included.

An unknown distribution, release or build fails the direct nested-map lookup while finalizing the
role include, and the native error names the missing key. A mapped role that is absent or lacks
`tasks/bootstrap.yml` is a framework defect that `include_role` also fails loudly.

## Adding an OS

Ship the new role under `operating_systems/<role>/` — an OS role converges a host, so it stays
in that namespace — with a named `tasks/bootstrap.yml` entry point and its own strict OS support
assertion. Then add its lower-case `/etc/os-release` ID and major release, or its Windows build,
to the corresponding nested map in `vars/main.yml`. Add any new paths to the repository-rooted
`.gitignore` allowlist and run the repository checks.
