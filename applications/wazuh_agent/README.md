# wazuh_agent

Installs and enrolls the **Wazuh agent** on endpoint hosts.

This role is for monitored endpoints only. Do not run it on the manager host: the role
compares `wazuh_agent.manager.host` with the endpoint's `private_ip_address`, `ansible_host`,
and `inventory_hostname`, and refuses to install the standalone agent package when one
matches because both packages own `/var/ossec`.

## What this role does NOT consume

Unlike the central indexer/server/dashboard roles, **this role does not pull the
`wazuh-offline.tar.gz` bundle**. It downloads exactly one file from S3:

```
s3://<bucket>/applications/wazuh-agent/wazuh-agent-<version>-1.x86_64.rpm
```

It verifies the RPM against an operator-supplied SHA256 in the per-env overlay, imports
the repo-owned Wazuh RPM signing key into the target rpmdb, and dnf-installs it.
Decoupling the agent from the central bundle lets the two ship on independent cadences.

## Required inputs

| Variable | Type | Description |
|---|---|---|
| `ENV` | str | Environment selector (`dev`, `test`, or `prod`). Used by overlay loader. |
| `wazuh_agent.state` | str | `present` (default) or `clean`. |
| `wazuh_agent.manager.host` | str | Required and non-empty for `state=present`. Set explicitly to the manager's routable IP address or DNS name; the shared role does not infer consumer inventory topology. |
| `wazuh_agent.agent_ip` | str | Optional explicit endpoint IPv4 for `agent-auth -I`. Required when `ansible_host` is a DNS name instead of an IPv4 address. |

The normal role entry point supports both Linux and Windows hosts in the same play. It gathers
the platform facts needed for per-host dispatch, uses POSIX package and staging tasks only on
non-Windows hosts, and selects the appropriate RPM or MSI validation contract.

## Agent-name uniqueness scope

The role rejects duplicate effective `wazuh_agent.agent_name` values among endpoints targeted by
the current play. It derives that host set from `ansible_play_hosts_all`, not inventory group
names, so the check is independent of a consumer's inventory topology and covers Linux and
Windows endpoints in the supported mixed-play shape.

This detection is intentionally play-scoped. It cannot see an endpoint that a consumer deploys
in a separate play, so consumers that split agent deployment across plays must enforce global
agent-name uniqueness themselves. Keeping all endpoint deployment in one mixed play lets the
normal Windows-safe loader provide the complete host set to this guard.

`tasks_from: main_windows` remains as a deprecated forwarding alias for the shared loader so existing
callers receive the same behavior. New callers should use the normal role entry point. The alias
will be removed in loader v4.0.0.

## Single-manager scope

This role deliberately accepts and renders exactly one manager endpoint. This is a limitation of
the role, not of Wazuh: Wazuh supports multiple `<server>` blocks for agent failover.

Adding failover later also requires correcting the existing manager-block replacement logic. Its
non-greedy `(?ms)^(\s*<client>\s*)<server>.*?</server>\s*` pattern rewrites only the first
`<server>` block in a configuration that already contains several and leaves later blocks in
place. The Windows ownership pattern has the same first-block behavior. Multi-manager support
must replace these patterns and their single-block guards together so convergence cannot be
partial or silent.

## Per-env S3 keys

The per-env overlay (`vars/redhat_<env>.yml`) supplies the bucket, the RPM key, and the
trusted SHA256. Bumping the agent version means re-uploading the RPM to the same prefix
and updating both fields:

```yaml
s3:
  bucket:           '<account-id>-ansible'
  agent_rpm_key:    'applications/wazuh-agent/wazuh-agent-4.14.5-1.x86_64.rpm'
  agent_rpm_sha256: '<sha256sum of the uploaded RPM>'
```

## S3 Python deps

boto3/botocore come from the **bootstrap venv** (`/opt/ansible/venv`, built by
`playbooks/bootstrap.yml`) — not from pip on the target. The agent's `amazon.aws.s3_object`
task borrows the venv via a block-level `ansible_python_interpreter` override, while every other
task runs under platform-python (which carries the libselinux/dnf/firewalld bindings the role
needs). The former `python3-pip` install + fapolicyd-trust dance was removed with that change.

On the **Windows** path the artifact is an MSI and `s3_object` runs delegated to the *controller*
venv (a Windows target has no boto3), then `win_copy` pushes the verified MSI to the endpoint.

## Enrollment security model

The role calls `agent-auth -m <manager> -p 1515 -A <name> -I <ip>` to register the
endpoint. By default the manager's authd accepts any client that can reach 1515/tcp -
**network reachability is the only enrollment gate**. The `-I` flag binds the
client.keys entry to the endpoint's IP so the manager rejects a re-enrollment of the
same name from a different address.

For environments where 1515/tcp is reachable from untrusted networks, configure the
manager's authd with a shared secret and pass it to this role:

```yaml
wazuh_agent:
  manager:
    enrollment_password: '<vault-encrypted-secret>'
```

The role then invokes `agent-auth -P <secret>` and only clients holding the secret can
register. The value is marked `no_log` in argument_specs and the enrollment task itself
no-logs whenever the password is set.

## Agent-manager transport encryption

`wazuh_agent.manager.protocol` defaults to `tcp`. The Wazuh agent-manager link wraps
every message in a per-agent AES-256 envelope keyed off `client.keys` regardless of
whether the transport is TCP or UDP, so `tcp` is not plaintext. UDP is the legacy 3.x
transport and has the same crypto guarantees but no delivery guarantees.

## File integrity monitoring

The role configures `/etc` for real-time monitoring by default. Override the list for targeted
monitoring:

```yaml
wazuh_agent:
  fim:
    realtime_paths:
      - '/etc/hosts'
```

## Example

```yaml
- hosts: monitored_endpoints
  roles:
    - role: 'wazuh_agent'
      vars:
        ENV: 'dev'
        wazuh_agent:
          manager:
            host: 'wazuh-manager.example.internal'
          fim:
            realtime_paths:
              - '/etc/hosts'
```
