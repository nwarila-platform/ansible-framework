# windows_disk_manager

The Windows sibling of `linux_disk_manager`. It establishes a stable disk identity,
drive-letter, and formatting contract for Windows hosts on VMware and AWS.

This WDM-01 role is intentionally **guard-only**. It validates configuration and confirms that
the declared platform matches the detected system vendor, but performs no disk initialization,
partitioning, formatting, or other mutation. Any non-empty `disks` list fails closed with a
message that provisioning is deferred to WDM-02. Only an empty list can complete successfully.

## Configuration

Defaults live under `windows_disk_manager_defaults` and merge through the framework v3.2.0
loader with OS overlays and the playbook's `windows_disk_manager:` override dictionary.

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `platform` | Yes | `''` | `vmware` or `aws`. Proxmox is not accepted until its Windows identity path is measured. |
| `disks` | No | `[]` | Disk declarations. WDM-01 rejects a non-empty list; WDM-02 will provision them. |

Each future `disks[]` entry uses this contract:

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `unique_id` | Identity option | — | VMware whole-disk identity such as `eui.<hex>`; required for VMware. |
| `function` | Identity option | — | AWS EBS `Function` tag, resolved in a later piece. Do not combine with `unique_id`. |
| `drive_letter` | Yes | — | One ASCII letter, optionally followed by `:` or `:\`. |
| `label` | Yes | — | Volume label. |
| `allocation_unit` | No | `4096` | Allocation-unit size in bytes. |
| `fstype` | No | `NTFS` | Filesystem type. |

The enforced drive-letter grammar is `^[A-Za-z](?::\\?)?$`. Accepted examples are `D`, `d`,
`D:`, `d:`, `D:\`, and `d:\`. Values such as `Data`, `D::`, bare `D\`, an empty string, or a
path after the drive letter are rejected. Accepted values canonicalize to their uppercase
letter, so equivalent spellings such as `D`, `d:`, and `D:\` are duplicates.

## WDM-01 behavior

- `platform: vmware` requires detected vendor `VMware, Inc.`.
- `platform: aws` requires detected vendor `Amazon EC2`.
- All validation guards are scoped to `state=present`; `state=clean` is a supported no-op.
- A non-empty `disks` list always fails before any disk action.

Disk discovery, AWS Function-tag resolution, initialization, partitioning, and formatting are
deferred to WDM-02.
