"""l. no message-based stop: a remote refusal whose text resembles a configuration message leaves the
walk running, whether the text is censored (SSH under no_log) or reaches the advisory category (WinRM)."""

RUNS = [{"name": "message"}]


def check(evidence, require):
    run = evidence["message"]
    ssh = '"L-WINNER l-ssh.invalid {\\"l-ssh-message\\": {\\"rounds\\": 1, \\"category\\": \\"not-ready\\"}, ' \
          '\\"l-ssh-winner\\": {\\"rounds\\": 1, \\"category\\": \\"worked\\"}}"'
    winrm = '"L-WINNER l-winrm.invalid {\\"l-winrm-message\\": {\\"rounds\\": 1, \\"category\\": \\"configuration\\"}, ' \
            '\\"l-winrm-winner\\": {\\"rounds\\": 1, \\"category\\": \\"worked\\"}}"'
    require(ssh in run.log, "the SSH walk stopped on message text")
    require(winrm in run.log, "the WinRM walk stopped on message text")
    raised = [r for r in run.of("winrm", kind="open_shell") if r.get("result") == "raised"]
    require(len(raised) == 1 and "must install" in raised[0]["message"], f"WinRM refusal {raised}")
    return [
        "ssh: the refusal text is censored under no_log (not-ready); the next set worked",
        f"winrm: remote text {raised[0]['message']!r} selected the advisory 'configuration' category; the next set worked",
    ]
