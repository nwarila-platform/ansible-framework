#!/usr/bin/env python3
"""Judge Ansible JSON callback artifacts for GATE-01."""

import argparse
import json
from pathlib import Path


COUNTERS = ("changed", "unreachable", "failures", "ignored")


def fail(message):
    print("FAIL: " + message)
    raise SystemExit(1)


def artifact_path(args):
    return args.artifact_dir / f"{args.leg}-{args.run_id}-{args.run_attempt}.json"


def host_union(inventory):
    union = set()
    for name, body in inventory.items():
        if name == "_meta" or not isinstance(body, dict):
            continue
        union.update(body.get("hosts", []) or [])
    return union


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-dump", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--leg", required=True, choices=("converge-2", "check-diff"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()

    artifact = artifact_path(args)
    if not artifact.is_file():
        fail("artifact absent: " + str(artifact))

    try:
        artifact_text = artifact.read_text(encoding="utf-8")
        result = json.loads(artifact_text)
    except json.JSONDecodeError as exc:
        fail("unreadable JSON: " + str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        fail("unreadable JSON: " + str(exc))

    try:
        inventory_text = args.inventory_dump.read_text(encoding="utf-8")
        inventory = json.loads(inventory_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("unreadable inventory dump: " + str(exc))

    hostvars = inventory.get("_meta", {}).get("hostvars", {})
    all_hosts = host_union(inventory)
    excluded = sorted(
        h
        for h in all_hosts
        if h == "localhost" or hostvars.get(h, {}).get("ansible_connection") == "local"
    )
    expected = sorted(all_hosts - set(excluded))
    if not expected:
        fail("empty expected host set")

    stats = result.get("stats", {})
    missing = sorted(set(expected) - set(stats))
    if missing:
        fail("missing expected hosts: " + ",".join(missing))

    judged = sorted((set(expected) | set(stats)) - set(excluded))

    counter_bad = []
    for host in judged:
        for counter in COUNTERS:
            value = stats[host].get(counter, "missing")
            if value != 0:
                counter_bad.append(f"{host}.{counter}={value}")

    task_bad = []
    if args.leg == "check-diff":
        for play_index, play in enumerate(result.get("plays", [])):
            for task_index, task in enumerate(play.get("tasks", [])):
                for host in sorted(task.get("hosts", {})):
                    if task["hosts"][host].get("changed") is True:
                        task_bad.append(f"p{play_index}t{task_index}.{host}")

    reasons = []
    if counter_bad:
        reasons.append("four-zero predicate: " + ",".join(counter_bad))
    if task_bad:
        reasons.append("check leg predicted change: " + ",".join(task_bad))
    if reasons:
        fail("; ".join(reasons))

    print(
        f"PASS: {artifact.name}; expected={','.join(expected) or '-'}; "
        f"excluded={','.join(excluded) or '-'}"
    )


if __name__ == "__main__":
    main()
