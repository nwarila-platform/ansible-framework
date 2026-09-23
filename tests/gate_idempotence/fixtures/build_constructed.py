#!/usr/bin/env python3
"""Build the deterministic constructed fixtures for the GATE-01 test suite."""

import argparse
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_bytes().decode("utf-8"))


def dump(obj, path):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    # T7 -- the non-idempotent second converge under the leg-addressable name.
    shutil.copyfile(HERE / "nonidempotent-2-SPIKE600-1.json",
                    out / "converge-2-NONIDEM600-1.json")

    # T13 -- inventory-main plus a literal localhost in the union and in hostvars.
    inv = load("inventory-main.json")
    inv["controllers"]["hosts"].append("localhost")
    inv["_meta"]["hostvars"]["localhost"] = {}
    dump(inv, out / "inventory-localhost-present.json")
    shutil.copyfile(HERE / "converge-2-SPIKE100-1.json",
                    out / "converge-2-LOCALHOST110-1.json")

    # T14 -- clean T1 with exactly one counter key deleted.
    art = load("converge-2-SPIKE100-1.json")
    del art["stats"]["node_a"]["ignored"]
    dump(art, out / "converge-2-NOIGNORE120-1.json")

    # T15 -- an inventory dump truncated mid-object: exactly nine bytes, no newline.
    (out / "inventory-truncated.json").write_bytes(b'{"_meta":')

    # T17 -- clean T1 with exactly one failures counter set to 1.
    art = load("converge-2-SPIKE100-1.json")
    art["stats"]["node_a"]["failures"] = 1
    dump(art, out / "converge-2-FAILURES130-1.json")

    # T18 -- the check leg with every stats.changed zeroed, task results untouched.
    art = load("check-diff-SPIKE700-1.json")
    for host in art["stats"]:
        art["stats"][host]["changed"] = 0
    dump(art, out / "check-diff-TASKONLY710-1.json")

    # T20 -- clean T1 under a check-diff name, one changed task result for the
    # EXCLUDED controller and no other change.
    art = load("converge-2-SPIKE100-1.json")
    art["plays"][0]["tasks"][0]["hosts"]["controller_explicit"] = {"changed": True}
    dump(art, out / "check-diff-CTRL720-1.json")


if __name__ == "__main__":
    main()
