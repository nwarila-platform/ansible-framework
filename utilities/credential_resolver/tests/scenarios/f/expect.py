"""f. SSH isolation: each profile's argv starts with its prefix; ssh -G of each attempt lists exactly
the set's identities under poisoned user and system configurations and conflicting caller scalars;
identity and control-path options in any argument string are refused, while the default
ControlMaster/ControlPersist ssh_args stay accepted; password attempts arm one askpass segment and
never retry; PKCS#11, agent/FIDO .pub, certificate and key-content sets; an encrypted key file fails
fast under BatchMode; key content in PEM format is refused before traffic."""

FIXTURES = "utilities/credential_resolver/tests/fixtures"
SYSTEM_CONFIG = """EnableSSHKeysign yes
Host *
    IdentityFile /poison/system-identity
    CertificateFile /poison/system-certificate
    PKCS11Provider /poison/system-provider.so
    User poison-system-config-user
    BatchMode yes
    PreferredAuthentications keyboard-interactive
    IdentitiesOnly no
"""
USER_SSH = {
    "config": "Host *\n    IdentityFile ~/.ssh/poison-user-identity\n"
              "    CertificateFile ~/.ssh/poison-user-certificate\n    User poison-user-config-user\n"
              "    BatchMode yes\n    IdentitiesOnly no\n",
    "id_ed25519": "PLAIN-DEFAULT-IDENTITY-PLACEHOLDER\n",
    "id_rsa": "PLAIN-DEFAULT-IDENTITY-PLACEHOLDER\n",
}
RUNS = [
    {
        "name": "forms",
        "global_ssh_config": SYSTEM_CONFIG,
        "user_ssh": USER_SSH,
        "env": {"ANSIBLE_SSH_PASSWORD_MECHANISM": "sshpass", "ANSIBLE_SSH_RETRIES": "3",
                "ANSIBLE_SSH_AGENT": "auto"},
        "files": {"encrypted-key": "ENCRYPTED-KEY-FIXTURE\n"},
        "keys": {"content-key": ""},
    },
    {"name": "identity-options", "inventory": "inventory-identity-options.yml",
     "playbook": "identity-options.yml"},
    {"name": "keysign-equals-spelling", "inventory": "inventory-hostbased.yml",
     "global_ssh_config": "EnableSSHKeysign=yes\n"},
    {"name": "key-content-format", "env": {"ANSIBLE_SSH_AGENT": "auto"}, "keys": {"content-key": ""},
     "key_format": "PEM", "args": ["--limit", "f-content.invalid"], "expected_rc": 2},
]
PEM_REFUSED = ("Credential resolution validation failed for 'f-content.invalid': f-content: rule 2 requires "
               "OpenSSH-format key content, the only format core loads\"")
BASELINE = ["-C", "-o", "ControlMaster=auto", "-o", "ControlPersist=60s", "-o", "BatchMode=yes",
            "-o", "PreferredAuthentications=keyboard-interactive", "-o", "IdentitiesOnly=no",
            "-o", "PubkeyAuthentication=yes", "-o", "PasswordAuthentication=yes",
            "-o", "GSSAPIAuthentication=no", "-o", "HostbasedAuthentication=no"]
PUBLICKEY = ["-F", "/dev/null", "-o", "PreferredAuthentications=publickey", "-o", "IdentitiesOnly=yes"]
PREFIX = {
    "key": PUBLICKEY + ["-o", "BatchMode=yes"],
    "pkcs11": ["-o", "KbdInteractiveAuthentication=no", "-o", "PreferredAuthentications=publickey",
               "-o", "PasswordAuthentication=no", "-o", f"PKCS11Provider={FIXTURES}/provider.so"]
              + PUBLICKEY + ["-o", "BatchMode=no"],
    "certificate": PUBLICKEY + ["-o", "BatchMode=yes", "-o", f"CertificateFile={FIXTURES}/cert_stub.pub"],
    "password": ["-F", "/dev/null", "-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no",
                 "-o", "BatchMode=no"],
    "gssapi": ["-F", "/dev/null", "-o", "PreferredAuthentications=gssapi-with-mic",
               "-o", "GSSAPIAuthentication=yes", "-o", "BatchMode=yes"],
    "hostbased": ["-F", "/dev/null", "-o", "PreferredAuthentications=hostbased",
                  "-o", "HostbasedAuthentication=yes", "-o", "EnableSSHKeysign=yes", "-o", "BatchMode=yes"],
}
EXPECTED = {
    "192.0.2.9": ("key", {"identityfile": [f"{FIXTURES}/id_stub"], "identitiesonly": ["yes"],
                          "batchmode": ["yes"], "preferredauthentications": ["publickey"]}),
    "192.0.2.11": ("pkcs11", {"identityfile": [f"{FIXTURES}/id_stub.pub"], "identitiesonly": ["yes"],
                              "batchmode": ["no"], "pkcs11provider": [f"{FIXTURES}/provider.so"],
                              "preferredauthentications": ["publickey"]}),
    "192.0.2.12": ("key", {"identityfile": [f"{FIXTURES}/id_stub.pub"], "identitiesonly": ["yes"],
                           "batchmode": ["yes"]}),
    "192.0.2.13": ("certificate", {"identityfile": [f"{FIXTURES}/id_stub"],
                                   "certificatefile": [f"{FIXTURES}/cert_stub.pub"], "batchmode": ["yes"]}),
    "192.0.2.14": ("gssapi", {"preferredauthentications": ["gssapi-with-mic"],
                              "gssapiauthentication": ["yes"], "batchmode": ["yes"]}),
    "192.0.2.15": ("hostbased", {"preferredauthentications": ["hostbased"],
                                 "hostbasedauthentication": ["yes"], "enablesshkeysign": ["yes"],
                                 "batchmode": ["yes"]}),
}


def check(evidence, require):
    lines = []
    forms = evidence["forms"]
    for name in ("f-key", "f-password-right", "f-pkcs11", "f-fido", "f-certificate", "f-gssapi",
                 "f-hostbased", "f-after-encrypted", "f-content"):
        require(f"F-WINNER {name}" in forms.log, f"{name} did not win")
    probes = forms.ssh(mode="exec")
    for probe in probes:
        require('ControlPath="none"' in probe["argv"], f"{probe['user']} probe is multiplexed")
        require("/poison/system-identity" in probe["unconfined"]["identityfile"]
                and "~/.ssh/poison-user-identity" in probe["unconfined"]["identityfile"],
                "the poisoned configurations were not live")
    for address, (profile, settings) in EXPECTED.items():
        calls = forms.ssh(mode="exec", host=address)
        require(len(calls) == 1, f"{address}: {len(calls)} probes")
        call = calls[0]
        prefix = PREFIX[profile] + BASELINE
        require(call["argv"][:len(prefix)] == prefix, f"{address} argv {call['argv'][:len(prefix)]}")
        for key, value in settings.items():
            require(call["effective"].get(key) == value,
                    f"{address} {key}={call['effective'].get(key)} expected {value}")
        for key in ("identityfile", "certificatefile"):
            require(not any("poison" in v for v in call["effective"].get(key, [])), f"{address} poisoned {key}")
        lines.append(f"{profile} {address}: argv prefix ok; effective {settings}")
    pkcs11 = forms.ssh(host="192.0.2.11", mode="exec")[0]
    require(pkcs11["askpass"]["armed"] and pkcs11["askpass"]["mode"] == "0o600", "PKCS#11 PIN not via askpass")
    require(pkcs11["argv"].index("-F") == 8, "the PKCS#11 preamble is not the only thing ahead of the prefix")

    passwords = forms.ssh(host="192.0.2.10", mode="exec")
    require([p["rc"] for p in passwords] == [255, 0], f"password attempts {[p['rc'] for p in passwords]}")
    for probe in passwords:
        require(probe["argv"][:len(PREFIX["password"] + BASELINE)] == PREFIX["password"] + BASELINE,
                "password argv prefix")
        require(probe["askpass"]["armed"] and probe["askpass"]["mode"] == "0o600", "password askpass")
        require(probe["effective"]["batchmode"] == ["no"] and probe["effective"]["pubkeyauthentication"] == ["false"]
                and probe["effective"]["numberofpasswordprompts"] == ["1"], "password effective settings")
        require(probe["environment"]["ANSIBLE_SSH_RETRIES"] == "<set by the run>"
                and probe["environment"]["ANSIBLE_SSH_PASSWORD_MECHANISM"] == "<set by the run>",
                "poisons not live")
    require(passwords[0]["askpass"]["sha256"] != passwords[1]["askpass"]["sha256"], "same segment content")
    lines.append("password: wrong then right, one exec each (no retries under ANSIBLE_SSH_RETRIES=3), "
                 "askpass armed 0o600 each, BatchMode no under three BatchMode=yes poisons, sshpass poisons ignored")

    encrypted = forms.ssh(host="192.0.2.16", mode="exec", user="f-encrypted-IDENTITY-CANARY")
    after = forms.ssh(host="192.0.2.16", mode="exec", user="f-after-encrypted-IDENTITY-CANARY")
    require(len(encrypted) == 4, f"encrypted key invocations {len(encrypted)} (one plus three plumbing retries)")
    for call in encrypted:
        require(call["passphrase_prompt"] == "refused-by-batchmode" and call["rc"] == 255
                and call["elapsed"] < 5 and call["effective"]["batchmode"] == ["yes"],
                f"encrypted key {call.get('passphrase_prompt')} {call['elapsed']}")
    require(len(after) == 1 and after[0]["rc"] == 0, "the set after the encrypted key did not run")
    lines.append(f"encrypted key file: every invocation (1 + 3 ANSIBLE_SSH_RETRIES) failed without a prompt "
                 f"in <= {max(c['elapsed'] for c in encrypted)}s under BatchMode yes; the next set won")

    content = forms.ssh(host="192.0.2.17", mode="exec")
    require(len(content) == 1, "key-content probe count")
    identities = content[0]["effective"]["identityfile"]
    require(len(identities) == 1 and identities[0].endswith(".pub") and "/local/" in identities[0]
            and content[0]["effective"]["identitiesonly"] == ["yes"]
            and content[0]["environment"].get("SSH_AUTH_SOCK"), f"key content identities {identities}")
    lines.append(f"key content: agent-held key only, identityfile={identities}")

    refusals = evidence["identity-options"]
    messages = [m for m in refusals.messages() if m.startswith("F-REFUSED")]
    sets = next(m for m in messages if m.startswith("F-REFUSED f3-sets.invalid"))
    rule = "rule 3 found an identity or control-path option in effective SSH arguments"
    for index in range(1, 17):
        require(f"f3-set-{index}: {rule}" in sets, f"f3-set-{index} not refused")
    for host in ("f3-base-ssh-args", "f3-base-common", "f3-base-extra", "f3-base-scp", "f3-base-sftp",
                 "f3-base-control-path", "f3-base-control-socket"):
        require(any(m.startswith(f"F-REFUSED {host}.invalid") and f"f3-clean: {rule}" in m for m in messages),
                f"{host} not refused")
    require(not refusals.records["ssh"], "a refused identity option produced ssh traffic")
    lines.append("rule 3: 16 set-level forms (IdentityFile =/space/attached/lowercase, IdentityAgent, "
                 "CertificateFile, PKCS11Provider, SecurityKeyProvider, -i, -i<path>, -F, -F<path>, "
                 "ControlPath =/space, -S, -S<path>) and 7 baseline carriers (including ControlPath in "
                 "ssh_args and -S in common args) refused; zero ssh records")

    equals = evidence["keysign-equals-spelling"]
    require("F-WINNER f-hostbased" in equals.log and len(equals.ssh(mode="exec")) == 1,
            "EnableSSHKeysign=yes spelling not accepted")
    lines.append("hostbased: global 'EnableSSHKeysign yes' and 'EnableSSHKeysign=yes' both accepted")

    pem = evidence["key-content-format"]
    content = (pem.directory / "input" / "content-key").read_bytes()
    require(content and b"OPENSSH" not in content, "the generated key content is in OpenSSH format")
    require(PEM_REFUSED in pem.log and not pem.traffic(), "PEM key content was not refused before traffic")
    lines.append("key-content-format: RSA key content in PEM format refused before traffic, naming the OpenSSH "
                 "format core requires")
    return lines
