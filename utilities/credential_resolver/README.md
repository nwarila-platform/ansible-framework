# credential_resolver

Tries an ordered list of credential sets once. The first set that authenticates and, when
requested, is elevated and answers from a sufficiently new Windows boot becomes the host's
connection identity. Every response is reported unchanged; if no set works, the host fails with
all attempt records. Waiting and retrying belong to the calling playbook.

## Inputs

`credential_resolver_candidates` defaults to `[]`. Each set requires `name`, `connection` (`ssh`
or `winrm`), and `user`. An SSH set requires at least one of `private_key`,
`private_key_file`, or `password`. A WinRM set requires `password` and `transport` (`ntlm` or
`kerberos`); Kerberos is HTTPS-only. `port` is optional.

```yaml
credential_resolver_candidates:
  - name: 'domain-automation'
    connection: 'ssh'
    user: 'automation@example.com'
    private_key: "{{ lookup('secret', secret_url, secret_digest) }}"
```

`credential_resolver_require_elevated` defaults to `false`. When true, the winning POSIX set
must answer as uid 0 through non-interactive sudo, and a Windows set must show the High integrity
label. `credential_resolver_boot_time_after` defaults to `''`; when set, a Windows answer's boot
FILETIME must be greater than that floor.

## Outputs

The winner is published as facts under eleven names: `ansible_connection`, `ansible_user`,
`ansible_password` (always null), `ansible_ssh_password`, `ansible_winrm_password`,
`ansible_private_key`, `ansible_private_key_file`, `ansible_port`,
`ansible_winrm_transport`, `ansible_winrm_scheme`, and
`ansible_winrm_message_encryption`. A field absent from the winner is null.

Two internal facts are also published: `__credential_resolver_winner__` is the set name and
`__credential_resolver_attempts__` is the ordered list of exact `msg`, `rc`, `stdout`, and
`stderr` responses plus a separate observation.

## Caller contract

For served hosts, inventory, group, and play variables must not set the aliases
`ansible_ssh_user`, `ansible_ssh_port`, `ansible_ssh_pass`, `ansible_ssh_private_key`,
`ansible_ssh_private_key_file`, `ansible_winrm_user`, `ansible_winrm_port`, or
`ansible_winrm_pass`; among aliases, the last definition can defeat the published value.
Canonical names may remain in inventory: task variables outrank them before publication, include
parameters outrank them during an attempt, and the published facts outrank them afterward.

Inventory owns trust policy for every host: always accept SSH host keys, and set
`ansible_winrm_server_cert_validation: 'ignore'` for WinRM over HTTPS. Kerberos requires its
library in Ansible's Python, `kinit`, and realm configuration on the controller. Its set user must
be a UPN because managed `kinit` uses it as the principal. Managed `kinit` keeps a private (0600)
ticket cache in `TMPDIR` for the life of each connection and deletes it when the connection is
released. An interrupted worker can leave one behind, so a long-lived controller points `TMPDIR`
at a per-run directory and removes it. Address the target as its service principal expects,
normally its FQDN, or set `ansible_winrm_kerberos_hostname_override` when tunnelling.

Secrets in sets are lookups or vaulted values, never literals: errors can print source lines near
a rejected value. Key content requires `ANSIBLE_SSH_AGENT`; use `auto` for an ephemeral runner,
while a socket path leaves the key in that agent. `ansible_ssh_args` must not set `ControlPath`.
Key-file and password attempts also offer agent-held keys; key-content attempts use only their own
key. A passphrase-protected key file must already be in the agent because the resolver does not
set `BatchMode`.

A playbook wait submits a password set once per round. Keep `ANSIBLE_SSH_RETRIES=0`, because a
retry resubmits a refused password. Null attempt parameters hide inventory and play values, but
not extra vars, `--private-key`, `ANSIBLE_PRIVATE_KEY`, `ANSIBLE_PRIVATE_KEY_FILE`, or
`ANSIBLE_REMOTE_PORT`. A `ControlPath` in `ansible_ssh_common_args` or
`ansible_ssh_extra_args` also defeats the per-attempt fresh logon.

The resolver owns the port: a set supplies it or the connection plugin default applies. It makes
one pass and never waits or retries; a down, restarting, or rejecting host fails with every
response. Every host tries its sets exactly as supplied. An SSH password attempt submits once
(`NumberOfPasswordPrompts=1`), and correct credentials remain the credential owner's
responsibility. Never enable `ANSIBLE_DEBUG`, which prints variables.

The complete caller shape, including validation, the first-boot wait, the post-restart identity
publication and elevated/new-boot wait, and both resolver passes, is
[`tests/caller-example.yml`](tests/caller-example.yml).
