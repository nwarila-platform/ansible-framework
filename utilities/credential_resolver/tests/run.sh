#!/usr/bin/env bash
# Runs every scenario (or the letters given) inside private network and mount namespaces.
set -euo pipefail

tests=$(cd "$(dirname "$0")" && pwd)
python=/root/.local/share/pipx/venvs/ansible-core/bin/python

if [[ "${1:-}" != --isolated ]]; then
  if [[ $EUID -ne 0 ]]; then
    printf 'run.sh needs root to create the network and mount namespaces\n' >&2
    exit 1
  fi
  root=$(mktemp -d -p "${TMPDIR:-/tmp}" crs.XXXXXX)
  printf 'credential-resolver scenario root: %s\n' "$root"
  exec unshare --net --mount --propagation private -- "$0" --isolated "$root" "$@"
fi
shift
root=$1
shift

# The aws_ssm plugin prefers this path over PATH; reaching the real binary must fail at once.
real_plugin=/usr/local/bin/session-manager-plugin
if [[ -e "$real_plugin" ]]; then
  printf '#!/bin/sh\nprintf "real session-manager-plugin reached\\n" >> %s/tripwire.log\nexit 97\n' \
    "$root" > "$root/tripwire"
  chmod 0755 "$root/tripwire"
  mount --bind "$root/tripwire" "$(readlink -f "$real_plugin")"
fi

exec "$python" "$tests/verify.py" "$root" "$@"
