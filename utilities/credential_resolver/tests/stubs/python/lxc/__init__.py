from __future__ import annotations

import os

from credential_resolver_local_stub import record, response

LXC_ATTACH_CLEAR_ENV = 1


def attach_run_command():
    return None


class Container:
    state = "RUNNING"

    def __init__(self, name):
        self.name = name

    def attach(self, callback, command, **kwargs):
        del callback
        record("lxc", [self.name, *command])
        pid = os.fork()
        if pid == 0:
            os.write(kwargs["stdout"], response(" ".join(command)).encode())
            os._exit(0)
        return pid
