"""Records the escalation core resolved for the task, without contacting the host."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    _requires_connection = False

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        become = self._connection.become
        entry = {"kind": "become", "host": task_vars["inventory_hostname"], "enabled": become is not None}
        if become is not None:
            password = become.get_option("become_pass") or ""
            entry.update(
                plugin=become.ansible_name,
                user=become.get_option("become_user"),
                flags=become.get_option("become_flags"),
                password_bytes=len(password),
                password_sha256=hashlib.sha256(password.encode()).hexdigest(),
            )
        with Path(os.environ["CREDRES_OBSERVE_LOG"]).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        result["changed"] = False
        return result
