"""k. aws_ssm and the community local transports: each AWS credential mode resolves and runs an
ordinary module through the real SDK client construction; the profile mode ignores poisoned
environment keys; static is refused under AWS_PROFILE or AWS_DEFAULT_PROFILE and without its secret;
the ambient profile-plus-keys conflict fails that attempt before traffic and the walk continues; the
effective SSM and S3 endpoints must be HTTPS for every source and precedence, SSM and S3 separately;
publishing opens no session beyond the probe's and the next task's; every community local transport
runs with its user or remote at null under poisoned keyword, CLI, environment, configuration and
inventory values."""
import hashlib
import json
from urllib.parse import urlparse

AWS_CONFIG = "[default]\nregion = us-test-1\n\n[profile profile-only]\nregion = us-test-1\n"
AWS_CREDENTIALS = ("[default]\naws_access_key_id = AMBIENT-ACCESS-CANARY\n"
                   "aws_secret_access_key = AMBIENT-SECRET-CANARY\n\n"
                   "[profile-only]\naws_access_key_id = PROFILE-ACCESS-CANARY\n"
                   "aws_secret_access_key = PROFILE-SECRET-CANARY\n")
ENVIRONMENT_KEYS = {"AWS_ACCESS_KEY_ID": "ENV-ACCESS-IDENTITY-CANARY",
                    "AWS_SECRET_ACCESS_KEY": "ENV-SECRET-CANARY", "AWS_SESSION_TOKEN": "ENV-TOKEN-SECRET-CANARY"}
AWS = {"aws_config": AWS_CONFIG, "aws_credentials": AWS_CREDENTIALS}
ENDPOINTS = {"inventory": "inventory-endpoints.yml", **AWS}


def services(ssm, s3, extra=""):
    return (f"[default]\nregion = us-test-1\nservices = endpoints\n{extra}\n"
            f"[services endpoints]\nssm =\n  endpoint_url = {ssm}\ns3 =\n  endpoint_url = {s3}\n")


def limit(*hosts):
    return ["--limit", ",".join(f"{host}.invalid" for host in hosts)]


RUNS = [
    {"name": "modes", "inventory": "inventory-modes.yml", **AWS},
    {"name": "modes-environment-keys", "inventory": "inventory-modes.yml", **AWS, "env": ENVIRONMENT_KEYS,
     "args": limit("k-ambient", "k-profile", "k-static")},
    {"name": "static-under-aws-profile", "inventory": "inventory-modes.yml", **AWS,
     "env": {"AWS_PROFILE": "profile-only"}, "args": limit("k-static")},
    {"name": "static-under-aws-default-profile", "inventory": "inventory-modes.yml", **AWS,
     "env": {"AWS_DEFAULT_PROFILE": "profile-only"}, "args": limit("k-static")},
    {"name": "ambient-profile-and-keys", "inventory": "inventory-conflict.yml", **AWS,
     "env": {"AWS_PROFILE": "profile-only", **ENVIRONMENT_KEYS}},
    {"name": "endpoint-options", **ENDPOINTS, "args": limit(
        "k-ssm-option-http", "k-ssm-option-https", "k-bucket-option-http", "k-bucket-option-https",
        "k-ssm-http-bucket-https")},
    {"name": "environment-ssm-http", **ENDPOINTS, "args": limit("k-default", "k-ssm-option-https"),
     "env": {"AWS_ENDPOINT_URL_SSM": "http://ssm-env.invalid", "AWS_ENDPOINT_URL_S3": "https://s3-env.invalid"}},
    {"name": "environment-s3-http", **ENDPOINTS, "args": limit("k-default", "k-bucket-over", "k-ssm-option-https"),
     "env": {"AWS_ENDPOINT_URL_SSM": "https://ssm-env.invalid", "AWS_ENDPOINT_URL_S3": "http://s3-env.invalid"}},
    {"name": "environment-https", **ENDPOINTS, "args": limit("k-default"),
     "env": {"AWS_ENDPOINT_URL_SSM": "https://ssm-env.invalid", "AWS_ENDPOINT_URL_S3": "https://s3-env.invalid"}},
    {"name": "environment-global-http", **ENDPOINTS, "args": limit("k-default", "k-ssm-option-https"),
     "env": {"AWS_ENDPOINT_URL": "http://global-env.invalid"}},
    {"name": "environment-global-https", **ENDPOINTS, "args": limit("k-default"),
     "env": {"AWS_ENDPOINT_URL": "https://global-env.invalid"}},
    {"name": "configuration-services-ssm-http", **ENDPOINTS, "args": limit("k-default", "k-ssm-option-https"),
     "aws_config": services("http://ssm-services.invalid", "https://s3-services.invalid")},
    {"name": "configuration-services-s3-http", **ENDPOINTS,
     "args": limit("k-default", "k-bucket-over", "k-ssm-option-https"),
     "aws_config": services("https://ssm-services.invalid", "http://s3-services.invalid")},
    {"name": "configuration-services-https", **ENDPOINTS, "args": limit("k-default"),
     "aws_config": services("https://ssm-services.invalid", "https://s3-services.invalid")},
    {"name": "configuration-global-http", **ENDPOINTS, "args": limit("k-default", "k-ssm-option-https"),
     "aws_config": "[default]\nregion = us-test-1\nendpoint_url = http://global-config.invalid\n"},
    {"name": "configuration-global-https", **ENDPOINTS, "args": limit("k-default"),
     "aws_config": "[default]\nregion = us-test-1\nendpoint_url = https://global-config.invalid\n"},
    {"name": "services-under-global-environment", **ENDPOINTS, "args": limit("k-default"),
     "aws_config": services("https://ssm-services.invalid", "https://s3-services.invalid"),
     "env": {"AWS_ENDPOINT_URL": "http://global-env.invalid"}},
    {"name": "ignore-configured-endpoints", **ENDPOINTS, "args": limit("k-ignore", "k-ssm-option-http"),
     "aws_config": services("http://ssm-services.invalid", "http://s3-services.invalid",
                            "endpoint_url = http://global-config.invalid\n"),
     "env": {"AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true", "AWS_ENDPOINT_URL": "http://global-env.invalid",
             "AWS_ENDPOINT_URL_SSM": "http://ssm-env.invalid", "AWS_ENDPOINT_URL_S3": "http://s3-env.invalid"}},
    {"name": "local-transports", "inventory": "inventory-local.yml", "playbook": "local.yml",
     "args": ["-u", "poison-cli-user"], "env": {"ANSIBLE_REMOTE_USER": "poison-env-user"},
     "files": {"chroot/bin/sh": "#!/bin/sh\n"}, "executables": ["chroot/bin/sh"], "expected_rc": 2},
]
FLOOR = "rule 4 requires effective HTTPS SSM and S3 endpoints"
# run: {host: expected SSM host, S3 bucket-lookup host, S3 transfer host} or the refusal
ENDPOINT_EXPECTATIONS = {
    "endpoint-options": {
        "k-ssm-option-http": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
        "k-bucket-option-http": FLOOR,
        "k-bucket-option-https": ("ssm-option.invalid", "ssm-option.invalid", "s3-bucket.invalid"),
        "k-ssm-http-bucket-https": FLOOR,
    },
    "environment-ssm-http": {
        "k-default": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "environment-s3-http": {
        "k-default": FLOOR, "k-bucket-over": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "environment-https": {"k-default": ("ssm-env.invalid", "s3-env.invalid", "s3-env.invalid")},
    "environment-global-http": {
        "k-default": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "environment-global-https": {"k-default": ("global-env.invalid", "global-env.invalid", "global-env.invalid")},
    "configuration-services-ssm-http": {
        "k-default": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "configuration-services-s3-http": {
        "k-default": FLOOR, "k-bucket-over": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "configuration-services-https": {"k-default": ("ssm-services.invalid", "s3-services.invalid", "s3-services.invalid")},
    "configuration-global-http": {
        "k-default": FLOOR,
        "k-ssm-option-https": ("ssm-option.invalid", "ssm-option.invalid", "ssm-option.invalid"),
    },
    "configuration-global-https": {"k-default": ("global-config.invalid", "global-config.invalid", "global-config.invalid")},
    "services-under-global-environment": {"k-default": FLOOR},
}
LOCAL = {
    "chroot": lambda argv: argv[0].endswith("/input/chroot") and argv[1:3] == ["/bin/sh", "-c"],
    "jexec": lambda argv: "-U" not in argv and argv[0] in ("k-jail-target", "ioc-stub-uuid"),
    "iocage": lambda argv: argv == ["get", "host_hostuuid", "k-iocage-target"],
    "lxc": lambda argv: argv[0] == "k-lxc-target",
    "lxd": lambda argv: argv[:2] == ["exec", "local:k-lxd-target"],
    "qubes": lambda argv: "-u" not in argv and "k-qubes-target" in argv,
    "saltstack": lambda argv: argv[:2] == ["192.0.2.68", "cmd.exec_code_all"],
    "zoneadm": lambda argv: argv == ["list", "-ip"],
}
UPSTREAM = {
    "k-funcd": "the connection plugin 'community.general.funcd' was not found",
    "k-zone": "a bytes-like object is required, not 'str'",
}


def refused(run, host):
    return " ".join(m for m in run.messages() if m.startswith(f"K-REFUSED {host}.invalid "))


def requests(run, host):
    """Requests attributable to one host: its bucket in S3 URLs and its instance id in StartSession."""
    bucket = f"bucket-{host.removeprefix('k-')}"
    instance = f"i-{host.removeprefix('k-')}"
    return [r for r in run.records["placebo"] if r.get("session_target") == instance
            or bucket in urlparse(r["url"]).path.split("/")
            or (urlparse(r["url"]).hostname or "").split(".")[0] == bucket]


def sessions(run, instance):
    return [r for r in run.records["ssm"] if json.dumps({"Target": instance}) in r["argv"]]


def check_endpoint(run, host, expected, require):
    if expected == FLOOR:
        require(f"k-{host.removeprefix('k-')}: {FLOOR}" in refused(run, host), f"{run.name} {host} not refused")
        require(not requests(run, host), f"{run.name} {host} sent a request after its refusal")
        return f"{run.name}: {host} refused (rule 4) with no request"
    ssm_host, lookup_host, transfer_host = expected
    records = requests(run, host)
    start = [urlparse(r["url"]).hostname for r in records if "StartSession" in r["target"]]
    head = [urlparse(r["url"]).hostname for r in records if r["method"] == "HEAD"]
    transfer = [urlparse(r["url"]).hostname for r in records if r["method"] in ("PUT", "DELETE")]
    require(start and all(h == ssm_host for h in start), f"{run.name} {host} SSM hosts {start}")
    require(head and all(h.endswith(lookup_host) for h in head), f"{run.name} {host} bucket lookup {head}")
    require(transfer and all(h.endswith(transfer_host) for h in transfer), f"{run.name} {host} transfers {transfer}")
    require(f"K-WINNER {host}.invalid {host} k-ordinary-module" in run.log, f"{run.name} {host} did not run a module")
    return f"{run.name}: {host} SSM -> {ssm_host}, bucket lookup -> {lookup_host}, transfers -> {transfer_host}"


def check(evidence, require):
    lines = []
    modes = evidence["modes"]
    for host, key in (("k-ambient", "AMBIENT-ACCESS-CANARY"), ("k-profile", "PROFILE-ACCESS-CANARY"),
                      ("k-static", "STATIC-ACCESS-IDENTITY-CANARY")):
        records = requests(modes, host)
        require(records and {r["signing_access_key_id"] for r in records} == {key}, f"{host} signing keys")
        starts = [r for r in records if "StartSession" in r["target"]]
        require(len(starts) == 2 and len(sessions(modes, f"i-{host.removeprefix('k-')}")) == 2,
                f"{host}: {len(starts)} sessions (probe and next task expected)")
        require(f"K-WINNER {host}.invalid {host} k-ordinary-module" in modes.log, f"{host} module")
        token = {r["security_token_present"] for r in records}
        require(token == {host == "k-static"}, f"{host} session token presence {token}")
        presigned = {r["presigned_token_sha256"] for r in modes.records["curl"]
                     if f"/bucket-{host.removeprefix('k-')}/" in json.dumps(r["argv"])}
        expected = {hashlib.sha256(b"STATIC-TOKEN-SECRET-CANARY").hexdigest() if host == "k-static" else None}
        require(presigned == expected, f"{host} presigned transfer token {presigned}")
        lines.append(f"modes: {host} signs every request with {key}; 2 sessions (probe + ordinary module); "
                     f"module output k-ordinary-module")
    lines.append("OBSERVED (derived surface outside the resolver, open for the planner): the ordinary module's "
                 "S3 transfer URL is presigned with the static set's session token (X-Amz-Security-Token), "
                 "which the plugin hands to the remote curl command line; the resolver's raw probe transfers "
                 "nothing")
    require("k-static-missing: rule 2 is missing a required variable" in refused(modes, "k-static-missing")
            and not requests(modes, "k-static-missing"), "static without its secret key was not refused")
    lines.append("modes: a static set without its secret key is refused before traffic")

    environment = evidence["modes-environment-keys"]
    for host, key in (("k-ambient", "ENV-ACCESS-IDENTITY-CANARY"), ("k-profile", "PROFILE-ACCESS-CANARY"),
                      ("k-static", "STATIC-ACCESS-IDENTITY-CANARY")):
        records = requests(environment, host)
        require(records and {r["signing_access_key_id"] for r in records} == {key},
                f"{host} under environment keys signed with {({r['signing_access_key_id'] for r in records})}")
    lines.append("environment keys: ambient takes them (default chain); profile signs with its profile only; "
                 "static signs with its own keys only")

    for name in ("static-under-aws-profile", "static-under-aws-default-profile"):
        run = evidence[name]
        require("k-static: rule 4 refuses static AWS credentials while an environment profile is set"
                in refused(run, "k-static") and not run.records["placebo"], f"{name} not refused before traffic")
        lines.append(f"{name}: static refused before traffic")

    conflict = evidence["ambient-profile-and-keys"]
    records = conflict.records["placebo"]
    require(records and {r["signing_access_key_id"] for r in records} == {"PROFILE-ACCESS-CANARY"}
            and not requests(conflict, "k-conflict-ambient"), "the ambient conflict sent a request")
    require('\\"k-conflict-ambient\\": {\\"rounds\\": 1, \\"category\\": \\"not-ready\\"}' in conflict.log
            and "K-WINNER k-conflict.invalid k-conflict-profile k-ordinary-module" in conflict.log,
            "the walk did not continue past the ambient conflict")
    lines.append("ambient profile-plus-keys: that attempt failed before any request (not-ready); the walk "
                 "continued and the profile set won")

    for name, expectations in ENDPOINT_EXPECTATIONS.items():
        run = evidence[name]
        for host, expected in expectations.items():
            lines.append(check_endpoint(run, host, expected, require))

    ignore = evidence["ignore-configured-endpoints"]
    require(FLOOR not in refused(ignore, "k-ignore"), "configured endpoints were not ignored")
    require('\\"k-ignore-configured\\": {\\"rounds\\": 1, \\"category\\": \\"probe-failed\\"}' in ignore.log,
            "the ignored-endpoint set did not fail before traffic at its missing plugin")
    require(not requests(ignore, "k-ignore-configured"), "the ignored-endpoint set sent a request")
    option = requests(ignore, "k-ignore-option")
    require(option and {urlparse(r["url"]).hostname for r in option} == {"ssm-option.invalid"}
            and "K-WINNER k-ignore.invalid k-ignore-option k-ordinary-module" in ignore.log,
            "the explicit https option set did not win through ssm-option.invalid")
    lines.append(check_endpoint(ignore, "k-ssm-option-http", FLOOR, require))
    lines.append("ignore-configured-endpoints: http configured values ignored (the set passed the floor and "
                 "failed before traffic at its missing plugin); an explicit http option is still refused")

    local = evidence["local-transports"]
    for name in ("k-local", "k-chroot", "k-iocage", "k-jail", "k-lxc", "k-lxd", "k-qubes", "k-saltstack"):
        require(f"K-WINNER {name}.invalid {name}" in local.log, f"{name} did not win")
        require(f"'{name}.invalid' works as '{name}'" in local.log, f"{name} success line")
    for kind, accepted in LOCAL.items():
        found = [r for r in local.records["misc"] if r["kind"] == kind]
        require(found and all(accepted(r["argv"]) for r in found), f"{kind} records {[r['argv'] for r in found]}")
        lines.append(f"local-transports: {kind} {found[-1]['argv']}")
    require(not any("poison" in json.dumps(r) for r in local.records["misc"]), "a poisoned user or remote reached")
    lines.append("local-transports: no poison-keyword/cli/env/config/inventory user or remote in any record; "
                 "every success line names the inventory host")
    for host, error in UPSTREAM.items():
        failures = local.task("Apply The Complete Attempt Map")
        require(any(f"[ERROR]: Task failed: {error}" in block and f"failed: [{host}.invalid]" in block
                    for block in failures), f"{host} did not fail with the upstream error {error!r}")
        lines.append(f"OBSERVED (upstream, open for the planner): {host} cannot run on this controller: {error}")
    return lines
