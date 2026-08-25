# host_readiness

Waits until a host will answer, and nothing else.

Call it before [`os_bootstrap`](../../operating_systems/os_bootstrap/README.md): this role proves
the transport is usable, and that role then repairs it. A host that answers is ready as far as this
role is concerned — any further precondition, such as a cloud image finishing its first-boot
provisioning, is the caller's to state, because it is particular to where the host runs.

## Usage

```yaml
- name: 'Wait for every target to answer'
  hosts: 'all'
  gather_facts: false
  tasks:
    - name: 'Wait for this host'
      ansible.builtin.include_role:
        name: 'host_readiness'
```

`gather_facts: false` is required, for the same reason `os_bootstrap` requires it: gathering runs a
module, and on a fresh Windows host the shell that would wrap it is not the one OpenSSH serves until
the bootstrap changes it.

## What it does

Runs `raw` over whatever connection the inventory selected, repeatedly, until a command actually
executes — then asserts that one did. That is the entire role.

There is deliberately **no** controller-side port check. A plain TCP connect cannot speak for a
connection that reaches its target through a proxy command or a tunnel, so on an SSM-proxied or
port-forwarded host it would fail while the host was perfectly reachable. The connection is the
only honest test of the connection.

The probe never escalates. Proving a transport answers needs no privilege, and `raw` cannot be
escalated on every shell this suite meets — the `powershell` shell plugin refuses `become` outright,
so inheriting it would fail the probe on exactly the hosts the role exists for.

## How it repeats

With a `loop` and `break_when`, not `until`/`retries`.

A refused session raises out of ansible-core's attempt loop rather than returning a result, so
`until`/`retries` never evaluates and the wait ends after the **first** refusal — which is the one
thing this role must not do. Measured against ansible-core 2.21.2: a `raw` task with
`retries: 3`/`until` against a closed port reports `attempts` unset and returns in under a second.
A loop item that cannot connect is caught, so the next item runs; `ignore_unreachable` keeps the
host in the play, and the assertion afterwards is what decides the outcome.

The assertion reads the **last** attempt. The registered result reports unreachable if *any*
attempt was, which is the normal course of waiting, so asking it directly would fail every wait that
actually had to wait.

## Why not `wait_for_connection`

That action decides success by executing the ping module, and a module is precisely what cannot run
yet — this role exists to be the step before the host is known good. `raw` is passed to the shell as
written rather than wrapped.

## Inputs

All optional bounds, declared as **play** variables (never as `vars:` on the include).

| Variable | Default | Meaning |
| --- | ---: | --- |
| `host_readiness_attempts` | `60` | How many times the probe may run before the wait fails. |
| `host_readiness_pause_seconds` | `15` | Pause between attempts. |

The two multiply: the wait runs for at most `attempts × (pause + however long a refused connection
takes to give up)`. The defaults allow roughly fifteen minutes of pauses, which covers a Windows
first boot.
