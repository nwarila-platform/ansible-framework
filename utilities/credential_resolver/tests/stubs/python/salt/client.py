from credential_resolver_local_stub import record, response


class LocalClient:
    def cmd(self, host, function, arguments):
        command = str(arguments[-1]) if arguments else ""
        record("saltstack", [host, function, command])
        return {host: {"retcode": 0, "stdout": response(command), "stderr": ""}}
