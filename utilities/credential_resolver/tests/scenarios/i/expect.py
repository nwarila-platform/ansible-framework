"""i. baseline capture and validation: play-variable and configuration-only plumbing are captured and
the second invocation reuses the first baseline; every rule 0-8 refuses before any stub traffic; a
harmless plumbing extra variable is accepted; rule 7 refuses become extra variables only when a set
carries a become block, and a fleet without one keeps its runas password extra variable; role and
include parameters colliding with a written key fail the post-apply check before traffic."""
import hashlib

SINGLE = {"inventory": "inventory-single.yml", "playbook": "refusal.yml"}
BECOME = {"inventory": "inventory-become.yml", "playbook": "refusal.yml"}
EXTRA_BECOME_PASSWORD = "EXTRA-BECOME-SECRET-CANARY-I"
PASSWORD_FILE = {"password": "FILE-PASSWORD-SECRET-CANARY\n"}
KEY_FILE = {"cli-key": "PLAIN-PATH-FIXTURE-NOT-A-CREDENTIAL\n"}
RUNS = [
    {"name": "baseline",
     "config": {"defaults": {"timeout": "23"},
                "ssh_connection": {"ssh_args": "-C -o ControlMaster=auto -o ControlPersist=45s "
                                               "-o ServerAliveCountMax=7"}}},
    {"name": "rule0-debug-environment", **SINGLE, "env": {"ANSIBLE_DEBUG": "1"}},
    {"name": "rule0-debug-configuration", **SINGLE, "config": {"defaults": {"debug": "True"}}},
    {"name": "rule0-strategy-environment", **SINGLE, "env": {"ANSIBLE_STRATEGY": "free"}},
    {"name": "rule0-strategy-configuration", **SINGLE, "config": {"defaults": {"strategy": "free"}}},
    {"name": "shape", "inventory": "inventory-shape.yml", "playbook": "refusal.yml"},
    {"name": "hosts", "inventory": "inventory-hosts.yml", "playbook": "hosts.yml",
     "table": {"klist": {"rc": 1}}, "keys": {"agent-key": "", "passphrase-key": "KEY-PASSPHRASE-SECRET-CANARY-I6"},
     "expected_rc": 2},
    {"name": "rule7-extra-written", **SINGLE, "args": ["-e", "ansible_user=i-single-IDENTITY-CANARY"]},
    {"name": "rule7-extra-alias", **SINGLE, "args": ["-e", "ansible_ssh_pass=EXTRA-VAR-SECRET-CANARY"]},
    {"name": "rule7-extra-become", **BECOME, "args": ["-e", "ansible_become=false"]},
    {"name": "rule7-extra-become-alias", **BECOME, "args": ["-e", "ansible_sudo_flags=-H"]},
    {"name": "rule7-become-extra-without-block", "inventory": "inventory-runas.yml", "playbook": "runas.yml",
     "args": ["-e", f"ansible_become_password={EXTRA_BECOME_PASSWORD}"]},
    {"name": "rule7-extra-pin", **SINGLE, "args": ["-e", "ansible_connection=ssh"]},
    {"name": "rule7-extra-harmless", **SINGLE, "args": ["-e", "ansible_ssh_timeout=13"]},
    {"name": "rule7-ask-pass", **SINGLE, "args": ["--ask-pass"], "stdin": "ASK-PASS-SECRET-CANARY\n"},
    {"name": "rule7-ask-become-pass", **SINGLE, "args": ["--ask-become-pass"],
     "stdin": "ASK-BECOME-PASS-SECRET-CANARY\n"},
    {"name": "rule7-private-key", **SINGLE, "args": ["--private-key", "{input}/cli-key"], "files": KEY_FILE},
    {"name": "rule7-private-key-abbreviated", **SINGLE, "args": ["--private-k", "{input}/cli-key"],
     "files": KEY_FILE},
    {"name": "rule7-key-file", **SINGLE, "args": ["--key-file={input}/cli-key"], "files": KEY_FILE},
    {"name": "rule7-connection-password-file", **SINGLE,
     "args": ["--connection-password-file", "{input}/password"], "files": PASSWORD_FILE},
    {"name": "rule7-become-password-file", **SINGLE,
     "args": ["--become-password-file", "{input}/password"], "files": PASSWORD_FILE},
    {"name": "rule7-connection-password-setting", **SINGLE,
     "env": {"ANSIBLE_CONNECTION_PASSWORD_FILE": "{input}/password"}, "files": PASSWORD_FILE},
    {"name": "rule7-become-password-setting", **SINGLE,
     "env": {"ANSIBLE_BECOME_PASSWORD_FILE": "{input}/password"}, "files": PASSWORD_FILE},
]
RULE0 = "credential_resolver rule 0 requires controller debug mode off and the configured linear strategy"
REFUSED = {
    "rule0-debug-environment": RULE0,
    "rule0-debug-configuration": RULE0,
    "rule0-strategy-environment": RULE0,
    "rule0-strategy-configuration": RULE0,
    "rule7-extra-written": "rule 7 refuses extra variables on ansible_user",
    "rule7-extra-alias": "rule 7 refuses extra variables on ansible_ssh_pass",
    "rule7-extra-pin": "rule 7 refuses extra variables on ansible_connection",
    "rule7-ask-pass": "rule 7 refuses command-line credential flags --ask-pass",
    "rule7-ask-become-pass": "rule 7 refuses command-line credential flags --ask-become-pass",
    "rule7-private-key": "rule 7 refuses command-line credential flags --private-key",
    "rule7-private-key-abbreviated": "rule 7 refuses command-line credential flags --private-key",
    "rule7-key-file": "rule 7 refuses command-line credential flags --private-key",
    "rule7-connection-password-file": "rule 7 refuses command-line credential flags --connection-password-file",
    "rule7-become-password-file": "rule 7 refuses command-line credential flags --become-password-file",
    "rule7-connection-password-setting": "rule 7 requires CONNECTION_PASSWORD_FILE empty",
    "rule7-become-password-setting": "rule 7 requires BECOME_PASSWORD_FILE empty",
}
BECOME_REFUSED = {
    "rule7-extra-become": "rule 7 refuses extra variables on ansible_become",
    "rule7-extra-become-alias": "rule 7 refuses extra variables on ansible_sudo_flags",
}
BOUNDS = ("i-bounds-empty", "i-bounds-string", "i-bounds-rounds", "i-bounds-pause", "i-bounds-budget",
          "i-bounds-elevated", "i-bounds-floor")
SHAPE = {
    "<unnamed>": "rule 1 requires a mapping candidate",
    "extra-field": "rule 1 accepts only name, profile, vars, attempts, account, certificate_file, and become fields",
    "non-string-profile": "rule 1 requires a string profile",
    "non-mapping-vars": "rule 1 requires vars to be a mapping",
    "unknown-profile": "rule 1 names an unknown connection profile",
    "attempts-zero": "rule 1 requires attempts to be a positive integer",
    "attempts-string": "rule 1 requires attempts to be a positive integer",
    "become-not-mapping": "rule 1 requires become to be a mapping",
    "unknown-become": "rule 1 names an unknown become profile",
    "credential_resolver": "rule 1 requires unique candidate names",
    "missing-required": "rule 2 is missing a required variable",
    "empty-required": "rule 2 is missing a required variable",
    "two-key-forms": "rule 2 requires exactly one SSH public-key form",
    "passphrase-without-content": "rule 2 permits a passphrase only with key content",
    "pkcs11-without-pin": "rule 2 requires exactly one SSH public-key form",
    "kerberos-password-and-cache": "rule 2 requires managed-password XOR manual-cache Kerberos",
    "aws-two-targets": "rule 2 requires one aws_ssm target",
    "foreign-variable": "rule 2 contains a non-canonical or profile-incompatible variable",
    "alias-variable": "rule 2 contains a non-canonical or profile-incompatible variable",
    "certificate-on-winrm": "rule 5 permits certificate_file only for ssh_publickey",
    "password-without-account": "rule 5 requires account for a login password",
    "account-not-string": "rule 1 requires a string account id",
}
HOSTS = {
    "i-rule3": "i-rule3: rule 3 found an identity or control-path option in effective SSH arguments",
    "i-rule4": "i-rule4: rule 4 requires HTTPS",
    "i-rule6-hostbased": "i-rule6-hostbased: rule 6 missing controller dependency hostbased",
    "i-rule6-agent": "i-rule6-agent: rule 6 requires SSH agent support for key content",
    "i-rule6-bcrypt": "i-rule6-bcrypt: rule 6 missing controller dependency bcrypt",
    "i-rule6-ticket": "i-rule6-ticket: rule 6 missing controller dependency gssapi_ticket",
    "i-rule8": "i-rule8.invalid: rule 8 permits a boot floor only on Windows",
}
COLLISIONS = {
    "i-include-parameter": "ansible_user",
    "i-role-parameter": "ansible_password",
}
CONFIGURED = ["-C", "-o", "ControlMaster=auto", "-o", "ControlPersist=45s", "-o", "ServerAliveCountMax=7"]
PREFIX = ["-F", "/dev/null", "-o", "PreferredAuthentications=publickey", "-o", "IdentitiesOnly=yes",
          "-o", "BatchMode=yes"]


def refused(run, host):
    return [m for m in run.messages() if m.startswith(f"I-REFUSED {host}.invalid ")]


def check(evidence, require):
    lines = []
    baseline = evidence["baseline"]
    for address, host, expected in (("192.0.2.40", "i-play", "17"), ("192.0.2.41", "i-config", "23")):
        calls = baseline.ssh(mode="exec", host=address)
        users = [c["user"].split("-IDENTITY")[0] for c in calls]
        timeouts = [next(a for a in c["argv"] if a.startswith("ConnectTimeout=")).split("=")[1] for c in calls]
        require(users == ["i-a", "i-b", "i-a", "i-b"], f"{host} order {users}")
        require(timeouts == ["11", expected, "11", expected], f"{host} ConnectTimeout {timeouts}")
        for call in calls:
            require(call["argv"][:len(PREFIX + CONFIGURED)] == PREFIX + CONFIGURED and call["argv"].count("-F") == 1,
                    f"{host} argv {call['argv'][:16]}")
        require(f"I-BASELINE {host}.invalid i-b" in baseline.log, f"{host} winner")
        lines.append(f"{host}: ConnectTimeout per attempt {timeouts} (i-a names 11; i-b gets the captured "
                     f"{'play variable' if expected == '17' else 'configured value'} {expected} in both "
                     "invocations, not the 99 set between them); argv = prefix once + configured ssh_args")

    for name, message in REFUSED.items():
        run = evidence[name]
        require(any(message in m for m in refused(run, "i-single")), f"{name} not refused with {message!r}")
        require(not run.traffic(), f"{name} produced stub traffic")
    for name, message in BECOME_REFUSED.items():
        run = evidence[name]
        require(any(message in m for m in refused(run, "i-become")), f"{name} not refused with {message!r}")
        require(not run.traffic(), f"{name} produced stub traffic")
    fleet = evidence["rule7-become-extra-without-block"]
    runas = fleet.become("i-runas.invalid")
    require("'i-runas.invalid' works as 'i-runas'" in fleet.log and len(runas) == 1 and runas[0]["enabled"]
            and runas[0]["password_sha256"] == hashlib.sha256(EXTRA_BECOME_PASSWORD.encode()).hexdigest(),
            f"the fleet's own become extra variables were not accepted and used: {runas}")
    lines.append("rule 7 with a become-block set: '-e ansible_become=false' and '-e ansible_sudo_flags=-H' refused "
                 "before traffic; without one, '-e ansible_become_password=...' is accepted, the set resolves, "
                 "and the later runas block escalates with that password")
    debug = evidence["rule0-debug-environment"]
    require(": starting run" in debug.log and "SECRET-CANARY" not in debug.log,
            "debug output was not active or carried a secret canary")
    lines.append(f"rule 0: ANSIBLE_DEBUG=1 produced {debug.log.count(chr(10))} lines of core debug output and "
                 "the refusal came before any secret canary appeared")
    lines.append(f"rules 0 and 7: {len(REFUSED)} runs refused before traffic "
                 "(debug env/ini, non-linear strategy env/ini, extra vars on written/alias/pin, "
                 "--ask-pass, --ask-become-pass, --private-key, --private-k, --key-file=, "
                 "--connection-password-file, --become-password-file, both password-file settings)")
    harmless = evidence["rule7-extra-harmless"]
    require("I-ACCEPTED i-single.invalid i-single" in harmless.log
            and "ConnectTimeout=13" in harmless.ssh(mode="exec")[0]["argv"], "harmless plumbing extra var")
    lines.append("rule 7: '-e ansible_ssh_timeout=13' accepted; the probe carried ConnectTimeout=13")

    shape = evidence["shape"]
    for host in BOUNDS:
        require(any("rule 1 requires a non-empty candidate list, positive integer rounds" in m
                    for m in refused(shape, host)), f"{host} bounds not refused")
    messages = " ".join(refused(shape, "i-shape"))
    for name, reason in SHAPE.items():
        require(f"{name}: {reason}" in messages, f"shape {name} not refused with {reason!r}")
    require(not shape.traffic(), "a shape refusal produced traffic")
    lines.append(f"rules 1, 2 and 5: {len(BOUNDS)} bound violations and {len(SHAPE)} malformed sets refused")

    hosts = evidence["hosts"]
    for host, message in HOSTS.items():
        require(any(message in m for m in refused(hosts, host)), f"{host} not refused with {message!r}")
    checks = hosts.task("Require Effective Attempt Values")
    for host, key in COLLISIONS.items():
        require(any(f"{host}: effective-value check failed for {key} before probe traffic" in block
                    and f"[{host}.invalid]" in block for block in checks), f"{host} collision not refused")
    require(not hosts.records["ssh"] and not hosts.records["winrm"], "a refused host produced traffic")
    lines.append("rules 3, 4, 6 (real hostbased and bcrypt checks, agent none, no ticket), 8, include and role "
                 "parameter collisions refused before traffic")
    return lines
