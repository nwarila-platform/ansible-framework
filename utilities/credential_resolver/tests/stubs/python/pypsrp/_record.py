from __future__ import annotations

import json
import os
from pathlib import Path


def record(value: dict) -> None:
    with Path(os.environ["CREDRES_PSRP_LOG"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
