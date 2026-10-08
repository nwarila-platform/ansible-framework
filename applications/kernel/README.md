# `kernel` role

Configures the kernel from values its caller supplies: it makes the kernel package present, renders
sysctl and modprobe drop-in files, comments out every other definition of the sysctl keys it manages
within a caller-chosen set of directories and records what it changed, reloads sysctl, unloads
disabled modules that are loaded, and reads every value back from the kernel, from the static
locations and from kmod. The role carries no value of its own. A system role composes the complete
set from its policy and passes it in the `kernel` mapping; the role applies exactly that set, so a
second run changes nothing, a changed set converges to the new set, and `state: absent` restores
what the record lists.

> **Scope:** the RedHat family, EL 8 and 9. The role owns the `/etc/sysctl.d` and `/etc/modprobe.d`
> drop-ins it writes, the lines it comments out and its record under `/var/lib/ansible-kernel`, and
> nothing else. The kernel command line belongs to the grub2 role and audit rules to the audit role.

## Composition and prerequisites

- The shared loader (`tasks/main.yml`, byte-identical across application roles) merges
  `kernel_defaults`, `vars/redhat.yml` and the caller's `kernel` mapping into `kernel_running`,
  validates it through `tasks/validate.yml` and dispatches `present_redhat.yml` or
  `absent_redhat.yml`.
- `python3-dnf` on the host, for `ansible.builtin.dnf`.
- `community.general` 7.5.9 on the controller, for `modprobe` (pinned in `requirements.yml`).
- `become` for the PROCESS stage; every read runs unprivileged.

## Inputs

<!-- rolecheck:inputs:begin -->
| Input | Type | Required | Default | Description |
|---|---|---|---|---|
| `ENV` | str | yes | | Selects environment-specific overlay files; `^[a-zA-Z0-9_-]+$`. |
| `state` | str | no | `present` | `present` or `absent`; see State. |
| `kernel` | dict | no | | Overrides merged on top of `kernel_defaults`; reaches the role as `kernel_running`. |
| `kernel.package_manager` | dict | no | the RedHat dnf option set | Per-family dnf options for the kernel package, keyed by `os_family`; a `state` key is refused. |
| `kernel.sysctl.conflicts` | str | no | `etc` | Where other definitions of the managed keys are commented out: `none`, `etc` or `all`. |
| `kernel.modules.unload` | bool | no | `true` | Unload a disabled module that is loaded. |
| `kernel.templates` | dict | no | `{}` | Drop-in files keyed by destination path; see Configuration. |
| `kernel.temp_dir` | bool | no | `true` | Loader temp directory creation and cleanup. |
| `kernel.temp_dir_path` | str | no | | Parent of the loader temp directory. |
<!-- rolecheck:inputs:end -->

The caller's values travel inside the `kernel` mapping. An extra-vars override
(`-e '{"kernel": {…}}'`) replaces that mapping rather than merging with it, so it restates every key
the caller's mapping sets.

## Configuration

`templates` is keyed by destination path. Each entry names its template kind, its file metadata and
its settings:

```yaml
kernel:
  sysctl:
    conflicts: 'all'
  templates:
    '/etc/sysctl.d/99-policy.conf':
      template: 'sysctl.conf.j2'
      file:
        path: '/etc/sysctl.d/99-policy.conf'
        owner: 'root'
        group: 'root'
        mode: '0644'
      settings:
        kernel.example_alpha: 1
        net.example.beta: 0
    '/etc/modprobe.d/policy.conf':
      template: 'modprobe.conf.j2'
      file:
        path: '/etc/modprobe.d/policy.conf'
        owner: 'root'
        group: 'root'
        mode: '0644'
      settings:
        disabled: ['example-one', 'example_two']
```

- A `sysctl.conf.j2` file lives directly in `/etc/sysctl.d`, a `modprobe.conf.j2` file directly in
  `/etc/modprobe.d`, named `<name>.conf` with no slash or control byte in the name (a leading dot
  is allowed, and hidden files are inventoried like any other), the one alphabet the scan, the
  record and the restoration accept. Keys are rendered in sorted order, one
  `key = value` line each; modules as `install <name> /bin/false` then `blacklist <name>`, sorted.
- Values are strings or numbers. Booleans and null are refused: YAML `true` would render as `True`.
- `file.selinux` (`level`, `role`, `type`, `user`, each a string) is optional; omitted, the policy's
  default label applies, which differs by release [INV-05].
- `sysctl.conflicts` decides where a second definition of a managed key is commented out. `etc`
  covers `/etc/sysctl.conf` and `/etc/sysctl.d`; `all` adds `/run/sysctl.d`,
  `/usr/local/lib/sysctl.d`, `/usr/lib/sysctl.d` and `/lib/sysctl.d`, where vendor packages ship
  drop-ins [INV-02]. Choose `all` where a compliance check reads every location and reports any
  second definition; choose `etc` where the check reads the runtime value and separately verifies
  vendor files against the rpm database, because those files are not rpm config files and an edit
  shows as a digest mismatch [INV-03]. `none` leaves every other file alone; the runtime value then
  follows precedence [INV-01].
- A commented line keeps its text after the marker `# kernel-role-disabled: ` and the record keeps
  the original. A later run restores a line when its key is no longer managed or its file is
  outside the newly selected locations; `absent` restores every recorded line.
- A symlink inside a selected location is never edited. One whose target is a live regular file
  outside the files the role edits is read through the link, and END reports it when the target
  defines a managed key. `/etc/sysctl.conf` itself, when it is a live symlink to a regular file,
  is read through its own path under the `etc` and `all` policies and never edited; a stat
  through the link is taken in BEGIN and again in END. Immediately before each removal, restoration, rendering, edit and record
  write, every parent directory on the way to the target must be a real root-owned directory and
  the target a regular file or absent; a symlinked directory refuses the run rather than carrying
  the change outside the declared scope.
- The reload is a task, never a handler, gated on what is owed and decided before anything
  changes, from the record, the kernel and the files BEGIN read: a recorded sysctl file no longer
  declared, a recorded line no longer wanted, a declared value the kernel reports differently, a
  definition to comment out, or a declared sysctl file missing or different from its rendering;
  modprobe work never reloads sysctl, and no task result's change flag is consulted. A rerun
  therefore repairs runtime drift and finishes an interrupted transition instead of only reporting
  them [INV-09].
- Immediately before the record directory is created, before each record write and before the
  record and its directory are removed, the same parent-and-target guard runs over the record path,
  so a symlinked `/var/lib` refuses the run rather than carrying the record outside its directory.
- A file the role would edit is refused when it contains a carriage return, lacks a final newline,
  or already holds the exact marked line the role would write: the role could not restore it byte
  for byte or tell its own line from the existing one.

A system role composes the mapping from its policy and calls the role once:

```yaml
- name: 'PROCESS | Apply The Kernel Policy'

  ansible.builtin.include_role:
    name: 'kernel'
  vars:
    ENV: "{{ ENV }}"
    state: 'present'
    kernel: "{{ __policy_kernel__ }}"
```

## State

| `state` | Behaviour |
|---|---|
| `present` | The package is present and the record directory exists; both precede the journal. The record is validated, then written in two phases: before the first drop-in or line mutation it names every file and line this run may touch; after a successful reload it names exactly the declared set. Recorded files no longer declared are removed; recorded lines no longer wanted are restored; every declared file is rendered; other definitions of the managed keys within the `conflicts` locations are commented out; sysctl is reloaded when any file changed, when the record still names a file no longer declared or a line no longer wanted, or when the kernel reports a declared value differently; disabled modules that are loaded are unloaded; every value is read back from the kernel, from the static locations and from kmod. |
| `absent` | A record directory holding anything but the record is refused before any change. Every recorded file is removed and every recorded line restored to its recorded text, sysctl is reloaded when the record names a sysctl file or a line, and only then are the record and its directory removed, so a failed reload keeps the record for the retry. The package stays: the running kernel cannot be removed. A key with no other definition keeps its runtime value until the host reboots. |

There is no `clean` state: the role creates no cache. A declared destination that already holds a
file the record does not list is refused rather than overwritten. The record is
`/var/lib/ansible-kernel/manifest.json` (a regular root-owned `0600` file, refused otherwise): version
1, the destinations the role wrote, and the lines it commented out as `[file, original text]` pairs.
Its schema and every path in it are validated before any value is used, so a damaged record is a
refusal, never a deletion. A marked line the record does not list is left alone.

## Design invariants

1. [INV-01] `sysctl --system` reads `/usr/lib/sysctl.d`, `/run/sysctl.d`, `/etc/sysctl.d` and
   `/etc/sysctl.conf`; a file in `/etc/sysctl.d` with the same name as a vendor file replaces it,
   and later-sorting names win (sysctl.d(5); the stock `/etc/sysctl.conf` header, read
   2026-10-08). The role's files therefore win at reload when they sort last, and the conflict
   policy exists for checks that read files rather than the kernel.
2. [INV-02] Vendor packages ship sysctl drop-ins under `/usr/lib/sysctl.d`: four on EL 8 (from
   `systemd` and `elfutils-default-yama-scope`) and two on EL 9 (from `systemd` and the release
   package). On the merged-/usr layout of EL 8 and 9 `/lib` itself is the symlink (`/lib ->
   usr/lib`), so `/lib/sysctl.d` is the vendor directory reached through it, and `stat` with
   `follow: false` on `/lib/sysctl.d` alone reports a real directory (measured 2026-10-08 in
   `rockylinux:8` and `rockylinux:9`: same device and inode as `/usr/lib/sysctl.d`).
   `/etc/sysctl.conf` is present on EL 8 and owned by `systemd-udev` on EL 9 (the live-check
   record of the stock RHEL 9.8 image, 2026-10-07). The role lists `/lib/sysctl.d` only when `/lib`
   and `/lib/sysctl.d` are both real, non-link directories and the directory's device and inode
   differ from `/usr/lib/sysctl.d`'s, so no vendor file is seen twice (`tests/test.yml`, the alias
   play, runs that predicate over a merged, a split and a linked tree).
3. [INV-03] Those vendor files are not rpm `%config` files (`rpm -qc`, measured 2026-10-08), so an
   edit is a digest mismatch under `rpm -Va --noconfig`. The role never edits them unless the
   caller chooses `all`, and it records every line it edits.
4. [INV-04] kmod reports and matches module names with underscores: a hyphenated name appears with
   underscores in `lsmod` and in `modprobe --showconfig` (kmod 28-11.el9, measured 2026-10-08 in
   `rockylinux:9`). The role normalizes names before it unloads or reads them back.
5. [INV-05] The targeted policy labels `/etc/sysctl.d/*.conf` `etc_t` on EL 8 and `system_conf_t`
   on EL 9, and `/etc/modprobe.d/*.conf` `modules_conf_t` on both (`matchpathcon`, selinux-policy
   3.14.3-139.el8_10.2 and 38.1.75-2.el9_8.1, measured 2026-10-08). The template module applies
   the policy's label when `file.selinux` is omitted.
6. [INV-06] kmod runs the first `install` directive it reads for a module, reading its
   configuration directories as one set in sorted basename order, with a file in `/etc/modprobe.d`
   replacing a same-named file in `/usr/lib/modprobe.d`; `modprobe --dry-run --verbose <name>` prints
   exactly that command. An earlier-sorting file saying `/bin/true` makes the dry run print
   `install /bin/true` while `--showconfig` still lists the role's `/bin/false` line (kmod
   28-11.el9, measured 2026-10-08 in `rockylinux:9` with `00-true.conf` against `zz-false.conf`, the
   reverse order, both lines in one file, and the two directories). END therefore asserts the dry
   run's exact output, not the presence of a line, and a caller names its file to sort first.
7. [INV-07] `install <name> /bin/false` prevents loading; it does not unload a loaded module, which
   `modprobe -r` does and which fails while the module is in use (modprobe(8), kmod 28-11.el9,
   read 2026-10-08). kmod reads `/etc/modprobe.d`, `/run/modprobe.d` and `/usr/lib/modprobe.d`.
8. [INV-08] In a folded YAML scalar, ansible-core 2.21 hands a Jinja string literal to the regex
   engine with its backslashes intact: `'\r'` matches a carriage return in slurped file bytes and
   not a bare newline, `'\n$'` matches a final newline and not its absence, `'^a\.conf$'` matches
   `a.conf`, and a backreference `\1` works; a doubled backslash becomes a literal backslash and
   matches none of those. A double-quoted YAML scalar instead turns `\r` into a real carriage
   return, which Jinja normalises to a newline before the regex sees it (measured 2026-10-08 with
   ansible-core 2.21.2 against fixture files; the probe and its output are recorded with the piece
   that added the role). Every authored regex literal that relies on a preserved backslash
   therefore lives in a folded scalar with single-backslash escapes; regexes built from
   `regex_escape` output and plain single-quoted scalars carry no such escape; and the byte checks
   run on slurped content, never on Jinja literals.
9. [INV-09] The record is trimmed to the declared set only after a successful reload. A run
   interrupted between a mutation and its reload leaves a record that still names a file no longer
   declared or a line no longer wanted, and the next run reads that as a reload still owed even when
   every file task reports no change. ansible-core runs no handler after a play failure, and HAND-01
   places a notified flush last in its stage, after which no record could be written, so the reload
   is a task gated on what is owed rather than a handler, and REG-01 keeps task results' change
   flags out of that gate, so it is decided from the record, the kernel and the files before any
   mutation (ANSIBLE-STYLE-SPEC v2, HAND-01, CHG-01 and REG-01, read 2026-10-08).
10. [INV-10] `lineinfile` with `backrefs: true` passes `line` through the match's `expand`, so a
    backslash sequence in it is replacement syntax, not text (ansible-core 2.21,
    `modules/lineinfile.py`, read 2026-10-08). The role therefore never interpolates an admitted
    line into `line:`: commenting replaces the exact-match regexp with `# kernel-role-disabled: \g<0>`,
    restoration captures the escaped original and replaces with `\g<1>`, and `tests/test.yml` runs
    both over `\1`, `\t` and `\g<0>`.

## First-class PowerShell

None. The role has no Windows path.

## Verification

- END reads `sysctl -n` for every declared key and names every key whose observed value differs
  (compared case-sensitively),
  greps the `conflicts` locations (files, and live symlinks by their own path, less the role's own
  files) for any remaining definition, requires `modprobe --dry-run --verbose` to print exactly
  `install /bin/false` for every disabled module, lists the blacklist lines from
  `modprobe --showconfig`, and reads `lsmod` after an unload. A mismatch fails
  the run and names the key, file or module.
- `tests/test.yml` runs on localhost without root: the contract accepts a conforming
  configuration and four absent-state configurations whose unread sections are malformed, refuses
  twenty-six malformed present-state ones by cause, both templates render to expected bytes, the
  find module lists a symlink only under the link type, hidden files included, the hit pairs are
  built from per-file grep results over a space-named, a colon-named and a hidden file, the reload
  gate's rendering expression matches the template's bytes, the legacy sysctl directory is listed only as
  a distinct real directory, the guard expressions name exactly a symlinked parent, both record
  phases render identical bytes, the duplicate and marked-line refusals are exact for names and
  values holding any byte the contract admits, commenting and restoration preserve `\1`, `\t` and
  `\g<0>` as text, the legacy file is a read-only candidate only as a live symlink, and the END
  comparison expression names exactly the differing keys. From the repository root:
  `ansible-playbook -i applications/kernel/tests/inventory applications/kernel/tests/test.yml`.
- A converge-twice and check-diff proof on stock EL 8 and EL 9 hosts, with transition, negative
  and absent legs, is pending; its record will be cited here when it has run.
