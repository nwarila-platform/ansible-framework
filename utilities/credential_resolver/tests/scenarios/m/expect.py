"""m. secrecy: with debug mode off, no caller-supplied secret appears at default verbosity or -vvv, in
argv, in a child environment, on disk or in a fact cache, even when the stubbed remotes echo what they
receive; identity and selector canaries appear where documented; the derived surfaces behave as
documented: the SSM session token appears only in the session-manager argv and at -vvvv, and the
managed-Kerberos cache is 0600 during the connection (its removal afterwards is recorded, not asserted:
the plugin leaves it behind)."""
import hashlib
import json
from pathlib import Path

SECRETS = {
    "config": {"defaults": {"fact_caching": "jsonfile", "fact_caching_connection": "{run}/fact-cache"}},
    "env": {"ANSIBLE_SSH_AGENT": "auto"},
    "keys": {"content-key": "KEY-PASSPHRASE-SECRET-CANARY"},
}
RUNS = [
    {"name": "default", **SECRETS},
    {"name": "verbose", **SECRETS, "args": ["-vvv"]},
    {"name": "derived-token", "inventory": "inventory-derived.yml", "args": ["-vvvv"]},
]
TOKEN = "DERIVED-SESSION-TOKEN"


def check(evidence, require):
    lines = []
    for name in ("default", "verbose"):
        run = evidence[name]
        for host in ("m-ssh-password", "m-pkcs11", "m-winrm", "m-kerberos", "m-aws-static"):
            require(f"M-WINNER {host}.invalid" in run.log, f"{name}: {host} did not resolve")
        require('\\"m-key-content\\": {\\"rounds\\": 1, \\"category\\": \\"not-ready\\"}, \\"m-key-file\\": '
                '{\\"rounds\\": 1, \\"category\\": \\"worked\\"}' in run.log,
                f"{name}: the passphrase key-content set did not fall through to the key file")
        echoed = [r for r in run.ssh(mode="exec") if r["rc"] == 0]
        require(len(echoed) >= 3, f"{name}: echoing SSH probes {len(echoed)}")
        leaks = [p for p in run.directory.rglob("*") if p.is_file() and "input" not in p.parts
                 and b"SECRET-CANARY" in p.read_bytes()]
        require(not leaks, f"{name}: secret canary on disk in {leaks}")
        require(TOKEN not in run.log, f"{name}: the derived session token reached the log")
        argv = [r for r in run.records["ssm"] if TOKEN in json.dumps(r["argv"])]
        require(argv, f"{name}: the derived token is not in the session-manager argv")
        cache = list((run.directory / "fact-cache").iterdir())
        require(cache and all("M-CACHE-MARKER" in p.read_text() for p in cache)
                and not any(word in p.read_text() for p in cache
                            for word in ("__credential_resolver", "ansible_password", "ansible_aws_ssm")),
                f"{name}: fact cache {[p.name for p in cache]}")
        kinit = run.of("kinit", kind="kinit")
        cache_path = Path(kinit[0]["krb5ccname"].removeprefix("FILE:")) if kinit else None
        protocols = [p for p in run.of("winrm", kind="Protocol") if p["transport"] == "kerberos"]
        require(len(kinit) == 1 and kinit[0]["cache_exists"] and kinit[0]["cache_mode"] == "0o600"
                and kinit[0]["stdin_sha256"] == hashlib.sha256(b"PASSWORD-SECRET-CANARY-MK\n").hexdigest()
                and protocols and protocols[0]["cache_mode"] == "0o600"
                and protocols[0]["krb5ccname"] == kinit[0]["krb5ccname"],
                f"{name}: managed Kerberos cache {kinit} {protocols[:1]}")
        lines.append(f"{name}: no SECRET-CANARY in {name} logs, stub records (argv, child environment), "
                     "temporary files or the jsonfile fact cache; echoing remotes stayed hidden; token absent "
                     "from the log and present in the session-manager argv; Kerberos cache 0600 during the "
                     "connection")
        lines.append(f"OBSERVED (plan premise contradicted, open for the planner): the managed-Kerberos cache "
                     f"{cache_path.name} still exists after the run (mode "
                     f"{oct(cache_path.stat().st_mode & 0o777) if cache_path.exists() else 'absent'}): the plugin "
                     "never closes its NamedTemporaryFile and the worker exits through os._exit")
    verbose = evidence["verbose"]
    for canary in ("m-ssh-IDENTITY-CANARY", "m-pkcs11-IDENTITY-CANARY", "id_stub.pub", "provider.so",
                   "M-STATIC-ACCESS-IDENTITY-CANARY"):
        require(canary in verbose.log or canary in json.dumps(verbose.records["placebo"]),
                f"documented identity or selector {canary} not visible at -vvv")
    lines.append("verbose: identity and selector canaries (users, key and provider paths, access key id) "
                 "appear in -vvv output or request signatures as documented")
    derived = evidence["derived-token"]
    require(TOKEN in derived.log, "the derived session token is not shown at -vvvv")
    lines.append("derived-token: the session token returned by the stubbed StartSession appears at -vvvv")
    return lines
