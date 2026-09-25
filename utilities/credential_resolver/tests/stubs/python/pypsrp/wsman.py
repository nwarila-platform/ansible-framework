from __future__ import annotations

import hashlib
from types import SimpleNamespace

from pypsrp._record import record


class WSMan:
    count = 0

    def __init__(self, **kwargs):
        WSMan.count += 1
        self.number = WSMan.count
        self.kwargs = kwargs
        self.max_payload_size = 150000
        scheme = "https" if kwargs.get("ssl") else "http"
        self.transport = SimpleNamespace(
            endpoint=f"{scheme}://{kwargs.get('server')}:{kwargs.get('port')}/{kwargs.get('path')}"
        )
        safe = dict(kwargs)
        password = safe.pop("password", None) or ""
        safe["password_bytes"] = len(password)
        safe["password_sha256"] = hashlib.sha256(password.encode()).hexdigest()
        record({"kind": "WSMan", "number": self.number, "arguments": safe})
