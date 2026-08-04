# linux_disk_manager

The **step-0 storage initializer**. Given a machine with attached-but-blank data disks, it
**partitions → formats → labels → mounts** each declared disk, then the application role (e.g.
`wazuh_server`) consumes the mounted volume at `/mnt/data`.

Framework-compatible role: ships the ansible-framework **shared** generic loader
(`tasks/main.yml`, byte-identical — never edit), merged-config guards in `tasks/validate.yml`,
and `present_redhat.yml` / `clean_redhat.yml`. AWS Function-tag resolution is isolated in
`tasks/resolve_aws.yml`.

## The Nitro problem this role solves

Block-device names (`/dev/sda`, `/dev/nvme0n1`) are **not stable** — on AWS Nitro the NVMe
enumeration order can differ across reboots, so partitioning or mounting *by device name* can
target the wrong disk or leave an fstab entry that fails after a re-enumeration (the previous
production role fed `/dev/nvme0n1` straight into `parted` and `fstab`). This role instead:

- **selects** each disk by its declared stable **`unique_id`** — the `/dev/disk/by-id/` name —
  and operates entirely through that symlink (`<unique_id>` / `<unique_id>-part1`), never
  `/dev/sdX`; and
- writes **fstab by filesystem `UUID`**, so a reboot that re-enumerates the disk still mounts
  the correct volume.

Both are platform-agnostic: the by-id name is the disk **WWN** on VMware (requires
`disk.EnableUUID = "TRUE"` on the VM), the **QEMU serial** on Proxmox, and the **NVMe/EBS
serial** on AWS. CI/CD supplies the literal value, or AWS entries can resolve it from an EBS
`Function` tag.

## Two kinds of logic (kept distinct)

- **Targeting** — dispatch to the declared `platform` provider and address each disk by a stable
  `/dev/disk/by-id/` name, writing fstab by UUID. VMware and Proxmox entries declare
  `unique_id`; AWS entries may instead declare `function`, which `tasks/resolve_aws.yml` maps
  to the attached EBS volume's NVMe by-id serial before any device probe.
- **Defensive validation** — `tasks/validate.yml` rejects unsupported platforms, ambiguous
  identities, and duplicate declared identities or mount points. Immediately before `parted`,
  read-only probes reject a foreign or occupied disk; this guard is load-bearing because
  `parted` can replace a non-GPT partition table instead of failing loudly. There is deliberately
  no detected-vendor match.

## Configuration

Defaults live under `linux_disk_manager_defaults` (`defaults/main.yml`) and merge with
`vars/<family>[_<env>].yml` overlays plus the playbook's `linux_disk_manager:` override dict
into `linux_disk_manager_running` (exposed to task files as `config`).

Declare these in the `linux_disk_manager:` override dict:

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `platform` | ✅ | — | `vmware`, `proxmox`, or `aws`; all select the same shared by-id provider block. |
| `disks` | ✅ | `[]` | List of disks to manage. An empty list performs no disk mutation, but `platform` remains required. |

Each `disks[]` entry:

| `disks[]` key | Required | Default | Purpose |
|---------------|----------|---------|---------|
| `unique_id` | One identity required | — | Stable `/dev/disk/by-id/` **name** of the whole disk (VMware WWN, Proxmox QEMU serial, or AWS NVMe/EBS serial). Required on VMware/Proxmox; optional on AWS when `function` is used. Not a `/dev/…` path. |
| `function` | AWS alternative | — | EBS `Function` tag resolved to a unique attached volume. Declare exactly one of `unique_id` or `function`. |
| `mount_point` | ✅ | — | Absolute mount path. |
| `label` | ✅ | — | Filesystem label. |
| `fstype` | | `xfs` | Filesystem type. |
| `opts` | | `defaults,nodev,nosuid` | Mount options (STIG-friendly; **not** `noexec`). |
| `mode` | | `0755` | Mount-point directory mode. |
| `passno` | | `2` | fstab fsck order. |

## Run

```bash
# step 0 — provision the data disk, then deploy the stack
ansible-playbook -i lab/inventory.yml playbooks/linux_disk_manager.yml -e ENV=dev
```

## Requirements

- RHEL-family target over SSH; `ENV` play-var (loader-validated); `become: true`.
- Collections: `community.general` (parted, filesystem), `ansible.posix` (mount), and
  `amazon.aws` (`ec2_vol_info`) when AWS `function` resolution is used.
- VMware targets: `disk.EnableUUID = "TRUE"` on the VM (so `/dev/disk/by-id/wwn-*` exists).
- Proxmox targets: the data disk must expose a stable QEMU serial under `/dev/disk/by-id/`.
- AWS targets: the EBS volume must be attached to a **Nitro**-based instance (so
  `/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_vol<id>` exists); non-Nitro (Xen) instances
  do not produce this by-id name. Function-tag resolution also requires controller-side AWS
  credentials with permission to describe attached volumes; the target needs no EBS/IAM grant.
- Toolchain: RHEL 8 targets run platform-python 3.6 → controller ansible-core `>=2.16,<2.17`
  with `community.general <8` / `ansible.posix <2` (see `ansible/requirements.yml`).
