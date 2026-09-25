"""n. --tags with the resolver tagged always resolves; --check resolves; the gated second call does
not run when no restart was scheduled; a re-run on a converged host wins on the first probe with
changed=0."""
import re

RUNS = [
    {"name": "plain"},
    {"name": "tags", "args": ["--tags", "selected"]},
    {"name": "check", "args": ["--check"]},
    {"name": "tags-and-check", "args": ["--tags", "selected", "--check"]},
]


def check(evidence, require):
    lines = []
    for name, run in evidence.items():
        probes = [c for c in run.ssh(mode="exec") if "echo ready" in c["command"]]
        require(len(probes) == 1, f"{name}: {len(probes)} probes")
        require("'n-contract.invalid' works as 'n-winner' (ssh_publickey, user 'n-IDENTITY-CANARY')" in run.log,
                f"{name}: success line")
        entries = run.task("Refuse Unsafe Controller Modes")
        require(len(entries) == 2 and entries[0].lstrip().startswith("ok:")
                and entries[1].strip() == "skipping: [n-contract.invalid]", f"{name}: gated second call {entries}")
        selected = [c for c in run.ssh(mode="exec") if "n-selected" in c["command"]]
        require(len(selected) == 1 and selected[0]["user"] == "n-IDENTITY-CANARY", f"{name}: selected task")
        recap = re.search(r"n-contract\.invalid\s+: ok=\d+\s+changed=(\d+)", run.log)
        require(recap and recap.group(1) == "0", f"{name}: recap {recap.group(0) if recap else None}")
        lines.append(f"{name}: resolved on the first probe, gated second call skipped, selected task ran as "
                     f"the winner, changed=0")
    return lines
