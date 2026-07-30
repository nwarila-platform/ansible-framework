# windows_disk_manager

The Windows sibling of `linux_disk_manager`. It establishes a stable disk identity,
drive-letter, and formatting contract for Windows hosts on VMware and AWS.

The role validates configuration and confirms that the declared platform matches the detected
system vendor. It trusts each declared literal disk identity, brings that disk online and
writable, then initializes it as GPT, creates a full-size partition, and formats it as NTFS.
An existing NTFS volume whose label matches the declaration case-insensitively is skipped for
idempotency.

## Configuration

Defaults live under `windows_disk_manager_defaults` and merge through the framework v3.2.0
loader with OS overlays and the playbook's `windows_disk_manager:` override dictionary.

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `platform` | Yes | `''` | `vmware` or `aws`. Proxmox is not accepted until its Windows identity path is measured. |
| `disks` | No | `[]` | Disk declarations to provision. An empty list completes after the vendor check. |

Each `disks[]` entry uses this contract:

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `unique_id` | Identity option | — | VMware whole-disk identity such as `eui.<hex>`; required for VMware. |
| `function` | Identity option | — | AWS EBS `Function` tag, resolved in a later piece. Do not combine with `unique_id`. |
| `drive_letter` | Yes | — | One ASCII letter, optionally followed by `:` or `:\`. |
| `label` | Yes | — | Volume label. |
| `allocation_unit` | No | `4096` | Allocation-unit size in bytes. |
| `fstype` | No | — | Reserved and ignored. This role provisions NTFS only. |

The enforced drive-letter grammar is `^[A-Za-z](?::\\?)?$`. Accepted examples are `D`, `d`,
`D:`, `d:`, `D:\`, and `d:\`. Values such as `Data`, `D::`, bare `D\`, an empty string, or a
path after the drive letter are rejected. Accepted values canonicalize to their uppercase
letter, so equivalent spellings such as `D`, `d:`, and `D:\` are duplicates.

## Provisioning behavior

- `platform: vmware` requires detected vendor `VMware, Inc.`.
- `platform: aws` requires detected vendor `Amazon EC2`.
- All validation guards are scoped to `state=present`; `state=clean` is a supported no-op.
- AWS `function` resolution is deferred; every active declaration must provide a literal
  `unique_id`.
- Literal identifiers are trusted configuration. The role does not classify or refuse
  foreign/unknown disk contents.
- After the online/writable fixup, a disk is skipped only when any volume under its partitions
  is NTFS and has the declared label, compared case-insensitively.
- Every other declared disk enters the `force: false` GPT initialization, full-partition, and
  NTFS quick-format pipeline. Drive letters are canonicalized to their uppercase first letter,
  and `allocation_unit` defaults to 4096 bytes.
- `disks: []` completes successfully after the vendor check.
