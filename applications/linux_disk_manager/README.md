# linux_disk_manager

The **step-0 storage initializer**. Given a machine with attached-but-blank data disks, it
**partitions → formats → labels → mounts** each declared disk, then the application role (e.g.
`wazuh_server`) consumes the mounted volume at `/mnt/data`.

Framework-compatible role: ships the ansible-framework **v3.1.0** generic loader
(`tasks/main.yml`, byte-identical — never edit) plus `present_redhat.yml` / `clean_redhat.yml`.

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
`disk.EnableUUID = "TRUE"` on the VM) and the **NVMe/EBS serial** on AWS. CI/CD supplies the
correct value.

## Two kinds of logic (kept distinct)

- **Targeting** — the role's function, kept explicit and robust: dispatch to the declared
  `platform` provider, and hit each *specific* disk by its stable, globally-unique `unique_id`
  (its `/dev/disk/by-id/` name), writing fstab by UUID. This is what makes disk selection
  reliable and accurate; it is not overhead.
- **Defensive validation** — CI/CD's responsibility, **not** done here: no input re-checks, no
  vendor-match assert, no foreign-filesystem guard. A bad `unique_id` makes `parted` fail
  loudly; a bad `mount_point` makes the mount module fail. The only non-mechanical task is a
  `wait_for` on the partition node (udev creates it asynchronously) — reliability, not a guard.

## Configuration

Defaults live under `linux_disk_manager_defaults` (`defaults/main.yml`) and merge with
`vars/<family>[_<env>].yml` overlays plus the playbook's `linux_disk_manager:` override dict
into `linux_disk_manager_running` (exposed to task files as `config`).

Declare these in the `linux_disk_manager:` override dict:

| key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `platform` | ✅ | — | `vmware` (target-0) or `aws`. Selects the provider block in `present_redhat.yml`. Targeting, not a guard — no vendor-match assert. |
| `disks` | ✅ | `[]` | List of disks to manage (empty → no-op). |

Each `disks[]` entry:

| `disks[]` key | Required | Default | Purpose |
|---------------|----------|---------|---------|
| `unique_id` | ✅ | — | Stable `/dev/disk/by-id/` **name** of the whole disk (e.g. `wwn-0x6000c29…`). Not a `/dev/…` path. |
| `mount_point` | ✅ | — | Absolute mount path. |
| `label` | ✅ | — | Filesystem label. |
| `fstype` | | `xfs` | Filesystem type. |
| `opts` | | `defaults,nodev,nosuid` | Mount options (STIG-friendly; **not** `noexec`). |
| `mode` | | `0755` | Mount-point directory mode. |
| `passno` | | `2` | fstab fsck order. |

## Run

```bash
# step 0 — provision the data disk, then deploy the stack
ansible-playbook -i lab/inventory.yml playbooks/linux_disk_manager.yml -e env=int
```

## Requirements

- RHEL-family target over SSH; `ENV` play-var (loader-validated); `become: true`.
- Collections: `community.general` (parted, filesystem), `ansible.posix` (mount).
- VMware targets: `disk.EnableUUID = "TRUE"` on the VM (so `/dev/disk/by-id/wwn-*` exists).
- Toolchain: RHEL 8 targets run platform-python 3.6 → controller ansible-core `>=2.16,<2.17`
  with `community.general <8` / `ansible.posix <2` (see `ansible/requirements.yml`).
