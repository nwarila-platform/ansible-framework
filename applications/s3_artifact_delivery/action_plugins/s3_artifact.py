from __future__ import annotations

from ansible.plugins.action.normal import ActionModule as NormalActionModule


class ActionModule(NormalActionModule):
    def run(self, tmp=None, task_vars=None):
        self._task.no_log = True
        result = super().run(tmp=tmp, task_vars=task_vars)
        result["_ansible_no_log"] = True
        return result
