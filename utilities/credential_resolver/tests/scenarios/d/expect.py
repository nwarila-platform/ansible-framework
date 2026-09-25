"""d. two resolutions with a floor: the second call probes again and rejects the old boot; canaries in
every member of every non-plumbing group at three lower precedence levels never reach an attempt; a
set's plumbing never reaches another set's attempt; the winner's value fills every member of its group."""
import hashlib

RUNS = [{"name": "floor"}]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def check(evidence, require):
    run = evidence["floor"]
    protocols = run.of("winrm", kind="Protocol")
    summary = [(p["username"], p["read_timeout_sec"], p["send_cbt"]) for p in protocols]
    require(summary == [
        ("d-old-IDENTITY-CANARY", 41, False),
        ("d-old-IDENTITY-CANARY", 41, False),
        ("d-new-IDENTITY-CANARY", 33, None),
        ("d-new-IDENTITY-CANARY", 33, None),
    ], f"Protocol sequence {summary}")
    passwords = {"d-old-IDENTITY-CANARY": "PASSWORD-SECRET-CANARY-D-OLD",
                 "d-new-IDENTITY-CANARY": "PASSWORD-SECRET-CANARY-D-NEW"}
    for protocol in protocols:
        require(protocol["password_sha256"] == digest(passwords[protocol["username"]]),
                "a Protocol received a password other than its set's")
        require(protocol["transport"] == "ntlm" and protocol["cert_pem"] is None
                and protocol["cert_key_pem"] is None and protocol["endpoint"] == "http://192.0.2.6:5985/wsman"
                and protocol["message_encryption"] == "always", f"Protocol arguments {protocol}")
    commands = [r["script"] for r in run.of("winrm", kind="run_command")]
    require(len(commands) == 4 and "LastBootUpTime" not in commands[0]
            and all("LastBootUpTime" in c for c in commands[1:3]) and "d-ordinary" in commands[3],
            f"probe commands {commands}")
    leaked = [r for r in run.records["winrm"] if any(level in str(r) for level in ("D-GROUP", "D-HOST", "D-PLAY"))]
    require(not leaked, f"a lower-precedence canary reached an attempt: {leaked[:1]}")
    require("D-FIRST d-old" in run.log, "first resolution winner")
    second = '"D-SECOND d-new {\\"d-old\\": {\\"rounds\\": 1, \\"category\\": \\"boot-floor\\"}, ' \
             '\\"d-new\\": {\\"rounds\\": 1, \\"category\\": \\"worked\\"}}"'
    require(second in run.log, "second resolution observations")
    require("D-MEMBERS-VERIFIED" in run.log, "member fan-out assertion")
    return [
        f"Protocol sequence (user, read_timeout_sec, send_cbt): {summary}",
        "first probe command has no LastBootUpTime; both second-call probes carry it",
        "second call: d-old rejected as boot-floor (boot 90 <= 100), d-new worked (boot 101)",
        "no D-GROUP/D-HOST/D-PLAY canary in any WinRM record; every member of the winner's groups verified",
    ]
