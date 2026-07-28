# s3_artifact_delivery

Delivers one checksum-pinned S3 object without distributing a reusable AWS credential set to the
target. For each attempt, the controller assumes the supplied reader role, creates a fresh
presigned HTTPS URL locally, and lets the target fetch only through that bearer URL. The temporary
role session, bearer URL, and failure result are scrubbed before another attempt can begin.

This is a helper-capability role, not a lifecycle-managed application. It deliberately has no
`tasks/main.yml`; invoke its `fetch` entry point explicitly with `include_role` and `tasks_from`.
The framework's standard loader requires `ENV` and a `present`, `absent`, or `clean` state, none of
which describes a one-shot artifact transfer honestly.

## Use

```yaml
- name: Fetch a pinned artifact through a controller-signed URL
  ansible.builtin.include_role:
    name: s3_artifact_delivery
    tasks_from: fetch
  vars:
    s3_artifact_delivery_reader_role_arn: "{{ artifact_reader_role_arn }}"
    s3_artifact_delivery_session_name: "{{ artifact_reader_session_name }}"
    s3_artifact_delivery_bucket: "{{ artifact_bucket }}"
    s3_artifact_delivery_object_key: 'applications/example/package.rpm'
    s3_artifact_delivery_region: 'us-east-1'
    s3_artifact_delivery_checksum: "{{ package_sha256 }}"
    s3_artifact_delivery_destination: '/var/tmp/package.rpm'
    s3_artifact_delivery_platform: 'posix'
```

Set `s3_artifact_delivery_platform` to `windows` for a Windows target and use a Windows destination
path. Both platforms execute the same retry path; only the final transfer module differs.
The destination's parent directory must already exist on the target and be writable by the remote
Ansible execution context. The role does not create that directory on either platform.

## Contract

Required inputs:

| Variable | Purpose |
|----------|---------|
| `s3_artifact_delivery_reader_role_arn` | Scoped role that the controller assumes for the object read. |
| `s3_artifact_delivery_session_name` | STS role-session name supplied by the caller. |
| `s3_artifact_delivery_bucket` | Bucket containing the artifact. |
| `s3_artifact_delivery_object_key` | Exact object key to fetch. |
| `s3_artifact_delivery_region` | Region containing the bucket. |
| `s3_artifact_delivery_checksum` | Expected SHA-256 as 64 hexadecimal characters. |
| `s3_artifact_delivery_destination` | Target path for the downloaded object. |
| `s3_artifact_delivery_platform` | `posix` or `windows`. |

Optional inputs:

| Variable | Default | Purpose |
|----------|---------|---------|
| `s3_artifact_delivery_url_expiry_seconds` | `900` | Lifetime of each independently generated URL. |
| `s3_artifact_delivery_retry_delay_seconds` | `10` | Delay before the second and third attempts. |
| `s3_artifact_delivery_transfer_timeout_seconds` | `60` | Per-transfer socket inactivity timeout. |
| `s3_artifact_delivery_posix_mode` | `'0600'` | Mode applied by `get_url` on POSIX targets. |

The controller's ambient identity must be allowed to assume the reader role. The controller Python
used by `ansible-playbook` must provide `boto3` and `botocore`, and the controller must have the
`amazon.aws` collection. Windows transfers also require `ansible.windows`. Targets need outbound
HTTPS access to S3. They receive the scoped bearer URL, not the secret key or a standalone
temporary credential set.

The retry sequence is intentionally written as three gated includes. A loop over `include_tasks`
expands all iterations before any attempt runs and therefore cannot stop after success. Nothing on
the mint, sign, or fetch path uses `run_once`; each inventory host owns its own fresh session and
signature on every attempt.
