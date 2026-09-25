"""g. WinRM and PSRP: one Protocol/WSMan per attempt and fresh per task with exactly the profile's
transport/auth and credential arguments; certificate without a user; manual Kerberos without a
password or kinit; Basic/certificate over HTTPS accepted and over HTTP refused; the encryption floor
for NTLM/Kerberos/PSRP over HTTP, including HTTP derived from port 5985; pass-through arguments one set
names reach another set's pywinrm as pywinrm's defaults (the stub applies pywinrm's argument checks); a
WinRM and a PSRP winner with no platform or shell hint are classified as Windows by host_readiness and
os_bootstrap."""
import hashlib

FIXTURES = "utilities/credential_resolver/tests/fixtures"
RUNS = [
    {"name": "profiles"},
    {"name": "floors", "inventory": "inventory-floors.yml", "playbook": "floors.yml"},
    {"name": "classification", "inventory": "inventory-classify.yml", "playbook": "classify.yml"},
]
HTTPS = "rule 4 requires HTTPS"
ENCRYPTED = "rule 4 requires message_encryption=always over HTTP"
REFUSALS = {
    "g-basic-http": ("basic-http", HTTPS),
    "g-basic-port": ("basic-port", HTTPS),
    "g-certificate-http": ("certificate-http", HTTPS),
    "g-ntlm-http": ("ntlm-http", ENCRYPTED),
    "g-ntlm-port": ("ntlm-port", ENCRYPTED),
    "g-kerberos-http": ("kerberos-http", ENCRYPTED),
    "g-psrp-kerberos-http": ("psrp-kerberos-http", ENCRYPTED),
    "g-psrp-kerberos-port": ("psrp-kerberos-port", ENCRYPTED),
    "g-psrp-certificate-http": ("psrp-certificate-http", HTTPS),
    "g-psrp-certificate-port": ("psrp-certificate-port", HTTPS),
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def check(evidence, require):
    lines = []
    run = evidence["profiles"]
    for name in ("g-ntlm", "g-kerberos-manual", "g-basic", "g-certificate", "g-psrp-kerberos", "g-psrp-certificate",
                 "g-pass-certificate"):
        require(f"G-WINNER {name}" in run.log, f"{name} did not win")
    require(not [p for p in run.of("winrm", kind="Protocol") if "construction_error" in p],
            "pywinrm refused a Protocol's arguments")
    winrm = {
        "http://192.0.2.15:5985/wsman": ("ntlm", "g-ntlm-IDENTITY-CANARY", digest("PASSWORD-SECRET-CANARY-GN")),
        "https://192.0.2.16:5986/wsman": ("kerberos", "g-kerberos-IDENTITY-CANARY@TEST.INVALID", digest("")),
        "https://192.0.2.17:5986/wsman": ("basic", "g-basic-IDENTITY-CANARY", digest("PASSWORD-SECRET-CANARY-GB")),
        "https://192.0.2.18:5986/wsman": ("certificate", None, digest("")),
    }
    for endpoint, (transport, user, password) in winrm.items():
        protocols = run.of("winrm", kind="Protocol", endpoint=endpoint)
        require(len(protocols) == 2 and len({p["pid"] for p in protocols}) >= 1,
                f"{endpoint}: {len(protocols)} Protocols (probe and ordinary task expected)")
        for protocol in protocols:
            require((protocol["transport"], protocol["password_sha256"]) == (transport, password),
                    f"{endpoint} transport/password {protocol['transport']}")
            if user is not None:
                require(protocol["username"] == user, f"{endpoint} username {protocol['username']}")
        certificate = transport == "certificate"
        require(all((p["cert_pem"] is not None) == certificate and (p["cert_key_pem"] is not None) == certificate
                    for p in protocols), f"{endpoint} certificate arguments")
        lines.append(f"winrm {transport}: 2 Protocols (probe + ordinary task) at {endpoint}")
    named = run.of("winrm", kind="Protocol", endpoint="https://192.0.2.99:5986/wsman")
    require([p["username"].split("-IDENTITY")[0] for p in named]
            == ["g-named-host-rejected", "g-named-host-accepted", "g-named-host-accepted"],
            f"named-host Protocols {[p['username'] for p in named]}")
    require("'g-ntlm-named-host.invalid' works as 'g-named-host-accepted' (winrm_ntlm, user "
            "'g-named-host-accepted-IDENTITY-CANARY')" in run.log, "named-host success line")
    lines.append("winrm ntlm sets naming ansible_host: the rejected set does not stop the walk, every Protocol "
                 "targets the set's host, and the success line still names the inventory host")
    require(not run.records["kinit"], "manual Kerberos or another profile ran kinit")
    wsman = [r for r in run.of("psrp", kind="WSMan")]
    kerberos = [w["arguments"] for w in wsman if w["arguments"]["server"] == "192.0.2.19"]
    certificate = [w["arguments"] for w in wsman if w["arguments"]["server"] == "192.0.2.20"]
    require(len(kerberos) == 2 and all(a["auth"] == "kerberos" and a["ssl"] is False
                                        and a["encryption"] == "always" and a["password_bytes"] == 0
                                        and a["username"] == "g-psrp-kerberos-IDENTITY-CANARY@TEST.INVALID"
                                        for a in kerberos), f"PSRP Kerberos {kerberos}")
    require(len(certificate) == 2 and all(a["auth"] == "certificate" and a["ssl"] is True
                                           and a["certificate_pem"].endswith("/fixtures/client.pem")
                                           and a["password_bytes"] == 0 for a in certificate),
            f"PSRP certificate {certificate}")
    lines.append("psrp kerberos (http + always) and certificate (https): 2 WSMan each, no password")

    arguments = ("message_encryption", "read_timeout_sec", "operation_timeout_sec", "send_cbt", "ca_trust_path")
    passed = [tuple(p[a] for a in arguments) for p in run.of("winrm", kind="Protocol") if "192.0.2.22" in p["endpoint"]]
    require(passed == [("always", 50, 40, False, "/x/ca-bundle.pem"), ("auto", 30, 20, True, "legacy_requests"),
                       ("auto", 30, 20, True, "legacy_requests")], f"pass-through arguments {passed}")
    lines.append(f"pass-through: g-pass-ntlm names {dict(zip(arguments, passed[0]))}; the certificate winner's probe "
                 f"and ordinary task pass pywinrm's defaults {dict(zip(arguments, passed[1]))} and pywinrm's "
                 "argument checks accept them")

    floors = evidence["floors"]
    messages = [m for m in floors.messages() if m.startswith("G-REFUSED")]
    for host, (name, rule) in REFUSALS.items():
        require(any(m.startswith(f"G-REFUSED {host}.invalid") and f"{name}: {rule}" in m for m in messages),
                f"{host} not refused with {rule}")
    require(not floors.records["winrm"] and not floors.records["psrp"], "a refused floor produced traffic")
    lines.append("floors refused before traffic: " + ", ".join(f"{h}={r.split()[-1]}" for h, (_, r) in REFUSALS.items()))

    classification = evidence["classification"]
    for host, connection in (("g-classify-winrm", "winrm"), ("g-classify-psrp", "psrp")):
        line = (f"G-CLASSIFIED {host}.invalid {connection} windows Windows "
                f"(connection hint ansible_connection={connection})")
        require(line in classification.log, f"{host} was not classified as Windows")
        require(f"G-DISPATCH {host}.invalid windows_server_2025" in classification.log,
                f"{host} was not routed to the Windows bootstrap role")
        lines.append(line)
    scripts = ([r["script"] for r in classification.of("winrm", kind="run_command")]
               + [r["script"] for r in classification.of("psrp", kind="PowerShell.invoke")])
    require(sum("Win32_ComputerSystem" in s for s in scripts) == 2 and not any("sys_vendor" in s for s in scripts),
            f"host_readiness platform probes {scripts}")
    lines.append("classification: ansible_connection published by short name; host_readiness sent its Windows "
                 "platform probe to both hosts and os_bootstrap routed both to windows_server_2025")
    return lines
