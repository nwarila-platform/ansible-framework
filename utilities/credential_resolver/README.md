# `credential_resolver` role

Selects the ordered credential sets matching the inventory-declared transport. It can wait for a
first-booting host, obtain an EC2 launch password on the controller, or wait for a replacement
identity on a newer Windows boot. The first selected set that authenticates and satisfies the
requested elevation and boot floor becomes the host's connection identity.

## Inputs

`credential_resolver_candidates` defaults to `[]`. Each set requires `name`, `connection` (`ssh`
or `winrm`), and `user`. The role records the host's inventory-declared transport on its first call
and ignores sets for the other transport. An SSH set requires at least one of `private_key`,
`private_key_file`, `password`, or `launch_password`. A WinRM set requires exactly one of `password`
or `launch_password` and a `transport` of `ntlm` or `kerberos`; Kerberos is HTTPS-only. `port` is
optional. A `launch_password` mapping contains exactly `instance_id`, `region`, and
`private_key_file`, each non-empty, and cannot accompany `password`.

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
FILETIME must be greater than that floor. `credential_resolver_wait_rounds` defaults to `0`, which
preserves a single pass with no wait. `credential_resolver_wait_pause_seconds` defaults to `10`.

## Outputs

The winner is published as facts under eleven names: `ansible_connection`, `ansible_user`,
`ansible_password` (always null), `ansible_ssh_password`, `ansible_winrm_password`,
`ansible_private_key`, `ansible_private_key_file`, `ansible_port`,
`ansible_winrm_transport`, `ansible_winrm_scheme`, and
`ansible_winrm_message_encryption`. A field absent from the winner is null.

Two internal facts are also published: `__credential_resolver_winner__` is the set name and
`__credential_resolver_attempts__` is the ordered list of exact answers plus a separate
observation. A POSIX record keeps the Windows answer and the POSIX answer under `posix`. Nothing
about the OS is published.

## Caller contract

For served hosts, inventory, group, and play variables must not set the aliases
`ansible_ssh_user`, `ansible_ssh_port`, `ansible_ssh_pass`, `ansible_ssh_private_key`,
`ansible_ssh_private_key_file`, `ansible_winrm_user`, `ansible_winrm_port`, or
`ansible_winrm_pass`; among aliases, the last definition can defeat the published value.
Canonical names may remain in inventory: task variables outrank them before publication, include
parameters outrank them during an attempt, and the published facts outrank them afterward.

Inventory owns trust policy and declares the connection transport for every host: always accept SSH
host keys, and set
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

The first-boot wait submits each selected set once per round. It rotates identities correctly only
before any connection fact has been published in the run; task variables cannot displace those
facts. Keep `ANSIBLE_SSH_RETRIES=0`, because a retry resubmits a refused password. Null attempt
parameters hide inventory and play values, but not extra vars, `--private-key`,
`ANSIBLE_PRIVATE_KEY`, `ANSIBLE_PRIVATE_KEY_FILE`, or `ANSIBLE_REMOTE_PORT`. A `ControlPath` in
`ansible_ssh_common_args` or `ansible_ssh_extra_args` also defeats the per-attempt fresh logon.

The resolver owns the port: a set supplies it or the connection plugin default applies. A WinRM
set's port also selects its scheme and message encryption: 5985 is HTTP with encryption required
(`always`); every other port, including the plugin default 5986, is HTTPS with `auto`. The
resolver writes both values, so inventory, group, or play values of `ansible_winrm_scheme` or
`ansible_winrm_message_encryption` do not change its sets. Extra vars outrank these values,
as they outrank every value. An `ansible_become` from extra vars, an earlier `set_fact`, or a
variable on the outer role inclusion -- all higher-precedence sources -- outranks the task
variables that set escalation for the questions. An SSH password attempt submits once
(`NumberOfPasswordPrompts=1`), and correct credentials remain the credential owner's responsibility.
Never enable `ANSIBLE_DEBUG`, which prints variables.

When a boot floor and positive wait count are supplied, the role publishes the first selected set
before waiting. On SSH it makes exactly the declared number of attempts with a pause between attempts;
each attempt's own duration is additional. On WinRM it delays 60 seconds, then permits new attempts to
start during a `rounds × pause` retry window. A final in-flight attempt and the sleep after it are not
clamped, so there is no hard wall-clock ceiling. The first set is an ordering contract: a later
post-restart candidate cannot rescue a bad first one.

For each selected `launch_password`, the role delegates the AWS waiter and decrypt command to
`localhost`. The waiter remains visible because it returns no plaintext. Decryption is masked, and a
sanitized failure names only the set, return code, and module message.

No inventory value names the OS. Every set is first asked the Windows question through
`powershell.exe`; an answer of 127, the POSIX status for command not found, makes the resolver ask
`id -u`. A working Linux credential therefore makes two logons, while a refused credential makes
one. This reading serves only the resolver's elevation and boot-floor checks and is not published;
`os_bootstrap` reads the OS independently. Every question runs without a tty because Windows
OpenSSH can otherwise report a failed command as successful. A Linux host with `powershell.exe`
on its `PATH` reads as Windows.

The roles-only caller shape is [`tests/caller-example.yml`](tests/caller-example.yml). A later
post-restart call supplies only the identities intended for that transition; omitting launch-password
sets also guarantees that call performs no AWS command.
