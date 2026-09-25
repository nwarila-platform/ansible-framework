from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def record(kind, argv, stdin=""):
    with Path(os.environ["CREDRES_MISC_LOG"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "kind": kind,
            "argv": list(argv),
            "stdin": stdin,
        }, sort_keys=True) + "\n")


def response(command):
    return "0\n" if "id -u" in command else "ready\n"


def main(kind):
    argv = sys.argv[1:]
    # Only qvm-run takes its command on stdin; the other plugins may never close it.
    stdin = sys.stdin.read() if kind == "qubes" else ""
    record(kind, argv, stdin)
    if kind == "iocage" and argv[:2] == ["get", "host_hostuuid"]:
        sys.stdout.write("stub-uuid\n")
    elif kind == "jls":
        sys.stdout.write("k-jail-target ioc-stub-uuid\n")
    elif kind == "lxd" and argv[1:2] == ["local:k-lxd-absent-target"]:
        sys.stderr.write("error: not found\n")
        raise SystemExit(1)
    else:
        sys.stdout.write(response(" ".join(argv) + " " + stdin))
