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

No play-level privilege escalation is required. `RedHat_Rocky_8` runs only its main bootstrap
block with `become: true`; `Windows_Server_2025` explicitly disables become. A dynamic role
include does not replace those settings.

## Detection and routing

Detection uses the first available signal in this order:

1. An already-populated `ansible_facts.os_family`.
2. The `aws_ec2` inventory host variable `platform` when its value is `Windows`. EC2 omits this
   variable for Linux, so absence is never treated as a Linux signal.
3. An `ansible_shell_type` value of `powershell`.
4. An `ansible_connection` value of `winrm` or `psrp`.
5. A narrow `ansible.builtin.setup` fact gather as the last resort.

The first four checks are controller-side and open no target connection. Every optional value is
handled with an explicit empty default. The fallback is suitable for Linux and for a connection
already configured to execute its platform's modules. It cannot make an unlabelled fresh Windows
SSH host safe: inventory for that host must supply either `platform: Windows` or a Windows
connection hint so dispatch reaches `Windows_Server_2025` before any module runs.

Routing is by OS family:

- `RedHat` routes to `RedHat_Rocky_8`.
- `Windows` routes to `Windows_Server_2025`.

The dispatcher does not validate a distribution, version, Windows product type, or build.
Each selected bootstrap role retains that responsibility and fails if the target is unsupported.
For example, another RedHat-family release is intentionally routed to `RedHat_Rocky_8`, whose
strict RHEL/Rocky 8 assertion rejects it.

## Failure contract

Dispatch never skips an unknown route. Failure messages report the detected OS and the signal
used, and a failed or empty fallback fact gather is converted to the same loud detection failure.

The dispatcher owns detection and routing, and nothing else. It does not check that the mapped
role exists or ships an entry point, because a map naming a role this framework does not have is
a framework defect and `include_role` already fails the play on it. The two failures read
differently: an absent role is reported by name against every path searched, while a role that
exists without `tasks/bootstrap.yml` reports only `Could not find specified file in role:
tasks/bootstrap` and names neither the role nor the detected OS -- the role is recoverable from
the preceding `Resolve Bootstrap Role` task, which prints it under `-v`.

## Adding an OS

Ship the new role under `operating_systems/<role>/` — an OS role converges a host, so it stays
in that namespace — with a named `tasks/bootstrap.yml` entry point and its own strict OS support
assertion. Then extend
`os_bootstrap_role_map` in `vars/main.yml`. Add the new paths to the repository-rooted
`.gitignore` allowlist and run the repository checks.

### A second release of a family already in the map

Detection yields an OS FAMILY, and on Windows it resolves before facts are available, so the map
holds one role per family and cannot tell two releases apart. Adding `Windows_Server_2022`
beside `Windows_Server_2025` therefore does NOT mean editing the map: pointing `Windows` at
either one routes every Windows host to it and fails the other release's support assertion.

Name the role in the INVENTORY instead. `os_bootstrap_role`, when set on a host, wins over the
map:

```yaml
compose:
  os_bootstrap_role: >-
    (aws_ec2_tags.Function | default('', true) == 'workstation')
    | ternary('Windows_Server_2022', '')
```

A host variable is the only override that arrives before detection runs and does not become a
role parameter — callers of this role are told to pass it none, because a role parameter
outranks the connection scoping the pre-flip stage depends on. An empty value falls through to
the map, so hosts that say nothing keep the default.
