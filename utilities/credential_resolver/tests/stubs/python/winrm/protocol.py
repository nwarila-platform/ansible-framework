from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from winrm.exceptions import WinRMError, WinRMTransportError


def record(value: dict) -> None:
    with Path(os.environ["CREDRES_WINRM_LOG"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


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
        record({
            "kind": "Protocol", "number": self.number, "pid": os.getpid(),
            "endpoint": endpoint, "transport": transport, "username": username,
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
        })

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
