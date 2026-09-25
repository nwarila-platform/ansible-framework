#!/usr/bin/env python3
"""Generate credential_resolver's reviewed option table from the installed controller."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def use_ansible_interpreter() -> None:
    executable = shutil.which("ansible-doc")
    if not executable:
        raise SystemExit("ansible-doc is not installed")
    environment = Path(executable).resolve().parent.parent
    interpreter = environment / "bin" / "python"
    if Path(sys.prefix).resolve() != environment.resolve():
        os.execv(str(interpreter), [str(interpreter), *sys.argv])


if __name__ == "__main__":
    use_ansible_interpreter()

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = Path(__file__).with_name("credential-resolver-classification.yml")
OUTPUT = ROOT / "utilities" / "credential_resolver" / "vars" / "main.yml"
INTERNAL_WINRM = {
    "self",
    "endpoint",
    "transport",
    "username",
    "password",
    "scheme",
    "path",
    "kinit_mode",
    "kinit_cmd",
}
PLAY_CONTEXT_KEYS = ("play_context_aliases", "play_context_neutral")


def ansible_doc(*args: str) -> str:
    env = os.environ.copy()
    env.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/credential-resolver-generator")
    Path(env["ANSIBLE_LOCAL_TEMP"]).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ansible-doc", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return result.stdout


def installed_plugins(plugin_type: str) -> list[str]:
    return sorted(line.split()[0] for line in ansible_doc("-t", plugin_type, "-l").splitlines() if line.strip())


def option_docs(plugin_type: str, plugin: str) -> dict[str, dict]:
    document = json.loads(ansible_doc("-j", "-t", plugin_type, plugin))
    return next(iter(document.values()))["doc"].get("options") or {}


def flatten_classification(section: dict, expected: set[str], label: str) -> dict[str, dict]:
    flattened: dict[str, dict] = {}
    for option_class, entries in section.items():
        if isinstance(entries, list):
            entries = {entry: {} for entry in entries}
        for option, details in entries.items():
            if option in flattened:
                raise SystemExit(f"duplicate classification: {label}.{option}")
            details = details or {}
            if "neutral" not in details:
                raise SystemExit(f"missing neutral classification: {label}.{option}")
            flattened[option] = {"class": option_class, **details}
    actual = set(flattened)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise SystemExit(f"classification drift for {label}: missing={missing}, extra={extra}")
    return flattened


def canonical_name(aliases: list[str], details: dict) -> str | None:
    if details.get("canonical"):
        if details["canonical"] not in aliases:
            raise SystemExit(f"canonical alias {details['canonical']!r} is not in {aliases!r}")
        return details["canonical"]
    return next((alias for alias in aliases if alias != "inventory_hostname"), None)


def group(plugin_type: str, plugin: str, option: str, aliases: list[str], details: dict) -> dict:
    return {
        "plugin_type": plugin_type,
        "plugin": plugin,
        "option": option,
        "canonical": canonical_name(aliases, details),
        "aliases": aliases,
        "class": details["class"],
        "neutral": details.get("neutral"),
        **{key: details[key] for key in PLAY_CONTEXT_KEYS if key in details},
    }


def main() -> None:
    with CLASSIFICATION.open(encoding="utf-8") as stream:
        classification = yaml.safe_load(stream)

    groups: list[dict] = []
    discovered: dict[str, list[str]] = {}
    for plugin_type in ("connection", "become"):
        plugins = installed_plugins(plugin_type)
        discovered[plugin_type] = plugins
        classified_plugins = set(classification[plugin_type])
        if set(plugins) != classified_plugins:
            raise SystemExit(
                f"plugin classification drift for {plugin_type}: "
                f"missing={sorted(set(plugins) - classified_plugins)}, "
                f"extra={sorted(classified_plugins - set(plugins))}"
            )
        for plugin in plugins:
            options = option_docs(plugin_type, plugin)
            classes = flatten_classification(
                classification[plugin_type][plugin], set(options), f"{plugin_type}.{plugin}"
            )
            for option in sorted(options):
                aliases = [entry["name"] for entry in options[option].get("vars", [])]
                groups.append(group(plugin_type, plugin, option, aliases, classes[option]))

    from ansible.constants import MAGIC_VARIABLE_MAPPING
    from winrm.protocol import Protocol

    magic = flatten_classification(classification["magic"], set(MAGIC_VARIABLE_MAPPING), "magic")
    for option, aliases in MAGIC_VARIABLE_MAPPING.items():
        groups.append(group("magic", "ansible.builtin.play_context", option, list(aliases), magic[option]))

    parameters = inspect.signature(Protocol.__init__).parameters
    protocol_args = [name for name in parameters if name not in INTERNAL_WINRM]
    protocol = flatten_classification(
        classification["winrm_protocol"], set(protocol_args), "winrm_protocol"
    )
    for option in sorted(protocol_args):
        groups.append(
            {
                **group(
                    "connection",
                    "ansible.builtin.winrm",
                    f"protocol.{option}",
                    [f"ansible_winrm_{option}"],
                    protocol[option],
                ),
                "protocol_default": parameters[option].default,
            }
        )

    groups.sort(key=lambda item: (item["plugin_type"], item["plugin"], item["option"]))
    payload = {
        "credential_resolver_installed_plugins": discovered,
        "credential_resolver_option_groups": groups,
    }
    rendered = "---\n# Generated by scripts/generate-credential-resolver-vars.py; do not edit.\n"
    rendered += yaml.safe_dump(payload, sort_keys=False, width=1000)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
