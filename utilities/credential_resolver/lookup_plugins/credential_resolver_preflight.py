from __future__ import annotations

from importlib.util import find_spec
import os
from pathlib import Path
import shutil
import subprocess

from ansible import constants as C
from ansible import context
from ansible.plugins.lookup import LookupBase
from ansible.utils.vars import load_extra_vars


def _has_module(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def _has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _global_keysign_enabled() -> bool:
    path = Path("/etc/ssh/ssh_config")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        statement = line.split("#", 1)[0].strip().lower().replace("=", " ", 1).split()
        if statement == ["enablesshkeysign", "yes"]:
            return True
    return False


def _valid_ticket() -> bool:
    if not _has_binary("klist"):
        return False
    result = subprocess.run(
        ["klist", "-s"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _aws_endpoints(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    try:
        import boto3
    except ImportError:
        return [{
            "name": candidate["name"],
            "ssm_https": False,
            "s3_https": False,
            "bucket_https": False,
            "errors": ["SSM", "S3"],
            "ambient_conflict": False,
            "static_profile_conflict": False,
        } for candidate in candidates]

    reports = []
    for candidate in candidates:
        report = {
            "name": candidate["name"],
            "ssm_https": False,
            "s3_https": False,
            "bucket_https": True,
            "errors": [],
            "ambient_conflict": False,
            "static_profile_conflict": False,
        }
        mode = candidate["mode"]
        environment_profile = bool(os.environ.get("AWS_PROFILE") or os.environ.get("AWS_DEFAULT_PROFILE"))
        environment_keys = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
        report["ambient_conflict"] = mode == "ambient" and environment_profile and environment_keys
        report["static_profile_conflict"] = mode == "static" and environment_profile

        profile = candidate.get("profile") if mode == "profile" else None
        for service, result_key in (("ssm", "ssm_https"), ("s3", "s3_https")):
            try:
                session = boto3.Session(profile_name=profile, region_name=candidate.get("region"))
                endpoint_url = candidate.get("endpoint_url")
                client = session.client(
                    service,
                    endpoint_url=endpoint_url or None,
                    region_name=candidate.get("region") or None,
                    aws_access_key_id="PLACEHOLDER",
                    aws_secret_access_key="PLACEHOLDER",
                    aws_session_token="PLACEHOLDER",
                )
                report[result_key] = client.meta.endpoint_url.lower().startswith("https://")
            except Exception:
                report["errors"].append(service.upper())

        bucket_endpoint = candidate.get("bucket_endpoint_url")
        report["bucket_https"] = not bucket_endpoint or bucket_endpoint.lower().startswith("https://")
        reports.append(report)
    return reports


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        del variables, kwargs
        aws_candidates = terms[0] if terms else []
        cli = context.CLIARGS
        ssh_keysign = shutil.which("ssh-keysign") or next(
            (path for path in ("/usr/lib/openssh/ssh-keysign", "/usr/libexec/openssh/ssh-keysign") if Path(path).is_file()),
            None,
        )
        return [{
            "extra_var_names": sorted(load_extra_vars(self._loader).keys()),
            "ask_pass": bool(cli.get("ask_pass")),
            "become_ask_pass": bool(cli.get("become_ask_pass")),
            "private_key_file": bool(cli.get("private_key_file")),
            "connection_password_file": bool(cli.get("connection_password_file")),
            "become_password_file": bool(cli.get("become_password_file")),
            "connection_password_setting": bool(C.CONNECTION_PASSWORD_FILE),
            "become_password_setting": bool(C.BECOME_PASSWORD_FILE),
            "dependencies": {
                "pywinrm": _has_module("winrm"),
                "ntlm": _has_module("requests_ntlm"),
                "kerberos": _has_module("kerberos"),
                "kinit": _has_binary("kinit"),
                "pypsrp": _has_module("pypsrp"),
                "psrp_kerberos": _has_module("gssapi") or _has_module("krb5"),
                "gssapi_ticket": _valid_ticket(),
                "hostbased": bool(ssh_keysign) and _global_keysign_enabled(),
                "aws_ssm": _has_module("boto3") and _has_binary("session-manager-plugin"),
                "chroot": _has_binary("chroot"),
                "funcd": _has_module("func.overlord.client"),
                "iocage": _has_binary("iocage"),
                "jail": _has_binary("jexec"),
                "lxc": _has_module("lxc"),
                "lxd": _has_binary("lxc"),
                "qubes": _has_binary("qvm-run"),
                "saltstack": _has_module("salt.client"),
                "zone": _has_binary("zlogin"),
            },
            "ssh_agent_enabled": C.SSH_AGENT != "none",
            "aws": _aws_endpoints(aws_candidates),
        }]
