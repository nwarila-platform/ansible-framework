from credential_resolver_local_stub import record, response


class Command:
    def __init__(self, host):
        self.host = host

    def run(self, command):
        record("funcd", [self.host, command])
        return {self.host: (0, response(command), "")}


class Client:
    def __init__(self, host):
        self.host = host
        self.command = Command(host)
