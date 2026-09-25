from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from winrm.exceptions import InvalidCredentialsError, WinRMError, WinRMTransportError


def record(value: dict) -> None:
    with Path(os.environ["CREDRES_WINRM_LOG"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def strtobool(value: str) -> bool:
    if value.lower() in ("true", "t", "yes", "y", "on", "1"):
        return True
    if value.lower() in ("false", "f", "no", "n", "off", "0"):
        return False
    raise ValueError(f"invalid truth value '{value}'")


def check_arguments(transport, username, password, cert_pem, cert_key_pem, server_cert_validation,
                    kerberos_delegation, read_timeout_sec, operation_timeout_sec, message_encryption):
    """The argument checks pywinrm 0.5.0 applies in Protocol.__init__ and Transport.__init__."""
    try:
        read_timeout_sec = int(read_timeout_sec)
    except ValueError as error:
        raise ValueError(f"failed to parse read_timeout_sec as int: {error}")
    try:
        operation_timeout_sec = int(operation_timeout_sec)
    except ValueError as error:
        raise ValueError(f"failed to parse operation_timeout_sec as int: {error}")
    if operation_timeout_sec >= read_timeout_sec or operation_timeout_sec < 1:
        raise WinRMError("read_timeout_sec must exceed operation_timeout_sec, and both must be non-zero")
    if server_cert_validation not in [None, "validate", "ignore"]:
        raise WinRMError(f"invalid server_cert_validation mode: {server_cert_validation}")
    if not isinstance(kerberos_delegation, bool):
        strtobool(str(kerberos_delegation))
    if transport != "kerberos":
        if transport == "certificate" or (transport == "ssl" and (cert_pem or cert_key_pem)):
            if not cert_pem or not cert_key_pem:
                raise InvalidCredentialsError("both cert_pem and cert_key_pem must be specified for cert auth")
            if not os.path.exists(cert_pem):
                raise InvalidCredentialsError(f"cert_pem file not found ({cert_pem})")
            if not os.path.exists(cert_key_pem):
                raise InvalidCredentialsError(f"cert_key_pem file not found ({cert_key_pem})")
        else:
            if not username:
                raise InvalidCredentialsError(f"auth method {transport} requires a username")
            if password is None:
                raise InvalidCredentialsError(f"auth method {transport} requires a password")
    if message_encryption not in ["auto", "always", "never"]:
        raise WinRMError(f"invalid message_encryption arg: {message_encryption}. "
                         "Should be 'auto', 'always', or 'never'")


def response(username) -> dict:
    table = json.loads(Path(os.environ["CREDRES_TABLE"]).read_text(encoding="utf-8"))
    return table.get("winrm", {}).get("responses", {}).get(str(username), {})


class Protocol:
    count = 0

    def __init__(self, endpoint, transport="plaintext", username=None, password=None, realm=None,
                 service="HTTP", keytab=None, ca_trust_path="legacy_requests", cert_pem=None,
                 cert_key_pem=None, server_cert_validation="validate", kerberos_delegation=False,
                 read_timeout_sec=30, operation_timeout_sec=20, kerberos_hostname_override=None,
                 message_encryption="auto", credssp_disable_tlsv1_2=False, send_cbt=True,
                 proxy="legacy_requests"):
        Protocol.count += 1
        self.number = Protocol.count
        self.username = username
        self.password = password
        cache = Path(os.environ.get("KRB5CCNAME", "").removeprefix("FILE:"))
        entry = {
            "kind": "Protocol", "number": self.number, "pid": os.getpid(),
            "endpoint": endpoint, "transport": transport, "username": username,
            "password_given": password is not None,
            "password_bytes": len(password or ""),
            "password_sha256": hashlib.sha256((password or "").encode()).hexdigest(),
            "realm": realm, "service": service, "keytab": keytab,
            "ca_trust_path": ca_trust_path, "cert_pem": cert_pem,
            "cert_key_pem": cert_key_pem, "server_cert_validation": server_cert_validation,
            "kerberos_delegation": kerberos_delegation, "read_timeout_sec": read_timeout_sec,
            "operation_timeout_sec": operation_timeout_sec,
            "kerberos_hostname_override": kerberos_hostname_override,
            "message_encryption": message_encryption,
            "credssp_disable_tlsv1_2": credssp_disable_tlsv1_2,
            "send_cbt": send_cbt, "proxy": proxy,
            "krb5ccname": os.environ.get("KRB5CCNAME"),
            "cache_mode": oct(cache.stat().st_mode & 0o777) if cache.is_file() else None,
        }
        try:
            check_arguments(transport, username, password, cert_pem, cert_key_pem, server_cert_validation,
                            kerberos_delegation, read_timeout_sec, operation_timeout_sec,
                            message_encryption)
        except Exception as error:
            entry["construction_error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record(entry)

    def open_shell(self, codepage=None):
        if message := response(self.username).get("raise"):
            record({"kind": "open_shell", "number": self.number, "result": "raised", "message": message})
            raise WinRMError(message)
        if response(self.username).get("reject"):
            record({"kind": "open_shell", "number": self.number, "result": "401"})
            raise WinRMTransportError("http", 401, "Unauthorized")
        record({"kind": "open_shell", "number": self.number, "codepage": codepage})
        return f"SHELL-{self.number}"

    def run_command(self, shell_id, command, args, console_mode_stdin=False):
        words = [part.decode() if isinstance(part, bytes) else str(part) for part in args]
        script = ""
        if "-EncodedCommand" in words:
            script = base64.b64decode(words[words.index("-EncodedCommand") + 1]).decode("utf-16-le")
        record({"kind": "run_command", "number": self.number, "shell_id": shell_id,
                "command": repr(command), "args": repr(args), "script": script,
                "console_mode_stdin": console_mode_stdin})
        return f"COMMAND-{self.number}"

    def _get_soap_header(self, resource_uri=None, action=None, shell_id=None):
        return {"resource_uri": resource_uri, "action": action, "shell_id": shell_id}

    def send_message(self, xml):
        answer = response(self.username)
        output = answer.get("stdout", "ready")
        if answer.get("echo"):
            output = f"{output}\nECHO username={self.username} password={self.password}"
        encoded = base64.b64encode(output.encode()).decode()
        return (
            f'<Response><Stream Name="stdout" CommandId="COMMAND-{self.number}">{encoded}</Stream>'
            f'<CommandState CommandId="COMMAND-{self.number}" '
            'State="http://schemas.microsoft.com/wbem/wsman/1/windows/shell/CommandState/Done">'
            '<ExitCode>0</ExitCode></CommandState></Response>'
        )

    def cleanup_command(self, shell_id, command_id):
        record({"kind": "cleanup_command", "shell_id": shell_id, "command_id": command_id})

    def close_shell(self, shell_id):
        record({"kind": "close_shell", "shell_id": shell_id})
