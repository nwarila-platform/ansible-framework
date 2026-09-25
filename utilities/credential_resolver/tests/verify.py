"""Run every credential_resolver scenario against recording stubs and verify what each one left."""
from __future__ import annotations

import configparser
import errno
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import socket
import subprocess
import sys
import time
import traceback

import yaml

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
SCENARIOS = TESTS / "scenarios"
STUB_BIN = TESTS / "stubs" / "bin"
PLAYBOOK = "/root/.local/bin/ansible-playbook"
PROXY = "http://127.0.0.1:9"
RECORD_KINDS = ("ssh", "winrm", "psrp", "kinit", "misc", "placebo", "ssm", "curl")
USER_SSH = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".ssh"
GLOBAL_SSH_CONFIG = Path("/etc/ssh/ssh_config")
SECRET_MARK = b"SECRET-CANARY"
DEFAULT_AWS_CONFIG = "[default]\nregion = us-test-1\n"
DEFAULT_AWS_CREDENTIALS = (
    "[default]\naws_access_key_id = AMBIENT-ACCESS-CANARY\n"
    "aws_secret_access_key = AMBIENT-SECRET-CANARY\n"
)


class ScenarioFailure(AssertionError):
    pass


def require(condition: object, message: str) -> None:
    if not condition:
        raise ScenarioFailure(message)


class Evidence:
    """One ansible-playbook run: its exit code, its log and every stub record it produced."""

    def __init__(self, name: str, directory: Path, rc: int, elapsed: float) -> None:
        self.name = name
        self.directory = directory
        self.rc = rc
        self.elapsed = elapsed
        self.log = (directory / "ansible.log").read_text(encoding="utf-8", errors="replace")
        self.records = {}
        for kind in RECORD_KINDS:
            path = directory / f"{kind}.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            self.records[kind] = [json.loads(line) for line in lines if line.strip()]

    def ssh(self, **match: object) -> list[dict]:
        return [r for r in self.records["ssh"] if all(r.get(k) == v for k, v in match.items())]

    def of(self, source: str, **match: object) -> list[dict]:
        return [r for r in self.records[source] if all(r.get(k) == v for k, v in match.items())]

    def play(self, title: str) -> str:
        sections = re.split(r"^(?=PLAY \[)", self.log, flags=re.MULTILINE)
        matches = [section for section in sections if section.startswith(f"PLAY [{title}")]
        require(len(matches) == 1, f"{self.name}: expected one play titled {title!r}")
        return matches[0]

    def task(self, title: str, text: str | None = None) -> list[str]:
        """The output of every run of the task whose header names `title`."""
        blocks = re.split(r"^(?=TASK \[|PLAY \[|PLAY RECAP)", text or self.log, flags=re.MULTILINE)
        return [block.split("\n", 1)[1] for block in blocks
                if block.startswith("TASK [") and title in block.split("\n", 1)[0]]

    def messages(self) -> list[str]:
        return re.findall(r'"msg": "(.*)"', self.log)

    def traffic(self) -> list[dict]:
        """Every record of a connection attempt; the preflight's controller-side ticket check is not one."""
        return [r for kind in RECORD_KINDS for r in self.records[kind] if r.get("kind") != "klist"]

    def touched(self, address: str) -> list[dict]:
        """Every stub record that names the address, in any kind."""
        return [r for kind in RECORD_KINDS for r in self.records[kind]
                if address in json.dumps(r)]


def require_isolation() -> list[str]:
    for kind in ("net", "mnt"):
        if os.readlink(f"/proc/self/ns/{kind}") == os.readlink(f"/proc/1/ns/{kind}"):
            raise SystemExit(f"refusing to run outside a private {kind} namespace")
    links = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True, check=True)
    routes = [
        subprocess.run(["ip", family, "route", "show"], capture_output=True, text=True,
                       check=True).stdout.strip()
        for family in ("-4", "-6")
    ]
    names = [line.split(":")[1].strip() for line in links.stdout.splitlines()]
    require(names == ["lo"] and routes == ["", ""], f"network namespace not isolated: {names} {routes}")
    try:
        socket.create_connection(("192.0.2.1", 22), timeout=3).close()
    except OSError as error:
        require(error.errno == errno.ENETUNREACH, f"unexpected connect result: {error}")
        unreachable = errno.errorcode[error.errno]
    else:
        raise SystemExit("a TCP connection succeeded inside the scenario namespace")
    return [
        "isolation: private net and mount namespaces (differ from pid 1)",
        f"isolation: links={names} ipv4-routes=0 ipv6-routes=0 connect(192.0.2.1:22)={unreachable}",
    ]


NETWORK_PROFILES = ("ssh_", "winrm_", "psrp_", "aws_ssm_")


def hosts_of(group: dict) -> dict[str, dict]:
    hosts = {name: variables or {} for name, variables in (group.get("hosts") or {}).items()}
    for child in (group.get("children") or {}).values():
        hosts.update(hosts_of(child or {}))
    return hosts


def network_addresses(variables: dict) -> list[str]:
    """The host's own address and every network-profile candidate's address."""
    addresses = [variables["ansible_host"]] if "ansible_host" in variables else []
    candidates = variables.get("credential_resolver_candidates")
    for candidate in candidates if isinstance(candidates, list) else []:
        if isinstance(candidate, dict) and str(candidate.get("profile")).startswith(NETWORK_PROFILES):
            candidate_vars = candidate.get("vars")
            if isinstance(candidate_vars, dict) and "ansible_host" in candidate_vars:
                addresses.append(candidate_vars["ansible_host"])
    return [str(address) for address in addresses]


def check_scenario_text(letter: str) -> None:
    for path in sorted(p for p in (SCENARIOS / letter).iterdir() if p.is_file()):
        text = path.read_text(encoding="utf-8")
        for host in re.findall(r"[a-z]+://([^/'\"\s:\\]+)", text):
            require(host.endswith(".invalid") or host.startswith("192.0.2."), f"{path.name}: URL host {host}")
        if path.suffix == ".yml" and path.name.startswith("inventory"):
            hosts = hosts_of(yaml.safe_load(text)["all"])
            require(all(name.endswith(".invalid") for name in hosts), f"{path.name}: host names {list(hosts)}")
            addresses = [a for variables in hosts.values() for a in network_addresses(variables)]
            require(all(a.startswith("192.0.2.") for a in addresses), f"{path.name}: addresses {addresses}")


def expand(value: str, inputs: Path, directory: Path) -> str:
    return value.replace("{input}", str(inputs)).replace("{run}", str(directory))


def deep_merge(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def write_config(path: Path, overrides: dict, inputs: Path, directory: Path) -> None:
    parser = configparser.RawConfigParser()
    parser.read(TESTS / "ansible.cfg", encoding="utf-8")
    for section, values in overrides.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in values.items():
            if value is None:
                parser.remove_option(section, key)
            else:
                parser.set(section, key, expand(str(value), inputs, directory))
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)


def generate_key(path: Path, passphrase: str) -> list[bytes]:
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", passphrase, "-C", "", "-f", str(path)],
                   check=True, stdin=subprocess.DEVNULL)
    body = path.read_bytes().splitlines()[1:-1]
    return [line for line in body[2:] if len(line) > 40]


def environment(directory: Path, inputs: Path, run: dict) -> dict[str, str]:
    env = {
        "PATH": f"{STUB_BIN}:/root/.local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(directory / "home"),
        "USER": "root",
        "LOGNAME": "root",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(TESTS / "stubs" / "python"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ANSIBLE_CONFIG": str(inputs / "ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(REPO / "utilities"),
        "ANSIBLE_COLLECTIONS_PATH": "/root/.ansible/collections",
        "ANSIBLE_HOME": str(directory / "ansible-home"),
        "ANSIBLE_LOCAL_TEMP": str(directory / "local"),
        "ANSIBLE_REMOTE_TMP": str(directory / "remote"),
        "ANSIBLE_SSH_CONTROL_PATH_DIR": str(directory / "control-path"),
        "ANSIBLE_NOCOLOR": "1",
        "TMPDIR": str(directory / "tmp"),
        "HTTP_PROXY": PROXY,
        "HTTPS_PROXY": PROXY,
        "http_proxy": PROXY,
        "https_proxy": PROXY,
        "NO_PROXY": "",
        "no_proxy": "",
        "AWS_CONFIG_FILE": str(inputs / "aws-config"),
        "AWS_SHARED_CREDENTIALS_FILE": str(inputs / "aws-credentials"),
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_SESSION_MANAGER_PLUGIN": str(STUB_BIN / "session-manager-plugin"),
        "KRB5_CONFIG": str(inputs / "krb5.conf"),
        "KRB5CCNAME": f"FILE:{directory / 'krb5cc'}",
        "_ANSIBLE_PLACEBO_RECORD": str(directory / "placebo"),
        "CREDRES_TABLE": str(inputs / "table.json"),
        "CREDRES_RECORD_DIR": str(directory),
        "CREDRES_STORE": str(directory / "store"),
        "CREDRES_INPUT": str(inputs),
    }
    env.update({f"CREDRES_{kind.upper()}_LOG": str(directory / f"{kind}.jsonl") for kind in RECORD_KINDS})
    env["CREDRES_RUN_ENV_NAMES"] = ",".join(run.get("env", {}))
    for name, value in run.get("env", {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = expand(value, inputs, directory)
    return env


def execute(letter: str, run: dict, root: Path, markers: list[bytes]) -> Evidence:
    directory = root / letter / run["name"]
    inputs = directory / "input"
    for name in ("home", "ansible-home", "local", "remote", "tmp", "control-path", "placebo",
                 "store", "fact-cache", "input/user-ssh"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    write_config(inputs / "ansible.cfg", run.get("config", {}), inputs, directory)
    table = json.loads((SCENARIOS / letter / "table.json").read_text(encoding="utf-8"))
    (inputs / "table.json").write_text(json.dumps(deep_merge(table, run.get("table", {}))),
                                       encoding="utf-8")
    (inputs / "aws-config").write_text(run.get("aws_config", DEFAULT_AWS_CONFIG), encoding="utf-8")
    (inputs / "aws-credentials").write_text(run.get("aws_credentials", DEFAULT_AWS_CREDENTIALS),
                                            encoding="utf-8")
    (inputs / "krb5.conf").write_text("[libdefaults]\ndefault_realm = TEST.INVALID\n", encoding="utf-8")
    for name, content in run.get("files", {}).items():
        (inputs / name).parent.mkdir(parents=True, exist_ok=True)
        (inputs / name).write_text(expand(content, inputs, directory), encoding="utf-8")
    for name in run.get("executables", ()):
        (inputs / name).chmod(0o755)
    for name, passphrase in run.get("keys", {}).items():
        markers.extend(generate_key(inputs / name, passphrase))
    for name, content in run.get("user_ssh", {}).items():
        path = inputs / "user-ssh" / name
        path.write_text(expand(content, inputs, directory), encoding="utf-8")
        path.chmod(0o600)
    mounts = [(inputs / "user-ssh", USER_SSH)]
    if "global_ssh_config" in run:
        (inputs / "ssh_config").write_text(expand(run["global_ssh_config"], inputs, directory),
                                           encoding="utf-8")
        mounts.append((inputs / "ssh_config", GLOBAL_SSH_CONFIG))
    command = [
        PLAYBOOK,
        "-i", str(SCENARIOS / letter / run.get("inventory", "inventory.yml")),
        str(SCENARIOS / letter / run.get("playbook", "playbook.yml")),
        *[expand(argument, inputs, directory) for argument in run.get("args", [])],
    ]
    mounted = []
    started = time.monotonic()
    try:
        for source, target in mounts:
            subprocess.run(["mount", "--bind", str(source), str(target)], check=True)
            mounted.append(target)
        with (directory / "ansible.log").open("wb") as log:
            completed = subprocess.run(
                command,
                cwd=REPO,
                env=environment(directory, inputs, run),
                input=run.get("stdin", "").encode(),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=run.get("timeout", 900),
                start_new_session=True,
                check=False,
            )
    finally:
        for target in reversed(mounted):
            subprocess.run(["umount", str(target)], check=True)
    return Evidence(run["name"], directory, completed.returncode, time.monotonic() - started)


def load(letter: str):
    spec = importlib.util.spec_from_file_location(f"scenario_{letter}", SCENARIOS / letter / "expect.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_scenario(letter: str, root: Path, markers: list[bytes]) -> tuple[bool, list[str]]:
    lines = []
    try:
        check_scenario_text(letter)
        scenario = load(letter)
        evidence = {}
        for run in scenario.RUNS:
            result = execute(letter, run, root, markers)
            evidence[run["name"]] = result
            lines.append(f"run {run['name']}: rc={result.rc} elapsed={result.elapsed:.1f}s")
            require(result.rc == run.get("expected_rc", 0),
                    f"{run['name']}: rc={result.rc}, expected {run.get('expected_rc', 0)}")
            faults = [r for kind in RECORD_KINDS for r in result.records[kind] if "stub_error" in r]
            require(not faults, f"{run['name']}: stub fault {faults[:1]}")
            require(not (root / "tripwire.log").exists(), f"{run['name']}: a real binary was reached")
        lines += scenario.check(evidence, require)
        return True, lines
    except ScenarioFailure as failure:
        return False, lines + [f"FAILURE: {failure}"]
    except Exception:
        return False, lines + ["ERROR: " + traceback.format_exc().strip().splitlines()[-1]]


def sweep(root: Path, markers: list[bytes]) -> list[str]:
    leaks = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if path.is_file() and "input" not in path.relative_to(root).parts:
            scanned += 1
            data = path.read_bytes()
            leaks += [f"{path}: {marker[:24]!r}" for marker in markers if marker in data]
    shared = 0
    for path in Path("/dev/shm").iterdir():
        if path.is_file():
            shared += 1
            data = path.read_bytes()
            leaks += [f"{path}: {marker[:24]!r}" for marker in markers if marker in data]
    require(not leaks, "secret canary sweep found " + "; ".join(leaks[:5]))
    return [f"secret-canary-sweep: PASS — {scanned} run files and {shared} /dev/shm segments hold no "
            f"secret marker ({len(markers)} markers: SECRET-CANARY plus generated key material)"]


def main() -> int:
    root = Path(sys.argv[1])
    letters = sys.argv[2:] or sorted(path.name for path in SCENARIOS.iterdir() if path.is_dir())
    for line in require_isolation():
        print(line, flush=True)
    markers = [SECRET_MARK]
    table = []
    for letter in letters:
        started = time.monotonic()
        passed, lines = run_scenario(letter, root, markers)
        table.append((letter, passed, time.monotonic() - started))
        print(f"SCENARIO {letter} {'PASS' if passed else 'FAIL'}", flush=True)
        for line in lines:
            print(f"  {line}", flush=True)
    try:
        for line in sweep(root, markers):
            print(line)
        swept = True
    except ScenarioFailure as failure:
        print(f"secret-canary-sweep: FAIL — {failure}")
        swept = False
    print("SUMMARY")
    for letter, passed, elapsed in table:
        print(f"  {letter}: {'PASS' if passed else 'FAIL'} ({elapsed:.0f}s)")
    passed = swept and all(passed for _, passed, _ in table)
    print("ALL SCENARIOS PASS" if passed else "SUITE FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
