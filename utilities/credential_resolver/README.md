# credential_resolver

`credential_resolver` tries caller-declared credential sets in their declared order and publishes
the first set whose fresh session works. It does not decide which credential is allowed. A set may
also require passwordless POSIX elevation, and a Windows invocation may require a boot newer than
a FILETIME floor.

The role is a utility with one entry point, `tasks/main.yml`. Candidate inputs are play variables,
never role or include parameters. The boot floor is passed on the gated second invocation exactly
as the caller contract below shows. Resolving plays must use the `linear` strategy and keep the role
tagged `always`.

## Caller contract

```yaml
roles:
  - { role: 'credential_resolver', tags: ['always'] }
  - role: 'host_readiness'
  - role: 'os_bootstrap'
  - role: 'domain_member'
  - role: 'credential_resolver'
    tags: ['always']
    when: __domain_member_boot_time__ is defined
    vars:
      credential_resolver_boot_time_after: "{{ __domain_member_boot_time__ }}"
  - role: 'host_readiness'
    when: __domain_member_boot_time__ is defined
  - role: 'domain_member'
    when: __domain_member_boot_time__ is defined
```

The play supplies `credential_resolver_candidates` and optional
`credential_resolver_require_elevated`. It supplies `ssh_trusted_principals` for `os_bootstrap`,
and the first `domain_member` call uses `restart_wait: false`. The gated resolver call proves an
identity on the new boot before readiness and membership are proved again. Later plays declare no
connection identity.

## How a resolution runs

1. Check the controller mode, command-line inputs and required controller dependencies.
2. Validate every candidate and its effective security floors before any connection traffic.
3. Capture the original connection-plumbing baseline once per host for the run.
4. Walk the candidates in caller order for each eligible round. Each attempt performs budget →
   apply → verify → probe → record.
5. Publish the first winner, print the `'<host>' works as '<name>' (<profile>, user '<user>')`
   success line, and reset the connection only when that winner uses SSH.

On a re-run against a converged host, the first probe wins, the gated second invocation does not
run because `__domain_member_boot_time__` is not published, and the play reports `changed=0`.

Credential acquisition is the sole exception to the ordinary utility boundary: this utility may
apply caller-declared sets in caller order. It is the only role that writes connection credentials,
writes each group as its rendered value or the plugin's reviewed neutral, and never changes the
play's escalation switch.

Controller debug mode is refused before a candidate value is templated. Extra variables on anything
the resolver writes, connection/elevation password prompts and files, and `--private-key` are also
refused. When a set carries a become block, extra variables on `ansible_become` and on the accepted
become plugins' variables are refused too; without one, a fleet's own become extra variables (for
example a runas password) stay allowed. Later plays declare no connection identity: the winning
non-cacheable facts remain the host's identity for the run. Invoke the role again when a restart can
change which set works.
Inventory and play variables use canonical connection names and carry plumbing only; every
credential and identity belongs in a declared set. Do not enable a persistent fact cache on a
resolving controller.

## Inputs and results

| Variable | Default | Contract |
|---|---:|---|
| `credential_resolver_candidates` | `[]` | Required ordered list of sets. |
| `credential_resolver_rounds` | `60` | Maximum rounds. |
| `credential_resolver_pause_seconds` | `15` | Pause only between two eligible, winnerless rounds. |
| `credential_resolver_require_elevated` | `false` | Require a High/Administrators Windows token or POSIX uid 0. |
| `credential_resolver_boot_time_after` | `''` | Windows boot FILETIME that the answer must exceed. |
| `credential_resolver_password_budget` | `2` | Login-password submissions permitted per canonical account id during the run. |

A set is `{name, profile, vars, attempts?, account?, certificate_file?, become?}`. `name` is unique,
non-empty and non-secret. `vars` accepts only the canonical variables listed by its profile.
`attempts` defaults to one for a login-password set and every round otherwise. `account` is required
when the set submits a login password.

Every spelling of one principal on every host must use the same canonical `account` id. The budget
adds all hosts' prior tallies, reserves current-batch hosts in inventory order, and charges the
profile's measured cost: one for `ssh_password`, `winrm_ntlm`, `winrm_basic`, and managed
`winrm_kerberos`; zero for the accepted key, certificate, cache, local and AWS forms. An
authenticated probe refunds only its own booking. Tallies survive a second role invocation in the
same run. The default budget of two stays below a lockout threshold of three; it cannot account for
failures outside this run or a dishonest `account` partition.

Success publishes `__credential_resolver_selected__` and `__credential_resolver_profile__`. Every
key an attempt writes stays at `set_fact` precedence for the rest of the run:

- every alias of the attempt plugin's identity, secret and selector groups;
- `ansible_connection`, by short name for a builtin plugin (`ssh`, `winrm`, `psrp`, `local`) as
  `host_readiness` and `os_bootstrap` compare it, and `ansible_ssh_args` for SSH;
- every pin key of the plugin (`ansible_ssh_password_mechanism`, `ansible_ssh_retries`,
  `ansible_winrm_transport`, `ansible_psrp_auth`): the profile's value, else the baseline;
- plumbing that any set names: the set's value, else the baseline;
- the play-context names the plugin reads: `ansible_ssh_pass: ''` for WinRM and PSRP, and
  `ansible_ssh_user` (the set's user, else `null`) for jail, iocage and qubes.

The winner's attempt rewrites every key of its own plugin, so a losing attempt of the same plugin
leaves nothing behind. A losing attempt of another plugin leaves the keys only it wrote in place
(for example `ansible_winrm_pass`, `ansible_winrm_transport` or
`ansible_aws_ssm_secret_access_key`). A later task or block variable of any of these names is
ignored for the run; a different value needs a role or include parameter. No become setting is ever
written, and the switch never is: a later task's or block's own escalation settings stay its own.
Failure names each set, rounds tried and its last category; remote message text never controls or
stops the walk.

## Connection profile examples

Each fragment below is one independent candidate example. Keep only profiles suitable for that
host's OS.

```yaml
# ssh_publickey: OpenSSH-format key content; ANSIBLE_SSH_AGENT must not be "none", and a
# passphrase needs bcrypt in the controller's Python.
- name: 'ssh-content'
  profile: 'ssh_publickey'
  vars:
    ansible_user: 'deployer'
    ansible_private_key: "{{ lookup('file', '/secure/id_ed25519') }}"
    ansible_private_key_passphrase: "{{ vault_key_passphrase }}"

# ssh_publickey: unencrypted key file, agent-held key named by its .pub, or FIDO key.
- name: 'ssh-file-or-agent'
  profile: 'ssh_publickey'
  vars:
    ansible_user: 'deployer'
    ansible_private_key_file: '/secure/id_ed25519.pub'
  certificate_file: '/secure/id_ed25519-cert.pub'

# ssh_publickey: PKCS#11 requires the token key's public-key file and its PIN.
- name: 'ssh-pkcs11'
  profile: 'ssh_publickey'
  vars:
    ansible_user: 'deployer'
    ansible_private_key_file: '/secure/token-key.pub'
    ansible_ssh_pkcs11_provider: '/usr/lib/pkcs11/provider.so'
    ansible_password: "{{ vault_token_pin }}"

- name: 'ssh-password'
  profile: 'ssh_password'
  account: 'realm/deployer'
  vars:
    ansible_user: 'deployer'
    ansible_password: "{{ vault_login_password }}"

- name: 'ssh-gssapi'
  profile: 'ssh_gssapi'
  vars: {ansible_user: 'deployer@REALM.EXAMPLE'}

- name: 'ssh-hostbased'
  profile: 'ssh_hostbased'
  vars: {ansible_user: 'deployer'}

- name: 'winrm-ntlm'
  profile: 'winrm_ntlm'
  account: 'realm/windows-deployer'
  vars:
    ansible_host: 'windows.example'
    ansible_port: 5985
    ansible_user: 'REALM\windows-deployer'
    ansible_password: "{{ vault_login_password }}"
    ansible_winrm_scheme: 'http'
    ansible_winrm_message_encryption: 'always'

- name: 'winrm-kerberos-managed'
  profile: 'winrm_kerberos'
  account: 'realm/windows-deployer'
  vars:
    ansible_host: 'windows.example'
    ansible_user: 'windows-deployer@REALM.EXAMPLE'
    ansible_password: "{{ vault_login_password }}"

- name: 'winrm-kerberos-cache'
  profile: 'winrm_kerberos'
  vars:
    ansible_host: 'windows.example'
    ansible_user: 'windows-deployer@REALM.EXAMPLE'
    ansible_winrm_kinit_mode: 'manual'

- name: 'winrm-basic'
  profile: 'winrm_basic'
  account: 'windows/local-service'
  vars:
    ansible_host: 'windows.example'
    ansible_user: 'local-service'
    ansible_password: "{{ vault_login_password }}"
    ansible_winrm_scheme: 'https'

- name: 'winrm-certificate'
  profile: 'winrm_certificate'
  vars:
    ansible_host: 'windows.example'
    ansible_winrm_scheme: 'https'
    ansible_winrm_cert_pem: '/secure/client.pem'
    ansible_winrm_cert_key_pem: '/secure/client.key'

- name: 'psrp-kerberos'
  profile: 'psrp_kerberos'
  vars:
    ansible_host: 'windows.example'
    ansible_user: 'windows-deployer@REALM.EXAMPLE'
    ansible_psrp_protocol: 'https'

- name: 'psrp-certificate'
  profile: 'psrp_certificate'
  vars:
    ansible_host: 'windows.example'
    ansible_psrp_protocol: 'https'
    ansible_psrp_certificate_pem: '/secure/client.pem'
    ansible_psrp_certificate_key_pem: '/secure/client.key'

- name: 'ssm-ambient'
  profile: 'aws_ssm_ambient'
  vars:
    ansible_aws_ssm_instance_id: 'i-example'
    ansible_aws_ssm_region: 'us-east-1'
    ansible_aws_ssm_bucket_name: 'transfer-bucket'

- name: 'ssm-profile'
  profile: 'aws_ssm_profile'
  vars:
    ansible_aws_ssm_instance_id: 'i-example'
    ansible_aws_ssm_region: 'us-east-1'
    ansible_aws_ssm_bucket_name: 'transfer-bucket'
    ansible_aws_ssm_profile: 'deployment'

- name: 'ssm-static'
  profile: 'aws_ssm_static'
  vars:
    ansible_aws_ssm_instance_id: 'i-example'
    ansible_aws_ssm_region: 'us-east-1'
    ansible_aws_ssm_bucket_name: 'transfer-bucket'
    ansible_aws_ssm_access_key_id: "{{ vault_access_key_id }}"
    ansible_aws_ssm_secret_access_key: "{{ vault_secret_access_key }}"
    ansible_aws_ssm_session_token: "{{ vault_session_token }}"

- name: 'controller-local'
  profile: 'local'
  vars: {}

- name: 'local-chroot'
  profile: 'chroot'
  vars: {ansible_host: '/srv/chroot'}

- name: 'iocage-jail'
  profile: 'iocage'
  vars: {ansible_host: 'jail-name', ansible_user: 'root'}

- name: 'freebsd-jail'
  profile: 'jail'
  vars: {ansible_host: 'jail-name', ansible_user: 'root'}

- name: 'lxc-container'
  profile: 'lxc'
  vars: {ansible_host: 'container-name'}

- name: 'lxd-instance'
  profile: 'lxd'
  vars: {ansible_host: 'instance-name', ansible_lxd_remote: 'local'}

- name: 'qubes-vm'
  profile: 'qubes'
  vars: {ansible_host: 'work-vm', ansible_user: 'user'}

- name: 'salt-minion'
  profile: 'saltstack'
  vars: {}
```

AWS ambient mode deliberately leaves every AWS credential option `null` so the default chain can
run. Profile and static modes write every other AWS credential option as `''`. Static mode is
refused while `AWS_PROFILE` or `AWS_DEFAULT_PROFILE` is set. When ambient mode sees both an
environment profile and environment access key, the plugin's own check rejects that attempt before
traffic and the resolver continues the walk. The role locally constructs SSM and S3 clients with
placeholder client credentials and refuses any effective non-HTTPS endpoint, including
service/global environment and shared-configuration endpoints. It never contacts AWS during
preflight.

## Become profiles

Become is passwordless, POSIX-only and always verified with `id -u == 0`. None of it is written as
a fact. The probe of a set with a block carries, as its own task variables, the switch, the pinned
method and executable, and every alias of the plugin's user, flags and password groups: the block's
user and flags, else the profile defaults, and `''` for every password. A fact, an `include_vars`
file, a role or include parameter, or an extra variable that overrides any of them fails the host
before traffic. Plugin-specific options (`sudo_chdir`, `prompt_l10n`, `wrap_exe`) are plumbing and
never written. A block proves that the set can elevate that way; later escalation is the play's own
configuration.

```yaml
# sudo: flags are restricted to argument-less options and must include -n.
become: {profile: 'sudo', user: 'root', flags: '-H -S -n'}

# doas: no flags field; the plugin supplies -n.
become: {profile: 'doas', user: 'root'}

# pfexec: neither user nor flags is accepted.
become: {profile: 'pfexec'}
```

`sudo` users must match `^[A-Za-z0-9_][A-Za-z0-9_.@-]*$`; the same shell-inert user rule applies to
`doas`. Passwords and an `exe` field are refused.

## Security floors, prerequisites and refused forms

The SSH profiles prepend their scalar pins to `ansible_ssh_args`, starting with `-F /dev/null`, then
append the original configured `ssh_args`. No user or system `ssh_config` is read after selection;
put required non-identity options in `ansible_ssh_common_args`. Identity options, `ControlPath` and
`-S` in any effective argument string are refused: a control path there would let a probe reuse
another connection. Non-PKCS#11 key, GSSAPI and hostbased attempts use `BatchMode=yes`;
password and PKCS#11 attempts explicitly use `BatchMode=no`. Every probe disables connection
sharing. An encrypted private-key file fails fast because core cannot supply its passphrase: give
OpenSSH-format key content with `ansible_private_key_passphrase` (which needs `bcrypt`), or load the
key in an agent. Key content must be in the OpenSSH format that `ssh-keygen` writes by default: core
loads no other, so PEM and PKCS#8 content is refused.

WinRM NTLM and Kerberos over HTTP require `message_encryption: always`; Basic and certificate
profiles require HTTPS. PSRP Kerberos over HTTP has the same encryption requirement, and PSRP
certificate requires HTTPS. Server identity is accepted for now; these are encryption floors, not
a server-trust guarantee.

Prerequisites are checked before traffic:

- SSH key content needs configured SSH-agent support, and a passphrase also needs `bcrypt` in the
  controller's own Python; GSSAPI needs a valid controller ticket; hostbased needs `ssh-keysign`
  and `EnableSSHKeysign yes` in global `/etc/ssh/ssh_config`.
- WinRM needs `pywinrm`; NTLM needs its NTLM library; Kerberos needs its Python backend and
  `kinit`.
- PSRP needs `pypsrp`; Kerberos also needs a GSSAPI or krb5 backend.
- AWS SSM needs `boto3`, `session-manager-plugin`, a region and transfer bucket.
- Local community transports need their controller binary or Python library: `chroot`; `jls` and
  `jexec` for jail, and `iocage` as well for iocage; the LXC bindings; the `lxc` client for LXD;
  `qvm-run`; or Salt. Jail and iocage also need a root controller.

Jail, iocage and chroot inspect their target whenever a task constructs their connection, so a
missing target (for jail and iocage, also a stopped one) ends that host's resolution at that set's
attempt. The other local transports report a missing target at the probe, and the walk continues.

Refused connection forms are SSH keyboard-interactive, WinRM CredSSP, every PSRP password form
(`basic`, `ntlm`, `negotiate`, `credssp`, or Kerberos with a password), and encrypted PSRP
certificate keys. Their login-submission bounds or secret handling are not established here.
Refused become forms are every become password and `runas`, `su`, `dzdo`, `ksu`, `machinectl`,
`pbrun`, `pmrun`, `sesu`, and `sudosu`; each either prompts, has unproven non-interactive behavior,
depends on target PAM behavior, or cannot be verified by the raw probe. The secret-less forms of
these mechanisms remain: certificates, unencrypted keys, Kerberos caches and passwordless
escalation. The local transports `funcd` and `zone` are also refused, because community.general
7.5.9 breaks both: ansible-core cannot load its `funcd` plugin, and `zone` fails while listing
zones. A fixed collection would enable them.

## Elevation, boot floor and trust boundaries

Windows elevation means the fresh login token contains both `S-1-16-12288` and
`S-1-5-32-544`. POSIX elevation means `id -u` answers `0`, either directly or through the set's
accepted become profile. A boot floor is Windows-only and compares
`LastBootUpTime.ToFileTimeUtc()`.

The floors guard deployment mistakes, not an author who deliberately subverts their own inputs
with a non-deterministic identity parameter. A probe reports what the candidate account's own
session reports; an account with a hostile environment can misreport itself. Every candidate must
therefore be an account the caller controls. Argument strings, proxy commands, proxy URLs,
executables, identity paths, user names, AWS profile names and other plumbing can appear in core
verbose output or process arguments and must never carry a secret.

With controller debug refused, caller-supplied passwords, PINs, key content, passphrases, AWS secret
keys and session tokens are protected by `no_log`, never cached, and never placed in resolver
output or argv. They remain in `hostvars` for the run. Two derived surfaces are outside that
guarantee. Managed WinRM Kerberos writes a private (0600) credential-cache file in the controller's
`TMPDIR` for each managed-Kerberos connection: the probe's, and one per later task once such a set
is published. The plugin never closes that file and the task's worker exits without cleanup, so the
file persists after the run whenever the worker still references the connection at exit, as it does
for any task with a templated `when`, the probe included. Point `TMPDIR` at a per-run directory and
remove it after the run. The SSM plugin places the session token returned by AWS in its child argv
and shows that argv at `-vvvv`.

Two further surfaces belong to the plugins after publication, not to the resolver. An
`aws_ssm_static` winner's own session token signs the S3 presigned URLs inside the remote transfer
command of later file transfers, and the plugin prints that command in full at `-vvvvv`. A
key-content set's private key is added to the configured SSH agent with no lifetime; with an
external agent (`ANSIBLE_SSH_AGENT` naming a socket) it outlives the run.
