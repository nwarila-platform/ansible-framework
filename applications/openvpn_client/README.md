# openvpn_client

Installs the OpenVPN community client on Windows at a pinned version, places one pinned connection
profile where the automatic service runs it at boot with nobody signed in, holds that service on
under its own account, points a realm's DNS at the domain controllers across the tunnel, and proves
the result from the machine rather than from the installer's report.

This role exists to make a host reach a private network *before* the roles that depend on that
network run — most directly [`domain_member`](../../roles/domain_member/README.md), which cannot join a
realm it cannot resolve or reach.

## What it does

| Stage | What happens |
| --- | --- |
| BEGIN | Reads the installed client's version from the binary's own version resource, and refuses a host carrying any `.ovpn` profile this role did not declare. |
| PROCESS | Fetches the installer and the profile through the **controller**, verifies both against pinned digests, installs silently, writes the profile under a locked descriptor, holds the service on, and pins the realm's namespace to the declared servers. |
| END | Proves the client version, the profile's digest, the profile's exact permissions, the service's state/start mode/account, and that the tunnel actually reaches what the playbook declared. |

One action is decided in BEGIN — install, upgrade, or none — and a converged host reads as a column
of skips rather than a stage that vanished.

## Required inputs

```yaml
openvpn_client:
  installer:
    bucket: 'my-artifacts'
    path: 'openvpn/<version>/OpenVPN-<version>-amd64.msi'   # '<version>' is substituted
    version: '2.6.12'                                       # as the release is named
    sha256: '<64 lowercase hex>'                            # verified ON THE GUEST
  profile:
    bucket: 'my-secrets'
    object: 'openvpn/homelab.ovpn'
    sha256: '<64 lowercase hex>'                            # verified on the CONTROLLER, proven again from the file
  profile_name: 'homelab'                                   # bare name; the role appends '.ovpn'
```

### Optional

```yaml
openvpn_client:
  dns:                                    # declared together, or not at all
    domain: 'corp.example.com'            # null => no rule written, and any rule this role wrote is removed
    servers: [ '10.0.76.10', '10.0.76.11' ]   # order is the order Windows asks them in
  proofs:                                 # asked FROM THE GUEST; empty proves only the service and profile
    - { host: '10.0.76.10', port: 389 }
  proof_timeout_seconds: 120
  install:
    timeout_seconds: 600
```

## Before you run it: materialize the scripts

The role executes two PowerShell scripts that it does **not** track. Only the `.ps1.stub` build
markers naming their sources are committed; the `.ps1` copies are build artifacts the `.gitignore`
deliberately never allowlists, so a stale or hand-edited copy can never be committed.

```bash
scripts/materialize-role-scripts.sh     # in the consuming repository, before lint or run
```

| Script | What it owns |
| --- | --- |
| `Set-FileAcl.ps1` | Enforces the profile's descriptor **wholesale** — inheritance severed, exactly SYSTEM, Administrators and the service's own virtual account. |
| `Set-DnsNamespaceForwarder.ps1` | Owns every Name Resolution Policy Table rule carrying the role's marker: one rule for the declared namespace, and removal of any owned rule for a namespace no longer declared. |

Both are developed and Pester-tested once under `scripts/`, beside their `.pester.ps1` specs.

## Why the profile's permissions are enforced rather than granted

The profile holds a private key, and `config-auto` inherits the volume's grant to every user. The
native ACL modules never remove an entry they did not write, so a hand-added grant would survive
every converge. The role therefore writes the whole descriptor and END re-runs the same script in
check mode to prove the machine still reads back the same one — a would-change there is a key
readable by someone it should not be.

The file is created **empty** first, its permissions enforced, and only then is the key written into
it. Written the other way round, the key would briefly carry `config-auto`'s inherited grant.

The service account admitted by that descriptor is the MSI's own virtual account,
`NT SERVICE\OpenVPNService`. Its SID is written as a literal in `vars/windows.yml` because SDDL has
no abbreviation for a service account; the derivation is documented there and can be checked on any
host with `sc.exe showsid OpenVPNService`.

## Secrets and what pipelining does not change

The controller holds the S3 credentials and hands the files to the guest, so **the guest never
receives any reach into S3**. The profile is pulled as a string, verified, and written straight to
its destination — no task in this role writes it anywhere else.

That is not the same as "the key never touches disk on the way". With pipelining off — Ansible's
default, and what this chassis leaves in place — every module payload is staged as a file in the
target's temp directory before it executes, and the payload that writes the profile carries the key.
Enable pipelining for plays that run this role if that transit matters to you.

## Check mode

A dry run is honest about what it cannot know:

- Controller-side reads (staging, both fetches) run **for real** — they mutate nothing on the target,
  and running them is what lets a dry run prove the pinned objects exist and still match their pins.
- The install is **skipped**, explicitly: the package module cannot predict an MSI it was never
  handed. On a host whose install is pending, everything downstream that needs the client is skipped
  too, and END says so in plain words rather than failing as though something broke.
- On a host whose client is already current, every remaining task runs and predicts honestly, with
  one gap it states: the permissions of a profile that does not yet exist cannot be read.

## States

| State | Behaviour |
| --- | --- |
| `present` | Everything above. |
| `clean` | Removes any staged installer left on the guest. Deliberately does **not** uninstall the client, remove the profile, stop the service or drop the resolver policy — that is a decommission a person decides on, not something a converge does on its way past. |
| `absent` | **Not implemented.** The loader accepts the state and then fails with `OS task file not found`. Uninstalling tears down a working tunnel and, on a host that reaches its domain controllers across it, name resolution with it. |

## Collections

`ansible.windows`, `community.windows` (for `win_file_version`), and `amazon.aws` on the controller.
