"""h. escalation: plain probes stay unescalated under play become and --become; include/role
parameters forcing the switch fail before traffic; a root login wins require_elevated with no become
and a non-root login does not; each accepted become profile's command shape under poisoned keyword,
CLI, environment and ini selectors, executables and passwords, including omitted user or flags;
adversarial selectors and every refused form refused before traffic; host_readiness stays
unescalated after resolution."""
import re

POISON_INI = {
    "privilege_escalation": {"become_user": "poison-ini-user", "become_flags": "--poison-ini-flags",
                             "become_exe": "/poison/ini-exe", "become_method": "su"},
    "sudo_become_plugin": {"user": "poison-ini-sudo-user", "flags": "--poison-ini-sudo-flags",
                           "executable": "/poison/ini-sudo-exe", "password": "BECOME-INI-SECRET-CANARY-SUDO"},
    "doas_become_plugin": {"user": "poison-ini-doas-user", "flags": "--poison-ini-doas-flags",
                           "executable": "/poison/ini-doas-exe", "password": "BECOME-INI-SECRET-CANARY-DOAS"},
    "pfexec_become_plugin": {"user": "poison-ini-pfexec-user", "flags": "--poison-ini-pfexec-flags",
                             "executable": "/poison/ini-pfexec-exe", "password": "BECOME-INI-SECRET-CANARY-PFEXEC"},
    "defaults": {"executable": "/poison/ini-shell"},
}
POISON_ENV = {
    "ANSIBLE_BECOME_USER": "poison-env-user", "ANSIBLE_BECOME_FLAGS": "--poison-env-flags",
    "ANSIBLE_BECOME_EXE": "/poison/env-exe", "ANSIBLE_BECOME_METHOD": "su",
    "ANSIBLE_BECOME_PASS": "BECOME-ENV-SECRET-CANARY", "ANSIBLE_SUDO_PASS": "BECOME-ENV-SECRET-CANARY-SUDO",
    "ANSIBLE_DOAS_PASS": "BECOME-ENV-SECRET-CANARY-DOAS", "ANSIBLE_PFEXEC_PASS": "BECOME-ENV-SECRET-CANARY-PFEXEC",
    "ANSIBLE_SUDO_USER": "poison-env-sudo-user", "ANSIBLE_DOAS_USER": "poison-env-doas-user",
    "ANSIBLE_PFEXEC_USER": "poison-env-pfexec-user", "ANSIBLE_SUDO_FLAGS": "--poison-env-sudo-flags",
    "ANSIBLE_DOAS_FLAGS": "--poison-env-doas-flags", "ANSIBLE_PFEXEC_FLAGS": "--poison-env-pfexec-flags",
    "ANSIBLE_SUDO_EXE": "/poison/env-sudo-exe", "ANSIBLE_DOAS_EXE": "/poison/env-doas-exe",
    "ANSIBLE_PFEXEC_EXE": "/poison/env-pfexec-exe", "ANSIBLE_EXECUTABLE": "/poison/env-shell",
}
RUNS = [
    {"name": "keyword-sources", "config": POISON_INI, "env": POISON_ENV,
     "args": ["--become", "--become-user", "poison-cli-user", "--become-method", "su"]},
    {"name": "environment-sources", "inventory": "inventory-plain-sources.yml", "playbook": "plain-sources.yml",
     "config": POISON_INI, "env": POISON_ENV},
    {"name": "ini-sources", "inventory": "inventory-plain-sources.yml", "playbook": "plain-sources.yml",
     "config": POISON_INI},
    {"name": "switch", "inventory": "inventory-switch.yml", "playbook": "switch.yml", "expected_rc": 2},
    {"name": "adversarial", "inventory": "inventory-adversarial.yml", "playbook": "adversarial.yml"},
]
SHAPES = {
    "192.0.2.21": r"^/bin/sh -c 'sudo -H -S -n\s+-u SELECTOR-CANARY /bin/sh -c '\"'\"'echo BECOME-SUCCESS-\w+ ; id -u'\"'\"''$",
    "192.0.2.22": r"^/bin/sh -c 'sudo -H -S -n\s+-u root /bin/sh -c '\"'\"'echo BECOME-SUCCESS-\w+ ; id -u'\"'\"''$",
    "192.0.2.23": r"^/bin/sh -c 'doas\s+-n\s+-u root /bin/sh -c '\"'\"'echo BECOME-SUCCESS-\w+ ; id -u'\"'\"''$",
    "192.0.2.24": r"^/bin/sh -c 'doas\s+-n\s+-u SELECTOR-CANARY-DOAS /bin/sh -c '\"'\"'echo BECOME-SUCCESS-\w+ ; id -u'\"'\"''$",
    "192.0.2.25": r"^/bin/sh -c 'pfexec\s+'\"'\"'echo BECOME-SUCCESS-\w+ ; id -u'\"'\"''$",
    "192.0.2.26": r"^/bin/sh -c 'id -u'$",
    "192.0.2.28": r"^/bin/sh -c 'echo ready'$",
}
ADVERSARIAL = {
    **{name: "rule 5 requires allowed argument-less sudo flags including -n"
       for name in ("sudo-flags-command", "sudo-flags-swallow", "sudo-flags-end-options", "sudo-flags-quoted",
                    "sudo-flags-without-n")},
    **{name: "rule 5 rejects a shell-active become user"
       for name in ("sudo-user-space", "sudo-user-semicolon", "sudo-user-backslash", "sudo-user-dash")},
    "sudo-exe": "rule 5 rejects fields outside profile, user, and flags",
    "sudo-password": "rule 5 rejects fields outside profile, user, and flags",
    "doas-flags": "rule 5 forbids flags for doas",
    "pfexec-user": "rule 5 forbids user and flags for pfexec",
    "pfexec-flags": "rule 5 forbids user and flags for pfexec",
    **{f"become-{p}": f"rule 5 refuses {p} because"
       for p in ("su", "ksu", "machinectl", "pbrun", "pmrun", "sesu", "dzdo", "sudosu", "runas")},
    **{f"profile-{p}": f"rule 5 refuses {p} because"
       for p in ("ssh_keyboard_interactive", "winrm_credssp", "psrp_basic", "psrp_ntlm", "psrp_negotiate",
                 "psrp_credssp", "psrp_kerberos_password", "psrp_encrypted_certificate")},
    "become-password-variable": "rule 2 contains a non-canonical or profile-incompatible variable",
    "psrp-encrypted-key": "rule 5 refuses encrypted PSRP certificate keys",
}


def probe_command(run, address):
    probes = [c for c in run.ssh(host=address, mode="exec") if "echo ready" not in c["command"]
              or address == "192.0.2.28"]
    return probes[0]["command"] if probes else ""


def check(evidence, require):
    lines = []
    run = evidence["keyword-sources"]
    for address, shape in SHAPES.items():
        command = probe_command(run, address)
        require(re.match(shape, command), f"{address} probe command {command!r}")
        lines.append(f"{address}: {command}")
    for record in run.records["ssh"]:
        visible = f"{record['argv']} {record['command']}"
        require("poison" not in visible and " su " not in visible, f"a poisoned selector reached {visible}")
    require("H-NOT-WORKING h-nonroot.invalid No credential set worked for 'h-nonroot.invalid': "
            "h-nonroot (rounds 1, not-elevated)" in run.log, "non-root login without become won")
    for name in ("h-sudo", "h-sudo-defaults", "h-doas", "h-doas-user", "h-pfexec", "h-root", "h-plain"):
        require(f"H-WINNER {name}" in run.log, f"{name} did not win")
    readiness = [c for c in run.ssh(mode="exec") if c["command"] == "echo ready"]
    require(len(readiness) == 7 and not any(word in c["command"] for c in readiness
                                            for word in ("sudo", "doas", "pfexec", "BECOME-SUCCESS")),
            f"host_readiness probes {[c['command'] for c in readiness]}")
    lines.append("host_readiness after resolution: 7 unescalated 'echo ready' probes under play become: true")

    for name in ("environment-sources", "ini-sources"):
        plain = evidence[name]
        for address in ("192.0.2.22", "192.0.2.23", "192.0.2.25"):
            command = probe_command(plain, address)
            require(re.match(SHAPES[address], command), f"{name} {address} probe command {command!r}")
        require(not any("poison" in f"{r['argv']} {r['command']}" for r in plain.records["ssh"]),
                f"{name}: a poisoned selector reached an attempt")
        lines.append(f"{name}: sudo/doas/pfexec omitted-field shapes unchanged; no poison in any attempt")

    switch = evidence["switch"]
    require("H-SWITCH-REFUSED h-force-true.invalid PROCESS | Require The Effective POSIX Become Switch"
            in switch.log, "include parameter forcing become true was not refused")
    checks = switch.task("Require The Effective POSIX Become Switch")
    require(any("h-force-false: effective ansible_become does not match the POSIX probe before traffic" in block
                and "fatal: [h-force-false.invalid]" in block for block in checks),
            "role parameter forcing become false was not refused")
    require(not switch.records["ssh"], "a forced switch produced probe traffic")
    lines.append("switch: include parameter (true) and role parameter (false) failed at the effective-switch "
                 "check; zero ssh records")

    adversarial = evidence["adversarial"]
    refusal = next(m for m in adversarial.messages() if m.startswith("H-REFUSED"))
    for name, reason in ADVERSARIAL.items():
        require(f"{name}: {reason}" in refusal, f"{name} not refused with {reason!r}")
    require(not adversarial.records["ssh"], "an adversarial set produced traffic")
    lines.append(f"adversarial: {len(ADVERSARIAL)} sets refused by name and rule before traffic")
    return lines
