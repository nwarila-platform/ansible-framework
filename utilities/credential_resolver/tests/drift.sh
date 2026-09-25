#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/../../.." && pwd)
run_root=$(mktemp -d -p "${TMPDIR:-/tmp}" credential-resolver-drift.XXXXXX)
export PATH="$PATH:/root/.local/bin"
export ANSIBLE_HOME="$run_root/home"
export ANSIBLE_COLLECTIONS_PATH=/root/.ansible/collections
export ANSIBLE_LOCAL_TEMP="$run_root/local"
export TMPDIR="$run_root/tmp"
mkdir -p "$ANSIBLE_LOCAL_TEMP" "$TMPDIR"
cp "$repo_root/utilities/credential_resolver/vars/main.yml" "$run_root/main.yml"
/root/.local/share/pipx/venvs/ansible-core/bin/python \
  "$repo_root/scripts/generate-credential-resolver-vars.py"
cmp "$run_root/main.yml" "$repo_root/utilities/credential_resolver/vars/main.yml"
sha256sum "$run_root/main.yml" "$repo_root/utilities/credential_resolver/vars/main.yml"
printf 'drift-test: PASS — generated vars/main.yml is byte-identical\n'
