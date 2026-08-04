# windows_disk_manager

The Windows sibling of `linux_disk_manager`. It establishes a stable disk identity,
drive-letter, and formatting contract for Windows hosts on VMware and AWS.

The role validates configuration and confirms that the declared platform matches the detected
system vendor. It trusts each declared literal disk identity, brings that disk online and
writable, classifies its observed contents, and provisions only positively recognized blank or
unformatted disks. A foreign classification refuses provisioning for the entire declaration set.

## Configuration

Defaults live under `windows_disk_manager_defaults` and merge through the framework shared
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
- Literal `unique_id` values are trusted configuration. After resolving each declared disk and
  applying the online/writable fixup, the role classifies its observed contents as follows:

| State | Positive recognition | Behavior |
|-------|----------------------|----------|
| `ours` | Any observed volume has filesystem type NTFS and the declared label, both compared case-insensitively. | Skip initialization, partitioning, and formatting. Unrelated additional volumes do not disqualify this state. |
| `blank` | The disk reports `partition_style: RAW`. | Enter the provisioning pipeline. |
| `unfmtd` | The disk reports GPT and successful partition enumeration, and either has no non-`Reserved` partitions or every non-`Reserved` partition reports volumes, at least one volume is observed, every volume has a non-null `type`, and every `type` is empty. | Resume the provisioning pipeline. |
| `foreign` | Anything not positively recognized by an earlier state, including missing partition, volume, or filesystem-type evidence. | Fail before any declared disk is initialized, partitioned, or formatted. |

- Ownership is deliberately narrow: on the disk resolved by the declared `unique_id`, any NTFS
  volume carrying the declared label case-insensitively is `ours`. That match suppresses all
  three provisioning tasks. The role deliberately does not reconcile the drive letter,
  allocation-unit size, partition count, or unrelated additional volumes on a disk classified
  as `ours`.
- `blank` and `unfmtd` disks enter the `force: false` GPT initialization, full-partition, and
  NTFS quick-format pipeline. Drive letters are canonicalized to their uppercase first letter,
  and `allocation_unit` defaults to 4096 bytes.
- Drive-letter targeting has a known limitation: the underlying partition and format modules
  resolve a declared drive letter globally. A drive-letter collision on another disk can
  therefore target that other volume despite the declared disk number. This role does not
  preflight such collisions; its foreign-content refusal applies to the correctly targeted disk,
  so declarations must use an unoccupied drive letter.
- `disks: []` completes successfully after the vendor check.
