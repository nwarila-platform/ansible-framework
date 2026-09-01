# remote_client

Site policy for reaching the private network. It holds this organization's tunnel identity and
hands it to `openvpn_client`, which does the work.

```yaml
- name: 'Place this host on the private network'
  hosts: 'all'
  roles:
    - role: 'remote_client'
```

That is the whole call for this role's own configuration: it knows the tunnel, and a consumer
states none of it. Three obligations survive, and none of them is a value this role could hold:

- **`ENV`** — the shared loader requires it, as it does for every role.
- **`aws_account_id`** — an extra-var from the pipeline that knows which account it is deploying
  into. Both bucket names template from it.
- **openvpn_client's PowerShell must be materialized.** That role tracks only `.ps1.stub`
  markers and looks up the real `Set-FileAcl.ps1` and `Set-DnsNamespaceForwarder.ps1` at four
  call sites. The sources live in this framework's own `scripts/`, so a consumer does not carry
  them — it runs the framework's `scripts/materialize-role-scripts.sh` against the composed
  checkout before the play. Without that step the lookup fails with "File not found".

Collection floors come from openvpn_client's own meta: `ansible.windows >= 3.4.0`,
`community.windows >= 2.4.0`, and `amazon.aws >= 5.0.0` on the controller.

## Why this role is allowed to default what openvpn_client refuses

`openvpn_client` states plainly that bucket names, object keys, digests and the version pin do not
belong in its defaults — "a default for them is not a default, it is one deployment's value
wearing a default's clothes." That is correct for a generic mechanism, and it offered a caller two
homes for those values: the role's defaults, wrong, or the playbook, right.

The second home does not scale. Every repository placing a host on this network restated the same
nine values, and nine values copied into N playbooks is N places for the digest to go stale.

This role is the third home. Its values *are* one deployment's, stated once, which is exactly what
makes defaulting them honest here and dishonest there. The distinction is mechanism versus policy,
not framework versus consumer.

The cost is stated rather than hidden: this is the only role in the framework that knows which
organization it belongs to. Lifting the framework into another organization means replacing this
role's defaults, and nothing else.

## What it owns

| Value | Why it is site policy |
|---|---|
| `installer` | Which client build, from the account-local mirror, at a pinned digest |
| `profile` / `profile_name` | Which tunnel. The digest is the tunnel's identity |
| `service_account` | `NT AUTHORITY\SYSTEM`, not the role's own default — see below |
| `dns` | The realm's resolvers and the host address that identifies their registration adapter |
| `proofs` | LDAP on both controllers: the tunnel is up when these answer |

Two of those are measurements rather than preferences, and both are recorded where they are set:

- **`service_account`** overrides `openvpn_client`'s `NT SERVICE\OpenVPNService`. The automatic
  service cannot configure the data-channel-offload adapter under the installer's virtual account
  — `netsh` fails and the tunnel exits — and SYSTEM completes it.
- **`dns`** is not convenience. A multi-homed host answers a name from whichever adapter replies
  first, and a cloud resolver returns NXDOMAIN for a private realm faster than a controller answers
  across a tunnel. The NRPT pin makes realm lookups deterministic; `register_address` selects the
  one adapter that holds the host's private address and assigns the same two controllers there, so
  Windows dynamic registration does not go to the cloud resolver's unsupported UPDATE path.

The pinned v2 profile is a no-rotation reissue of the same tunnel: `profile_name` remains
`aws-ec2-test`. Its hostname remote remains primary, but `resolv-retry 60` replaces the infinite
retry so an unresolvable hostname can exhaust and reach the following IP remote. That IP is a
best-effort bootstrap path when DNS is unavailable, not a replacement endpoint. The profile omits
`block-outside-dns` because its Windows local-interface filter would block DNS sourced on the
physical adapter even when the route's next hop is the VPN; the adapter and NRPT instead contain
only the two domain controllers.

## What it does not own

Every guard, mutation and proof belongs to `openvpn_client`. This role adds one assertion of its
own — that `aws_account_id` is a twelve-digit id — because its bucket names template from it, and
an empty one resolves to a bucket named `-apprepo` that fails minutes later on a name no operator
wrote.

Guest-side paths, the service name and the install location stay in `openvpn_client`'s platform
overlay. This role passes nothing that would shadow them.

## Overriding

The `remote_client:` override dict MERGES, so naming one key keeps the rest:

```yaml
- role: 'remote_client'
  vars:
    remote_client:
      profile:
        object: 'roles/remote_client/second-site.ovpn'
        sha256: '<digest>'
      profile_name: 'second-site'
```

An `openvpn_client` extra-var behaves differently: it REPLACES this role's params wholesale, so a
partial one strips the installer, the DNS pin and the proofs and the run dies on openvpn_client's
installer contract. Loud rather than silent, but it is a replacement, not a refinement.

## State

`present` places the host on the network. `clean` is a supported no-op: this role owns no state of
its own. Removing the client is `openvpn_client`'s own clean path, called directly — tearing a
host off its network is not a side effect of tidying caches. Neither path automatically resets the
adapter DNS written for registration; that persistent site state must be reverted explicitly on
the previously selected adapter during a migration or decommission.
