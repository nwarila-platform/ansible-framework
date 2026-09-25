"""Records, at the end of each run, the name (never the value) of every fact each host holds."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "credential_resolver_facts"
    CALLBACK_NEEDS_ENABLED = True

    def __init__(self) -> None:
        super().__init__()
        self._variable_manager = None

    def v2_playbook_on_play_start(self, play) -> None:
        self._variable_manager = play.get_variable_manager()

    def v2_playbook_on_stats(self, stats) -> None:
        facts = self._variable_manager._nonpersistent_fact_cache if self._variable_manager else {}
        entry = {"kind": "facts", "hosts": {str(host): sorted(names) for host, names in facts.items()}}
        with Path(os.environ["CREDRES_OBSERVE_LOG"]).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
