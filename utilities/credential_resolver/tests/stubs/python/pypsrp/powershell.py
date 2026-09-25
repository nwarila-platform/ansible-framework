from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from pypsrp._record import record
from pypsrp.complex_objects import PSInvocationState, RunspacePoolState
from pypsrp.exceptions import AuthenticationError


class RunspacePool:
    count = 0

    def __init__(self, connection, host=None, **kwargs):
        RunspacePool.count += 1
        self.number = RunspacePool.count
        self.connection = connection
        self.host = host
        self.kwargs = kwargs
        self.state = RunspacePoolState.BEFORE_OPEN
        self.id = f"RUNSPACE-{self.number}"
        record({"kind": "RunspacePool", "number": self.number, "arguments": kwargs})

    def open(self):
        user = self.connection.kwargs.get("username")
        table = json.loads(Path(os.environ["CREDRES_TABLE"]).read_text(encoding="utf-8"))
        response = table.get("psrp", {}).get("responses", {}).get(user, {})
        if response.get("reject"):
            raise AuthenticationError("the specified credentials were rejected by the server")
        self.state = RunspacePoolState.OPENED
        record({"kind": "RunspacePool.open", "number": self.number, "username": user})

    def close(self):
        self.state = RunspacePoolState.CLOSED
        record({"kind": "RunspacePool.close", "number": self.number})


class PowerShell:
    def __init__(self, runspace):
        self.runspace = runspace
        self.output = []
        self.streams = SimpleNamespace(error=[])
        self.had_errors = False
        self.state = PSInvocationState.NOT_STARTED
        self.script = ""

    def add_script(self, script, use_local_scope=True):
        self.script = script

    def add_argument(self, arg):
        del arg

    def invoke(self, input=None):
        del input
        user = self.runspace.connection.kwargs.get("username")
        table = json.loads(Path(os.environ["CREDRES_TABLE"]).read_text(encoding="utf-8"))
        response = table.get("psrp", {}).get("responses", {}).get(user, {})
        self.output = [response.get("stdout", "ready")]
        self.state = PSInvocationState.COMPLETED
        record({"kind": "PowerShell.invoke", "runspace": self.runspace.id,
                "username": user, "script": self.script})

    def begin_invoke(self, input=None):
        self.invoke(input)

    def poll_invoke(self):
        pass

    def end_invoke(self):
        pass

    def stop(self):
        pass
