"""b. fresh: set 1 is refused, set 2 works and is published; the next ordinary task runs as set 2."""

PREFIX = ["-F", "/dev/null", "-o", "PreferredAuthentications=publickey", "-o", "IdentitiesOnly=yes",
          "-o", "BatchMode=yes"]
CONFIGURED = ["-C", "-o", "ControlMaster=auto", "-o", "ControlPersist=60s"]
KEY = "utilities/credential_resolver/tests/fixtures/id_stub.pub"

RUNS = [{"name": "fresh"}]


def check(evidence, require):
    run = evidence["fresh"]
    calls = run.ssh(mode="exec")
    require([(c["user"], c["rc"]) for c in calls] == [
        ("b-refused-IDENTITY-CANARY", 255),
        ("b-winner-IDENTITY-CANARY", 0),
        ("b-winner-IDENTITY-CANARY", 0),
    ], f"unexpected exec sequence {[(c['user'], c['rc']) for c in calls]}")
    refused, probe, ordinary = calls
    for call in calls:
        require(call["argv"][:len(PREFIX + CONFIGURED)] == PREFIX + CONFIGURED,
                f"argv does not start with the prefix and configured ssh_args: {call['argv'][:12]}")
    for call in (refused, probe):
        require('ControlPath="none"' in " ".join(call["argv"]) and "controlpath" not in call["effective"],
                "a probe is multiplexed")
    require("echo b-ordinary" in ordinary["command"], "the ordinary task is not the third exec")
    require(ordinary["effective"]["identityfile"] == [KEY], f"identities {ordinary['effective']['identityfile']}")
    require(ordinary["effective"]["identitiesonly"] == ["yes"], "identitiesonly is not yes")
    require(ordinary.get("control_master"), "the ordinary task did not open its own control master")
    resets = run.ssh(mode="check")
    require(len(resets) == 1 and resets[0]["user"] == "b-winner-IDENTITY-CANARY" and resets[0]["rc"] == 255,
            "the SSH winner reset did not check exactly the winner's absent master")
    require(not run.ssh(mode="stop"), "a stop was sent with no master open")
    line = "'b-fresh.invalid' works as 'b-winner' (ssh_publickey, user 'b-winner-IDENTITY-CANARY')"
    require(line in run.log, "success line missing")
    require("B-PUBLISHED b-winner ssh_publickey" in run.log, "published facts missing")
    return [
        line,
        f"exec sequence: {[(c['user'], c['rc']) for c in calls]}",
        f"ordinary argv[:13]={ordinary['argv'][:13]}",
        f"ordinary effective identityfile={ordinary['effective']['identityfile']} controlpath={ordinary['effective']['controlpath']}",
    ]
