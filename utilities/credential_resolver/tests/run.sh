#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
framework_dir=$(cd "$test_dir/../../.." && pwd)
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/credential-resolver.XXXXXX")
trap 'rm -rf "$run_dir"' EXIT
mkdir "$run_dir/cp" "$run_dir/python" "$run_dir/python/winrm"
export ANSIBLE_SSH_AGENT=auto
export ANSIBLE_SSH_CONTROL_PATH_DIR="$run_dir/cp"
export CREDENTIAL_RESOLVER_CANARY_A='canary-one-7jL4wK9q'
export CREDENTIAL_RESOLVER_CANARY_B='canary-two-2mR8xP5v'
export CREDENTIAL_RESOLVER_DOWN_CALLS=0
export CREDENTIAL_RESOLVER_KEY_FILE="$run_dir/id"
export CREDENTIAL_RESOLVER_TEST_LOG
export CREDENTIAL_RESOLVER_WINRM_LOG="$run_dir/winrm.log"
export CREDENTIAL_RESOLVER_TEST_SSH="$run_dir/ssh"
cat > "$CREDENTIAL_RESOLVER_TEST_SSH" <<'STUB'
#!/bin/sh
refuse() { printf 'ssh: connect to host 127.0.0.1: Connection refused\r\n' >&2; exit 255; }
args=$*; user=$(printf '%s\n' "$args" | sed -n 's/.*User="\([^"]*\)".*/\1/p')
auth=other
case "$user" in
  publication-key-content) case "$args" in *IdentitiesOnly=yes*PasswordAuthentication=no*) [ -z "${SSH_ASKPASS:-}" ] && auth=key-content || auth=missing ;; *) auth=missing ;; esac ;;
  publication-key-file) case "$args" in *IdentityFile=\"$CREDENTIAL_RESOLVER_KEY_FILE\"*PasswordAuthentication=no*) [ -z "${SSH_ASKPASS:-}" ] && auth=key-file || auth=missing ;; *) auth=missing ;; esac ;;
  publication-password) [ -n "${SSH_ASKPASS:-}" ] && auth=password || auth=missing ;;
esac
printf 'USER=%s AUTH=%s ASKPASS=%s ARGS=%s\n' "$user" "$auth" "${SSH_ASKPASS:+set}" "$args" >> "$CREDENTIAL_RESOLVER_TEST_LOG"
[ "$auth" != missing ] || refuse
calls=$(($(cat "$CREDENTIAL_RESOLVER_TEST_LOG.calls" 2>/dev/null || printf 0) + 1))
printf '%s\n' "$calls" > "$CREDENTIAL_RESOLVER_TEST_LOG.calls"
[ "$calls" -gt "${CREDENTIAL_RESOLVER_DOWN_CALLS:-0}" ] || refuse
case "$user" in
  closed-*) refuse ;;
  not-elevated) case "$args" in
    *Get-CimInstance*) printf 'Access denied\r\n' >&2; exit 1 ;;
    *'echo ready'*) printf 'READY\r\n' ;;
    *) printf 'MEDIUM-OUT\r\n100\r\n'; printf 'REFUSAL-ERR\r\n' >&2 ;; esac ;;
  command-failure) printf 'FAILURE-OUT\r\n'; printf 'FAILURE-ERR\r\n' >&2; exit 7 ;;
  elevated-winner)
    printf 'S-1-16-12288\r\n200\r\n'; printf 'WINNER-ERR\r\n' >&2 ;;
  publication-key-content|publication-key-file)
    case "$args" in *'echo after'*) printf 'AFTER-OUT\r\n' ;; *) printf 'S-1-16-12288\r\n200\r\n' ;; esac ;;
  publication-password)
    case "$args" in *'echo after'*) printf 'AFTER-OUT\r\n' ;; *) printf 'MEDIUM-OUT\r\n100\r\n' ;; esac ;;
  post-new) printf 'S-1-16-12288\r\n300\r\n' ;;
  post-old) printf 'S-1-16-12288\r\n250\r\n' ;;
  posix-low|posix-root)
    marker=$(printf '%s\n' "$args" | sed -n 's/.*\(BECOME-SUCCESS-[A-Za-z0-9]*\).*/\1/p')
    printf '%s\n' "$marker"
    if [ "$user" = posix-low ]; then printf '1000\r\n'; else printf '0\r\n'; fi ;;
  *) refuse ;;
esac
STUB
chmod 0700 "$CREDENTIAL_RESOLVER_TEST_SSH"
cat > "$run_dir/python/winrm/__init__.py" <<'PY'
from .protocol import Protocol
FEATURE_SUPPORTED_AUTHTYPES = ['ntlm', 'kerberos']
PY
cat > "$run_dir/python/winrm/exceptions.py" <<'PY'
class WinRMError(Exception): pass
WinRMOperationTimeoutError = WinRMTransportError = WSManFaultError = WinRMError
PY
cat > "$run_dir/python/winrm/protocol.py" <<'PY'
import os
class Protocol:
    def __init__(self, endpoint, transport='plaintext', username=None, password=None,
                 message_encryption='auto'):
        if password != os.environ['CREDENTIAL_RESOLVER_CANARY_A']: raise ValueError('WinRM credential missing')
        if transport != 'ntlm': raise ValueError('WinRM transport missing')
        with open(os.environ['CREDENTIAL_RESOLVER_WINRM_LOG'], 'a', encoding='utf-8') as log:
            log.write(f'USER={username} ENDPOINT={endpoint} TRANSPORT={transport} '
                      f'ENCRYPTION={message_encryption}\n')
    def open_shell(self, codepage=65001): return 'shell'
    def _get_soap_header(self, **kwargs): return {}
    def run_command(self, shell_id, command, args, console_mode_stdin=False): return 'command'
    def send_message(self, message):
        return ('<Response><Stream Name="stdout">Uy0xLTE2LTEyMjg4DQoyMDANCg==</Stream>'
                '<CommandState State="x/CommandState/Done"/><ExitCode>0</ExitCode></Response>')
    def cleanup_command(self, shell_id, command_id): pass
    def close_shell(self, shell_id): pass
PY
ssh-keygen -q -t ed25519 -N '' -f "$CREDENTIAL_RESOLVER_KEY_FILE" </dev/null
logs=()
run_case() {
  local expectation=$1 label=$2 inventory=$3 playbook=$4; shift 4
  CREDENTIAL_RESOLVER_TEST_LOG="$run_dir/$label.ssh"; export CREDENTIAL_RESOLVER_TEST_LOG
  : > "$CREDENTIAL_RESOLVER_TEST_LOG"; logs+=("$run_dir/$label.out"); printf 'CASE %s: ' "$label"
  if (cd "$framework_dir" && ansible-playbook -i "$test_dir/$inventory" -vvv \
      "$test_dir/$playbook" "$@") > "$run_dir/$label.out" 2>&1; then result=ok; else result=fail; fi
  if [ "$result" != "$expectation" ]; then
    printf 'UNEXPECTED %s\n' "$result"; tail -40 "$run_dir/$label.out"; exit 1; fi
  printf 'PASS\n'
}
require_text() { if ! grep -Fq -- "$1" "$2"; then printf 'Missing expected text: %s\n' "$1"; exit 1; fi; }
reject_text() { local text=$1; shift; if grep -Fq -- "$text" "$@"; then
  printf 'Unexpected text found: %s\n' "$text"; exit 1; fi; }
run_case ok 2a-pass inventory.yml pass.yml
run_case ok 2a-check inventory.yml pass.yml --check
PYTHONPATH="$run_dir/python${PYTHONPATH:+:$PYTHONPATH}" run_case ok 2b-publication inventory.yml publication.yml
run_case ok 2c-input-role inventory-input.yml input.yml -e "@$test_dir/input-cases.yml"
for input_case in basic kerberos_integer kerberos_string missing_name null_name missing_user null_user; do
  export CREDENTIAL_RESOLVER_INPUT_CASE=$input_case
  run_case fail "2c-caller-$input_case" inventory-input.yml caller-example.yml \
    -e "@$test_dir/input-cases.yml"
  require_text 'needs a name, a user' "$run_dir/2c-caller-$input_case.out"
  [ ! -s "$CREDENTIAL_RESOLVER_TEST_LOG" ]
done
export CREDENTIAL_RESOLVER_DOWN_CALLS=3
export CREDENTIAL_RESOLVER_POST_USER=post-new
run_case ok 2e-caller-no-restart inventory-caller.yml caller-scenarios.yml
run_case ok 2e-caller-new-boot inventory-caller.yml caller-scenarios.yml -e __domain_member_boot_time__=250
export CREDENTIAL_RESOLVER_POST_USER=post-old
run_case fail 2e-caller-old-boot inventory-caller.yml caller-scenarios.yml -e __domain_member_boot_time__=250
[ "$(grep -c 'USER=post-old.*Get-CimInstance' "$run_dir/2e-caller-old-boot.ssh")" -eq 3 ]
export CREDENTIAL_RESOLVER_DOWN_CALLS=0
run_case ok 2f-posix-elevation inventory.yml posix-elevation.yml
require_text 'boot not newer than the floor' "$run_dir/2e-caller-old-boot.out"
if ! grep -Eq "works as 'elevated-winner'.*not-elevated.*REFUSAL-ERR" \
    "$run_dir/2e-caller-no-restart.out"; then printf 'The success report omitted the refusal.\n'; exit 1; fi
for secret in "$CREDENTIAL_RESOLVER_CANARY_A" "$CREDENTIAL_RESOLVER_CANARY_B"; do
  reject_text "$secret" "${logs[@]}"; done
if grep -Fq -f "$CREDENTIAL_RESOLVER_KEY_FILE" "${logs[@]}" \
    || grep -Fq -f "$CREDENTIAL_RESOLVER_KEY_FILE.pub" "${logs[@]}"; then
  printf 'Temporary key material appeared in case output.\n'; exit 1; fi
printf 'CASE 2d-secrecy: PASS (0 canary hits)\nAll credential resolver cases passed.\n'
