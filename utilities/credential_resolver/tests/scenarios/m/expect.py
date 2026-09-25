"""m. secrecy: with debug mode off, no caller-supplied secret appears at default verbosity or -vvv, in
argv, in a child environment, on disk or in a fact cache, even when the stubbed remotes echo what they
receive; a passphrase key-content set is refused before traffic because this controller's Python has
no bcrypt, and its passphrase and key stay hidden; identity and selector canaries appear where
documented; the derived surfaces behave as documented: the SSM session token appears only in the
session-manager argv and at -vvvv, and the probe's managed-Kerberos cache is 0600 during the
connection and persists in the run's TMPDIR afterwards."""
import hashlib
import json
from pathlib import Path

SECRETS = {
    "config": {"defaults": {"fact_caching": "jsonfile", "fact_caching_connection": "{run}/fact-cache"}},
    "env": {"ANSIBLE_SSH_AGENT": "auto"},
    "keys": {"content-key": "KEY-PASSPHRASE-SECRET-CANARY"},
    "expected_rc": 2,
}
RUNS = [
    {"name": "default", **SECRETS},
    {"name": "verbose", **SECRETS, "args": ["-vvv"]},
    {"name": "derived-token", "inventory": "inventory-derived.yml", "args": ["-vvvv"]},
]
TOKEN = "DERIVED-SESSION-TOKEN"
BCRYPT = ("Credential resolution validation failed for 'm-key-content.invalid': m-key-content: rule 6 "
          "missing controller dependency bcrypt\"")
RESOLVED = ("m-ssh-password", "m-pkcs11", "m-winrm", "m-kerberos", "m-aws-static")


def check(evidence, require):
    lines = []
    for name in ("default", "verbose"):
        run = evidence[name]
        for host in RESOLVED:
            require(f"M-WINNER {host}.invalid" in run.log, f"{name}: {host} did not resolve")
        require(BCRYPT in run.log and not run.ssh(user="m-key-content-IDENTITY-CANARY"),
                f"{name}: the passphrase key-content set was not refused for bcrypt alone before traffic")
        echoed = [r for r in run.ssh(mode="exec") if r["rc"] == 0]
        require(len(echoed) == 2, f"{name}: echoing SSH probes {len(echoed)}")
        leaks = [p for p in run.directory.rglob("*") if p.is_file() and "input" not in p.parts
                 and b"SECRET-CANARY" in p.read_bytes()]
        require(not leaks, f"{name}: secret canary on disk in {leaks}")
        require(TOKEN not in run.log, f"{name}: the derived session token reached the log")
        argv = [r for r in run.records["ssm"] if TOKEN in json.dumps(r["argv"])]
        require(argv, f"{name}: the derived token is not in the session-manager argv")
        cache = list((run.directory / "fact-cache").iterdir())
        require(len([p for p in cache if "M-CACHE-MARKER" in p.read_text()]) == len(RESOLVED)
                and not any(word in p.read_text() for p in cache
                            for word in ("__credential_resolver", "ansible_password", "ansible_aws_ssm")),
                f"{name}: fact cache {[p.name for p in cache]}")
        kinit = run.of("kinit", kind="kinit")
        protocols = [p for p in run.of("winrm", kind="Protocol") if p["transport"] == "kerberos"]
        require(len(kinit) == 1 and kinit[0]["cache_exists"] and kinit[0]["cache_mode"] == "0o600"
                and kinit[0]["stdin_sha256"] == hashlib.sha256(b"PASSWORD-SECRET-CANARY-MK\n").hexdigest()
                and protocols and protocols[0]["cache_mode"] == "0o600"
                and protocols[0]["krb5ccname"] == kinit[0]["krb5ccname"],
                f"{name}: managed Kerberos cache {kinit} {protocols[:1]}")
        cache_path = Path(kinit[0]["krb5ccname"].removeprefix("FILE:"))
        require(cache_path.parent == run.directory / "tmp" and cache_path.is_file()
                and cache_path.stat().st_mode & 0o777 == 0o600,
                f"{name}: the probe's Kerberos cache {cache_path} did not persist in the run's TMPDIR")
        lines.append(f"{name}: no SECRET-CANARY in {name} logs, stub records (argv, child environment), "
                     "temporary files or the jsonfile fact cache; echoing remotes stayed hidden; the passphrase "
                     "key-content set was refused before traffic for bcrypt alone; token absent from the log "
                     "and present in the session-manager argv; Kerberos cache 0600 during the connection")
        lines.append(f"{name}: the probe's managed-Kerberos cache {cache_path.name} persists in the run's TMPDIR "
                     "after the run (mode 0600), as documented: the plugin never closes its NamedTemporaryFile, "
                     "and the probe's templated when leaves its worker referencing the connection when the "
                     "worker exits through os._exit")
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
