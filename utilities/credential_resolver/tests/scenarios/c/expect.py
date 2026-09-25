"""c. pre-policy: Medium, Medium, High wins only elevated; probes never multiplex; an SSH winner's
pre-existing control master is stopped at publication and a non-SSH winner gets no reset."""

RUNS = [{"name": "policy"}]


def check(evidence, require):
    run = evidence["policy"]
    calls = [c for c in run.records["ssh"] if c["host"] == "192.0.2.4"]
    sequence = [(c["mode"], c["user"].split("-IDENTITY")[0],
                 next((word for word in ("c-master", "id -u", "c-ordinary") if word in c["command"]), ""))
                for c in calls]
    require(sequence == [
        ("exec", "c-high", "c-master"),
        ("exec", "c-medium-one", "id -u"),
        ("exec", "c-medium-two", "id -u"),
        ("exec", "c-high", "id -u"),
        ("check", "c-high", ""),
        ("stop", "c-high", ""),
        ("exec", "c-high", "c-ordinary"),
    ], f"unexpected ssh sequence {sequence}")
    master, *probes, checked, stopped, ordinary = calls[0], *calls[1:4], calls[4], calls[5], calls[6]
    path = master["control_master"]
    require(path and path.endswith(tuple("0123456789abcdef")), "the pre-resolution task opened no master")
    for probe in probes:
        require('ControlPath="none"' in probe["argv"] and "controlpath" not in probe["effective"]
                and "control_master" not in probe, f"probe {probe['user']} is multiplexed")
    require(checked["effective"]["controlpath"] == [path] and checked["rc"] == 0,
            "the reset did not find the winner's pre-existing master")
    require(stopped["effective"]["controlpath"] == [path] and stopped["rc"] == 0,
            "the reset did not stop the winner's master")
    require(ordinary["control_master"] == path, "the ordinary task did not reuse the winner's path")
    require("C-WINNER c-high" in run.log and "C-WINNER c-local" in run.log, "winners not published")
    ssh_line = "'c-ssh.invalid' works as 'c-high' (ssh_publickey, user 'c-high-IDENTITY-CANARY')"
    local_line = "'c-local.invalid' works as 'c-local' (local, user '<none>')"
    require(ssh_line in run.log and local_line in run.log, "success lines missing")
    local_play = run.play("Scenario C | A Non-SSH Winner Is Not Reset")
    reset = run.task("Reset An SSH Winner Connection", local_play)
    require(len(reset) == 1 and reset[0].strip() == "skipping: [c-local.invalid]",
            "a reset ran for the local winner")
    require(not run.touched("192.0.2.5"), "the local winner produced stub traffic")
    return [
        ssh_line,
        local_line,
        f"ssh sequence: {sequence}",
        f"probe argv ControlPath: {[a for p in probes for a in p['argv'] if a.startswith('ControlPath')]}",
        f"pre-resolution master {path}: check rc={checked['rc']}, stop rc={stopped['rc']}",
        "local winner: reset task skipped, zero stub records",
    ]
