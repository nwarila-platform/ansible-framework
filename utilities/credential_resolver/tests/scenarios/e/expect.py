"""e. lower sources suppressed: remote_user = root, ANSIBLE_PRIVATE_KEY_FILE, inventory key files and
users, and ambient WinRM/PSRP certificate pairs never reach an attempt whose set did not name them; the
user-less WinRM and PSRP certificate attempts send an empty user, not remote_user, and no password
under an inventory ansible_ssh_pass."""

RUNS = [{
    "name": "lower-sources",
    "config": {"defaults": {"remote_user": "root"}},
    "env": {"ANSIBLE_PRIVATE_KEY_FILE": "/poison/environment-key"},
}]
POISON = ("/poison/", "poisoned-inventory-user")


def check(evidence, require):
    run = evidence["lower-sources"]
    for name in ("e-ssh-password", "e-ssh-key", "e-winrm-ntlm", "e-winrm-certificate", "e-psrp-certificate"):
        require(f"E-WINNER {name}" in run.log, f"{name} did not resolve")
    password = run.ssh(host="192.0.2.7", mode="exec")
    key = run.ssh(host="192.0.2.8", mode="exec")
    require(len(password) == 1 and len(key) == 1, "one probe per SSH host")
    password, key = password[0], key[0]
    require(password["user"] == "e-ssh-password-IDENTITY-CANARY" and key["user"] == "e-ssh-key-IDENTITY-CANARY",
            "an SSH attempt ran as a lower-source user")
    require(not any("IdentityFile" in a for a in password["argv"]), "the password attempt names an identity")
    require(password["effective"]["pubkeyauthentication"] == ["false"], "the password attempt allows public keys")
    require(key["effective"]["identityfile"] == ["utilities/credential_resolver/tests/fixtures/id_stub"],
            f"key attempt identities {key['effective']['identityfile']}")
    ntlm = run.of("winrm", kind="Protocol", endpoint="http://192.0.2.9:5985/wsman")
    certificate = run.of("winrm", kind="Protocol", endpoint="https://192.0.2.10:5986/wsman")
    require(len(ntlm) == 1 and ntlm[0]["cert_pem"] is None and ntlm[0]["cert_key_pem"] is None
            and ntlm[0]["username"] == "e-winrm-ntlm-IDENTITY-CANARY", f"NTLM Protocol {ntlm}")
    require(len(certificate) == 1 and certificate[0]["transport"] == "certificate"
            and certificate[0]["cert_pem"] == "utilities/credential_resolver/tests/fixtures/client.pem"
            and certificate[0]["username"] == "" and not certificate[0]["password_given"],
            f"certificate Protocol {certificate}")
    wsman = [r for r in run.of("psrp", kind="WSMan") if r["arguments"]["server"] == "192.0.2.11"]
    require(len(wsman) == 1 and wsman[0]["arguments"]["auth"] == "certificate"
            and wsman[0]["arguments"]["certificate_pem"].endswith("/tests/fixtures/client.pem")
            and wsman[0]["arguments"]["username"] == "" and wsman[0]["arguments"]["password_bytes"] == 0,
            f"PSRP WSMan {wsman}")
    records = [r for kind in ("ssh", "winrm", "psrp") for r in run.records[kind]]
    for record in records:
        visible = {k: v for k, v in record.items() if k != "environment"}
        require(not any(p in str(visible) for p in POISON), f"a lower source reached an attempt: {visible}")
    require(all(r["user"] != "root" for r in run.records["ssh"]), "remote_user = root reached an SSH attempt")
    require(all(r["environment"].get("ANSIBLE_PRIVATE_KEY_FILE") == "<set by the run>"
                for r in run.records["ssh"]), "the environment poison was not live")
    return [
        f"ssh password attempt: user={password['user']} no IdentityFile, pubkeyauthentication=false",
        f"ssh key attempt: identityfile={key['effective']['identityfile']}",
        f"winrm ntlm: cert_pem={ntlm[0]['cert_pem']} cert_key_pem={ntlm[0]['cert_key_pem']}",
        f"winrm certificate: cert_pem={certificate[0]['cert_pem']} (ambient pair absent)",
        f"psrp certificate: auth={wsman[0]['arguments']['auth']} (ambient pair absent)",
        "no /poison/ path or inventory user in any attempt record; no SSH attempt ran as root",
        "user-less attempts under remote_user = root and an inventory ansible_ssh_pass: winrm_certificate "
        f"username {certificate[0]['username']!r} and no password, psrp_certificate username "
        f"{wsman[0]['arguments']['username']!r} and {wsman[0]['arguments']['password_bytes']} password bytes",
    ]
