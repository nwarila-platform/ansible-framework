"""j. budget: six hosts and six forks share one wrong-password account under a budget of two, across
serial batches, both invocations and a later play; several sets for one account stop at the budget;
an accepted password refunds only its own booking; a non-linear strategy is refused; mixed accounts
with a winning host and an attempts-exhausted host ahead, and tallies from a host outside the play."""
import json

MECHANISM_POISON = {"ANSIBLE_SSH_PASSWORD_MECHANISM": "sshpass"}
RUNS = [
    {"name": "six-forks", "args": ["-f", "6"], "env": MECHANISM_POISON},
    {"name": "serial-batches", "args": ["-f", "6", "-e", "j_serial=2"], "env": MECHANISM_POISON},
    {"name": "sets", "inventory": "inventory-sets.yml", "playbook": "sets.yml"},
    {"name": "strategy-free", "env": {"ANSIBLE_STRATEGY": "free"}, "expected_rc": 2},
    {"name": "mixed", "inventory": "inventory-mixed.yml", "playbook": "mixed.yml", "args": ["-f", "6"]},
    {"name": "ineligible-ahead", "inventory": "inventory-ineligible.yml", "playbook": "ineligible.yml"},
]
HOSTS = [f"j-{n}.invalid" for n in range(1, 7)]


def categories(run, label):
    found = {}
    for message in run.messages():
        if message.startswith(label + " "):
            host, category = message.split(" ")[1:3]
            found[host] = category
    return found


def observations(run, label):
    found = {}
    for message in run.messages():
        if message.startswith(label + " "):
            host, payload = message.split(" ", 2)[1:]
            found[host] = json.loads(payload.replace('\\"', '"'))
    return found


def check(evidence, require):
    lines = []
    for name in ("six-forks", "serial-batches"):
        run = evidence[name]
        calls = run.ssh(mode="exec")
        require([c["host"] for c in calls] == ["192.0.2.31", "192.0.2.32"], f"{name} submissions {[c['host'] for c in calls]}")
        require(all(c["askpass"]["armed"] and c["authentication"] == "password-rejected" for c in calls),
                f"{name}: submissions were not askpass password attempts")
        first = categories(run, "J-FIRST")
        require(first == {**{h: "not-ready" for h in HOSTS[:2]}, **{h: "budget-exhausted" for h in HOSTS[2:]}},
                f"{name} first invocation {first}")
        require(categories(run, "J-SECOND") == {h: "budget-exhausted" for h in HOSTS}, f"{name} second invocation")
        require(categories(run, "J-LATER") == {h: "budget-exhausted" for h in HOSTS}, f"{name} later play")
        grants = run.task("Decide Password Budget Grant")
        require(grants and grants[0].count("ok: [j-") == (6 if name == "six-forks" else 2),
                f"{name}: the first grant was not decided in lockstep")
        lines.append(f"{name}: exactly 2 submissions (j-1, j-2, askpass despite sshpass poisons); first "
                     "invocation 4 budget-exhausted; second invocation and later play 6 of 6 budget-exhausted")

    sets = evidence["sets"]
    three = sets.ssh(mode="exec", host="192.0.2.37")
    require([c["user"].split("-IDENTITY")[0] for c in three] == ["j-set-one", "j-set-two"],
            f"three sets submissions {[c['user'] for c in three]}")
    three_obs = observations(sets, "J-SETS")["j-three-sets.invalid"]
    require(three_obs["j-set-three"]["category"] == "budget-exhausted", f"three sets {three_obs}")
    refund = sets.ssh(mode="exec", host="192.0.2.38")
    require([c["rc"] for c in refund] == [255, 0], f"refund attempts {[c['rc'] for c in refund]}")
    require('J-TALLY j-refund.invalid {\\"j-refund-account\\": 1}' in sets.log, "refund did not keep the rejected booking")
    lines.append("sets: three sets for one account submit twice and the third is budget-exhausted with no traffic; "
                 "wrong-then-right leaves the account tally at 1 (the accepted password refunded only itself)")

    free = evidence["strategy-free"]
    require(categories(free, "J-FIRST") == {} and not free.traffic()
            and "credential_resolver rule 0 requires controller debug mode off and the configured linear strategy"
            in free.log, "ANSIBLE_STRATEGY=free was not refused before traffic")
    lines.append("ANSIBLE_STRATEGY=free: refused by rule 0 before any traffic")

    mixed = evidence["mixed"]
    submitted = [(c["host"], c["user"].split(".invalid")[0]) for c in mixed.ssh(mode="exec")
                 if c["askpass"]["armed"]]
    require(submitted == [("192.0.2.40", "jm-outside-IDENTITY-CANARY".split(".invalid")[0]),
                          ("192.0.2.43", "jm-3"), ("192.0.2.44", "jm-4"), ("192.0.2.45", "jm-5")],
            f"mixed submissions {submitted}")
    grants = mixed.task("Decide Password Budget Grant", mixed.play("Scenario J | Mixed Accounts"))
    require(grants and all(block.count("ok: [jm-") == 1 for block in grants),
            "mixed sets were not decided one host at a time")
    batch = observations(mixed, "J-MIXED")
    require(batch["jm-1.invalid"] == {"jm-key": {"rounds": 1, "category": "worked"}}, f"jm-1 {batch['jm-1.invalid']}")
    require(batch["jm-6.invalid"]["jm-password"]["category"] == "budget-exhausted", f"jm-6 {batch['jm-6.invalid']}")
    lines.append("mixed: outside tally 1 on account a; jm-1 won ahead (reserved nothing), jm-3 on account b "
                 "(reserved nothing against a), jm-4 and jm-5 submitted to reach exactly 3, jm-6 budget-exhausted")

    ineligible = evidence["ineligible-ahead"]
    submitted = [c["host"] for c in ineligible.ssh(mode="exec")]
    require(submitted == ["192.0.2.47", "192.0.2.48", "192.0.2.48"], f"ineligible submissions {submitted}")
    lines.append("ineligible-ahead: ji-2 (attempts 1) is ineligible in round 2 and reserves nothing; "
                 "ji-4 submits in rounds 1 and 2 to reach exactly the budget of 3")
    return lines
