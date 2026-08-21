# `domain_member` role

Joins a host to an Active Directory realm. **One contract, two platforms.** The caller declares the
realm, the account permitted to place the machine in it, where that account's password lives, and
three optional knobs. Every key means the same thing and produces the same end state on both
platforms.

The RedHat path hands that contract to `redhat.rhel_system_roles.ad_integration` — the vendor's own
implementation of the join, shipped in the RHEL mirror, which is the only source an offline
controller has. The Windows path performs the same work against `microsoft.ad` and the registry,
because Windows has no equivalent system role. Read
[`present_redhat.yml`](tasks/present_redhat.yml) and [`present_windows.yml`](tasks/present_windows.yml)
side by side and the regions line up.

## Configuration

Role overrides go in the `domain_member` dictionary and merge through the shared loader as
`defaults` → OS overlay (`vars/redhat.yml`, `vars/windows.yml`) → the `domain_member:` override
dict. Tasks read the merged result as `domain_member_running`.

| Key | Required | Default | Purpose |
|---|---|---|---|
| `realm` | Yes | `''` | DNS name of the realm, e.g. `corp.example.com`. Not the NetBIOS short name. |
| `user` | Yes | `''` | Account permitted to create or reuse this machine's computer object. |
| `password.bucket` | Yes | `''` | S3 bucket holding that account's password. |
| `password.object` | Yes | `''` | Object key of the password. |
| `password.sha256` | Yes | `''` | Lowercase 64-character digest, verified before the value is used. |
| `computer_ou` | No | `null` | LDAP DN of the OU a **new** computer object is created in. |
| `force_rejoin` | No | `false` | Leave the current realm and join again from scratch. |
| `timesync_source` | No | `null` | Host or address to synchronise the clock with. |

`ENV` is required by the loader — it selects the environment-specific overlay layer
(`vars/<family>_<ENV>.yml`), none of which this role ships — so any value matching the loader's
`[A-Za-z0-9_-]` shape works today.
`state` accepts `present` and `clean`; `absent` is deliberately not implemented and fails at task
resolution rather than silently doing nothing.

The credential is fetched, not declared: the role pulls the object through the **controller**,
verifies it against `password.sha256`, and hands the value to the join. The guest is never given
cloud credentials, and no task in this role writes the value to a file.

That is not the same as "it never touches disk": with pipelining off — Ansible's default, which
this chassis keeps — Ansible itself stages every module payload as a file in the target's temp
directory before executing it, and for the join that payload carries the password. Enable
pipelining for plays running this role if that transit matters to you.

The fetch runs **on the controller, with the controller's own ambient AWS credentials** — the role
never authenticates to S3 itself. It is also `no_log`, so a failure prints the censored-output
notice rather than a reason: check controller credentials, region, and `boto3` first. Note that
`ignore_nonexistent_bucket: true` means a missing bucket surfaces as an object-level error.

Delegated tasks resolve connection variables from the **delegate**, not the target, so site
`group_vars` that set WinRM/SSH connection vars on `all` will follow the delegation onto localhost
and break it. A Windows play therefore needs an explicit `localhost` inventory host with
`ansible_connection: local` and `ansible_python_interpreter: "{{ ansible_playbook_python }}"`.

```yaml
# inventory must carry the controller host the fetch delegates to:
#   localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"
- hosts: 'domain_members'
  roles:
    - role: 'domain_member'
      vars:
        domain_member:
          realm: 'corp.example.com'
          user: 'svc-join@corp.example.com'
          password:
            bucket: '123456789012-ansible'
            object: 'secrets/ad/svc-join'
            sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
          computer_ou: 'OU=Servers,OU=Prod,DC=corp,DC=example,DC=com'
          timesync_source: 'dc01.corp.example.com'
```

## How one contract becomes two implementations

| Contract key | RedHat | Windows |
|---|---|---|
| `realm` | `ad_integration_realm` | `dns_domain_name` |
| `user` | `ad_integration_user` | `domain_admin_user` |
| password (fetched) | `ad_integration_password` | `domain_admin_password` |
| `computer_ou` | `ad_integration_computer_ou` → `computer-ou` in `realmd.conf` | `domain_ou_path` |
| `force_rejoin` | `ad_integration_force_rejoin` → `realm leave` + `realm join` | unjoin to workgroup, restart, join |
| `timesync_source` | `ad_integration_manage_timesync` + the `timesync` role | `W32Time` `NtpServer` + `Type`, service restarted |
| machine-account posture | `sssd_custom_settings` in `vars/redhat.yml` | `secure_channel` in `vars/windows.yml` |

## Security posture

The role holds only what is **join-relevant**. The secure channel *is* the membership's channel,
the machine account password *is* the membership credential, Kerberos encryption types are how the
membership authenticates, and time is what Kerberos requires. General system hardening — FIPS
itself, SMB signing, password policy — belongs to the OS role, not here.

- **Machine account rotation** is declared on both platforms rather than inherited: 30 days, with
  renewal enabled. RedHat writes SSSD's `ad_maximum_machine_account_password_age` and
  `ad_machine_account_password_renewal_opts`; Windows writes Netlogon's `MaximumPasswordAge` and
  `DisablePasswordChange`.
- **Secure channel** on Windows: `RequireSignOrSeal`, `SealSecureChannel`, `SignSecureChannel`,
  `RequireStrongKey`. On RedHat the equivalent sealing is what SSSD's AD provider does by default;
  `krb5_validate` is declared so a spoofed KDC fails instead of passing.
- **Kerberos encryption excludes DES and RC4**, and nothing in the contract can re-admit them.
  Windows writes the bitmask DISA's Windows Server 2022 STIG **WN22-SO-000290 (V-254473)** requires,
  as a literal in the task rather than a config key. RedHat holds the same line by leaving the
  system-wide crypto policy alone — which is *abstention*, not enforcement: a host someone already
  moved to `LEGACY` converges green with RC4 available, because the role never reads the policy
  back. If you need that enforced, the crypto policy belongs to the OS hardening role. The reasoning
  and the benchmark citation live beside the code in
  [`present_windows.yml`](tasks/present_windows.yml) and [`present_redhat.yml`](tasks/present_redhat.yml).

Because the role never touches the system-wide crypto policy, a host in FIPS mode stays in FIPS.
The role neither reads nor sets FIPS state.

## Refusals and boundaries

- **A host already joined to a different realm is refused**, before anything is written — unless
  `force_rejoin` says otherwise. Joining it elsewhere abandons its computer object and every access
  granted through that object's group memberships.
- **`force_rejoin` on Windows requires a local connection account.** The machine is unjoined and
  restarted before it rejoins, and a domain account cannot authenticate to a host that is, at that
  moment, not in the domain.
- **Renaming the machine is not offered.** A rename is a separate change with its own consequences.
- **An existing computer object is never moved between OUs.** `computer_ou` applies at creation.
- **Leaving a domain is not implemented** as a state. `state: clean` is a supported no-op on both
  platforms; the role stages nothing on the guest.
- **Check mode cannot complete a join**, so END fails on a host that is not already a member, with
  a message that says so rather than a postcondition that looks broken — on RedHat the system-role
  include is skipped outright under `--check`, because it cannot run honestly on a host that has no
  realm client yet. The password fetch and its
  digest check *do* run under `--check` — they are reads, and `s3_object` returns early in check
  mode without the `contents` field the digest needs — so a dry run still proves the secret object
  exists and matches its pin.

## What END proves

Both platforms prove the result from the machine, not from the join tool's report, and both prove
two separate things:

1. **Membership** — `realm list` on RedHat; on Windows the facts module's `windows_domain`
   subset, which calls `DsRoleGetPrimaryDomainInformation`.
2. **That the machine account credential actually works** — `adcli testjoin` on RedHat,
   `Test-ComputerSecureChannel` on Windows. A configured realm is not a working membership: the
   computer object can be deleted or reset in the directory while every local answer still looks
   correct. This is the check that tells an operator they need `force_rejoin`.
