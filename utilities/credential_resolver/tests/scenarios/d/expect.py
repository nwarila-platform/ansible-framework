"""d. two resolutions with a floor: the second call probes again and rejects the old boot; canaries in
every member of every non-plumbing SSH and WinRM group at three lower precedence levels never reach an
attempt, nor does the user or password of the SSH attempt just before a password-less WinRM attempt; a
set's value fills every member of its group; a set naming ansible_host leaves inventory_hostname
untouched; a losing attempt's pins do not outlive it within its plugin and another plugin's keys stay
as documented; an unnamed WinRM pass-through argument reaches pywinrm as pywinrm's default; after the
second invocation a pdq_deploy-shaped runas block escalates with its own settings."""
import hashlib
import json

RUNS = [{"name": "floor", "env": {"ANSIBLE_SSH_RETRIES": "2", "ANSIBLE_SSH_PASSWORD_MECHANISM": "sshpass"}}]
CANARIES = ("D-GROUP", "D-HOST", "D-PLAY", "/poison/")
FIXTURES = "utilities/credential_resolver/tests/fixtures"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def check(evidence, require):
    run = evidence["floor"]
    lines = []

    calls = run.ssh(mode="exec")
    users = [c["user"].split("-IDENTITY")[0] for c in calls]
    require(users == ["d-ssh-password"] + ["d-ssh-key"] * 3 + ["d-ssh-password"] + ["d-ssh-key"] * 3,
            f"ssh attempts {users}")
    require(all(c["rc"] == 255 for c in calls), "an SSH attempt was accepted")
    for call in calls:
        if call["user"].startswith("d-ssh-password"):
            require(call["askpass"]["armed"] and "PubkeyAuthentication=no" in call["argv"],
                    "the password attempt did not submit through askpass")
        else:
            require(call["effective"]["identityfile"] == [f"{FIXTURES}/id_stub"] and not call["askpass"]["armed"],
                    f"key attempt identities {call['effective'].get('identityfile')}")
    lines.append(f"ssh attempts per invocation: password once (its pinned retries 0), then after the WinRM "
                 f"certificate attempt the key 1 + 2 retries (the baseline ANSIBLE_SSH_RETRIES=2, not the "
                 f"password attempt's 0): {users}")

    protocols = run.of("winrm", kind="Protocol")
    summary = [(p["endpoint"], p["transport"], p["username"], p["password_given"], p["read_timeout_sec"],
                p["send_cbt"]) for p in protocols]
    certificate = ("https://192.0.2.6:5986/wsman", "certificate", "", False, 33, True)
    old = ("http://192.0.2.6:5985/wsman", "ntlm", "d-old-IDENTITY-CANARY", True, 41, False)
    new = ("http://192.0.2.16:5985/wsman", "ntlm", "d-new-IDENTITY-CANARY", True, 33, True)
    require(summary == [certificate, old, certificate, old, new, new], f"Protocol sequence {summary}")
    passwords = {"d-old-IDENTITY-CANARY": digest("PASSWORD-SECRET-CANARY-D-OLD"),
                 "d-new-IDENTITY-CANARY": digest("PASSWORD-SECRET-CANARY-D-NEW"), "": digest("")}
    for protocol in protocols:
        require("construction_error" not in protocol, f"pywinrm refused its arguments: {protocol}")
        require(protocol["password_sha256"] == passwords[protocol["username"]],
                "a Protocol received a password other than its set's")
        require(protocol["message_encryption"] == "always" and protocol["operation_timeout_sec"] == 20
                and protocol["ca_trust_path"] == "legacy_requests", f"Protocol arguments {protocol}")
        certificate_set = protocol["transport"] == "certificate"
        require((protocol["cert_pem"], protocol["cert_key_pem"])
                == ((f"{FIXTURES}/client.pem", f"{FIXTURES}/client-key.pem") if certificate_set else (None, None)),
                f"certificate arguments {protocol}")
    lines.append("password-less winrm_certificate directly after the SSH password attempt: username '' and no "
                 "password, under inventory/play ansible_ssh_pass and ansible_ssh_user canaries and remote_user "
                 "poison-config-user")
    lines.append("d-new's unnamed send_cbt reached pywinrm as its default True and its read timeout as the "
                 "host baseline 33; d-new named ansible_host 192.0.2.16")

    commands = [r["script"] for r in run.of("winrm", kind="run_command")]
    require(len(commands) == 4 and "LastBootUpTime" not in commands[0]
            and all("LastBootUpTime" in c for c in commands[1:3]) and "d-ordinary" in commands[3],
            f"probe commands {commands}")

    records = [{k: v for k, v in r.items() if k != "environment"}
               for kind in ("ssh", "winrm") for r in run.records[kind]]
    leaked = [r for r in records if any(canary in json.dumps(r) for canary in CANARIES)]
    require(not leaked, f"a lower-precedence canary reached an attempt: {leaked[:1]}")

    require("D-FIRST d-old" in run.log, "first resolution winner")
    second = [m for m in run.messages() if m.startswith("D-SECOND d-new ")]
    require(len(second) == 1, "second resolution winner")
    observations = json.loads(second[0].split(" ", 2)[2].replace('\\"', '"'))
    categories = {name: value["category"] for name, value in observations.items()}
    require(categories["d-old"] == "boot-floor" and categories["d-new"] == "worked"
            and categories["d-certificate"] == "credentials-rejected", f"second resolution {categories}")
    for name in ("d-old", "d-new"):
        require(f"'d-windows.invalid' works as '{name}' (winrm_ntlm, user '{name}-IDENTITY-CANARY')" in run.log,
                f"{name} success line")
    require("D-KEYS-VERIFIED d-windows.invalid winrm" in run.log, "the documented keys after the walk")
    lines += [
        "first probe command has no LastBootUpTime; both second-call probes carry it",
        f"second call categories {categories}",
        "no D-GROUP/D-HOST/D-PLAY or /poison/ canary in any SSH or WinRM record",
        "after the walk: the winner's aliases, ansible_connection 'winrm', ansible_ssh_pass '', the "
        "certificate selectors reset by the winner; the losing SSH attempt's keys stay "
        "(ansible_ssh_user, ansible_ssh_args, retries 2, mechanism sshpass); inventory_hostname unchanged",
    ]

    runas = run.become("d-windows.invalid")
    expected = {"enabled": True, "plugin": "ansible.builtin.runas", "user": "D-RUNAS-USER",
                "flags": "logon_type=batch", "password_sha256": digest("RUNAS-PASSWORD-SECRET-CANARY-D")}
    require(len(runas) == 1 and all(runas[0].get(k) == v for k, v in expected.items()),
            f"the runas block did not keep its own escalation: {runas}")
    lines.append(f"runas block after the second invocation: switch on, {runas[0]['plugin']}, user "
                 f"{runas[0]['user']}, flags {runas[0]['flags']}, its own password (digest matches)")
    return lines
