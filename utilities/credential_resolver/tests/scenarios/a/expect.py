"""a. walk trace: unequal attempts over four rounds with pauses only between winnerless rounds, two
one-shot password sets that stop after round 1, a round-3 winner, and the full default 60 rounds."""

RUNS = [{"name": "walk", "timeout": 1500}]


def users(run, address):
    return [c["user"].split("-IDENTITY")[0] for c in run.ssh(mode="exec") if c["host"] == address]


def pauses(run, play):
    blocks = run.task("Pause Before A Follow-Up Round", run.play(play))
    return sum("Pausing for" in block for block in blocks), len(blocks)


def check(evidence, require):
    run = evidence["walk"]
    lines = []

    walk = users(run, "192.0.2.1")
    require(walk == ["a-one", "a-two", "a-four", "a-two", "a-four", "a-four", "a-four"],
            f"four-round order {walk}")
    paid = pauses(run, "Scenario A | Three Sets")
    require(paid == (3, 4), f"four-round pauses {paid}")
    summary = ("A-WINNERLESS rounds=4 No credential set worked for 'a-walk.invalid': "
               "a-one (rounds 1, not-ready); a-two (rounds 2, not-ready); "
               "a-four (rounds 4, not-ready)")
    require(summary in run.log, "four-round failure summary")
    lines += [f"four rounds: exec order {walk}; pauses paid {paid[0]} of {paid[1]} pause tasks", summary]

    passwords = users(run, "192.0.2.2")
    require(passwords == ["a-password-one", "a-password-two"], f"password order {passwords}")
    paid = pauses(run, "Scenario A | Two One-Shot")
    require(paid == (0, 1), f"password pauses {paid}")
    summary = ("A-WINNERLESS rounds=1 No credential set worked for 'a-passwords.invalid': "
               "a-password-one (rounds 1, not-ready); a-password-two (rounds 1, not-ready)")
    require(summary in run.log, "password failure summary")
    armed = [c["askpass"]["armed"] for c in run.ssh(mode="exec", host="192.0.2.2")]
    require(armed == [True, True], "each password attempt armed one askpass segment")
    lines += [f"password sets: exec order {passwords}; pauses paid {paid[0]}; askpass armed {armed}", summary]

    third = users(run, "192.0.2.3")
    require(third == ["a-third"] * 3, f"round-three order {third}")
    paid = pauses(run, "Scenario A | A Winner In Round Three")
    require(paid == (2, 3), f"round-three pauses {paid}")
    require("A-WINNER rounds=3 a-third" in run.log, "round-three winner")
    lines.append(f"round-three winner: {len(third)} probes, pauses paid {paid[0]} of {paid[1]}, none after the win")

    first, second = users(run, "192.0.2.61"), users(run, "192.0.2.62")
    require(len(first) == 1 and len(second) == 3, f"batch probes {len(first)} and {len(second)}")
    paid = pauses(run, "Scenario A | A Batch Keeps Pausing")
    require(paid == (2, 3), f"batch pauses {paid}")
    batch = run.play("Scenario A | A Batch Keeps Pausing")
    rounds = [line.split(" for ", 1)[1] for line in batch.splitlines() if "round.yml for " in line]
    require(rounds == ["a-batch-first.invalid, a-batch-second.invalid", "a-batch-second.invalid",
                       "a-batch-second.invalid"], f"round inclusions {rounds}")
    require("A-BATCH a-batch-first.invalid rounds=1" in run.log and "A-BATCH a-batch-second.invalid rounds=3"
            in run.log, "batch round of each win")
    lines.append("batch: the first host won in round 1 and expanded no later round; the batch still paused "
                 "twice for the second host, which won in round 3")

    sixty = users(run, "192.0.2.60")
    require(sixty == ["a-sixty"] * 60, f"sixty-round probes {len(sixty)}")
    paid = pauses(run, "Scenario A | The Full Sixty-Round Walk")
    require(paid == (59, 60), f"sixty-round pauses {paid}")
    summary = ("A-WINNERLESS rounds=60 No credential set worked for 'a-sixty.invalid': "
               "a-sixty (rounds 60, not-ready)")
    require(summary in run.log, "sixty-round failure summary")
    lines += [f"sixty rounds: {len(sixty)} probes, pauses paid {paid[0]} of {paid[1]}", summary]
    return lines
