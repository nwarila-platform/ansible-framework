#!/usr/bin/env bash
# ============================================================================================= #
# File: tests/run.sh | Version 1.0.0                                                            #
# --- [ Description ] ------------------------------------------------------------------------- #
# Runs the resolver's local-only behavioral cases with ephemeral credentials and SSH fixture.
# ============================================================================================= #
set -euo pipefail
test_dir=$(cd "$(dirname "$0")" && pwd)
framework_dir=$(cd "$test_dir/../../.." && pwd)
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/credential-resolver.XXXXXX")
trap 'rm -rf "$run_dir"' EXIT
mkdir "$run_dir/cp"
export ANSIBLE_SSH_AGENT=auto ANSIBLE_SSH_CONTROL_PATH_DIR="$run_dir/cp"
stub="$run_dir/ssh"
cat > "$stub" <<'STUB'
#!/bin/sh
args=$*
user=$(printf '%s\n' "$args" | sed -n 's/.*User="\([^"]*\)".*/\1/p')
printf 'USER=%s ARGS=%s\n' "$user" "$args" >> "$CREDENTIAL_RESOLVER_TEST_LOG"
case "$user" in
  closed-*) printf 'ssh: connect to host 127.0.0.1: Connection refused\r\n' >&2; exit 255 ;;
  not-elevated)
    case "$args" in *'echo ready'*) printf 'READY\r\n' ;;
      *) printf 'MEDIUM-OUT\r\n100\r\n'; printf 'REFUSAL-ERR\r\n' >&2 ;; esac ;;
  command-failure) printf 'FAILURE-OUT\r\n'; printf 'FAILURE-ERR\r\n' >&2; exit 7 ;;
  elevated-winner|prior-user) printf 'S-1-16-12288\r\n200\r\n'; printf 'WINNER-ERR\r\n' >&2 ;;
  new-key) case "$args" in *'echo after'*) printf 'AFTER-OUT\r\n'; printf 'AFTER-ERR\r\n' >&2 ;;
      *) printf 'S-1-16-12288\r\n200\r\n' ;; esac ;;
  post-new) printf 'S-1-16-12288\r\n300\r\n' ;;
  post-old) printf 'S-1-16-12288\r\n200\r\n' ;;
  posix-low|posix-root)
    marker=$(printf '%s\n' "$args" | sed -n 's/.*\(BECOME-SUCCESS-[A-Za-z0-9]*\).*/\1/p')
    printf '%s\n' "$marker"
    if [ "$user" = posix-low ]; then printf '1000\r\n'; else printf '0\r\n'; fi
    ;;
  *) printf 'ssh: connect to host 127.0.0.1: Connection refused\r\n' >&2; exit 255 ;;
esac
STUB
chmod 0700 "$stub"
printf '%s\n' 'canary-one-7jL4wK9q' > "$run_dir/canary-a"
printf '%s\n' 'canary-two-2mR8xP5v' > "$run_dir/canary-b"
ssh-keygen -q -t ed25519 -N '' -f "$run_dir/id" </dev/null
export CREDENTIAL_RESOLVER_CANARY_A CREDENTIAL_RESOLVER_CANARY_B CREDENTIAL_RESOLVER_KEY_FILE
export CREDENTIAL_RESOLVER_TEST_LOG CREDENTIAL_RESOLVER_TEST_SSH="$stub"
CREDENTIAL_RESOLVER_CANARY_A=$(<"$run_dir/canary-a")
CREDENTIAL_RESOLVER_CANARY_B=$(<"$run_dir/canary-b")
CREDENTIAL_RESOLVER_KEY_FILE="$run_dir/id"
logs=()
run_case() {
  local expectation=$1 label=$2 inventory=$3 playbook=$4; shift 4
  CREDENTIAL_RESOLVER_TEST_LOG="$run_dir/$label.ssh"; export CREDENTIAL_RESOLVER_TEST_LOG
  : > "$CREDENTIAL_RESOLVER_TEST_LOG"; logs+=("$run_dir/$label.out")
  printf 'CASE %s: ' "$label"
  if (cd "$framework_dir" && ansible-playbook \
      -i "$test_dir/$inventory" -vvv "$test_dir/$playbook" "$@") \
      > "$run_dir/$label.out" 2>&1; then result=ok; else result=fail; fi
  if [ "$result" != "$expectation" ]; then
    printf 'UNEXPECTED %s\n' "$result"
    tail -40 "$run_dir/$label.out"
    exit 1
  fi
  printf 'PASS\n'
}
run_case ok 2a-pass inventory.yml pass.yml
run_case ok 2a-check inventory.yml pass.yml --check
run_case ok 2b-precedence inventory.yml precedence.yml
run_case ok 2c-input-role inventory.yml input.yml
for input_case in basic kerberos_integer kerberos_string missing_name \
    null_name missing_user null_user; do
  export CREDENTIAL_RESOLVER_INPUT_CASE=$input_case
  run_case fail "2c-caller-$input_case" inventory-input.yml caller-example.yml
  grep -Fq 'needs a name, a user' "$run_dir/2c-caller-$input_case.out"
  [ ! -s "$CREDENTIAL_RESOLVER_TEST_LOG" ]
done
export CREDENTIAL_RESOLVER_POST_USER=post-new
run_case ok 2e-caller-no-restart inventory-caller.yml caller-example.yml
run_case ok 2e-caller-new-boot inventory-caller.yml caller-example.yml \
  -e __domain_member_boot_time__=250
export CREDENTIAL_RESOLVER_POST_USER=post-old
run_case fail 2e-caller-old-boot inventory-caller.yml caller-example.yml \
  -e __domain_member_boot_time__=250
run_case ok 2f-posix-elevation inventory.yml posix-elevation.yml
grep -Fq 'ESTABLISH WINRM CONNECTION FOR USER: u on PORT 5985' "$run_dir/2a-pass.out"
grep -Fq 'PasswordAuthentication=no' "$run_dir/2b-precedence.out"
[ "$(grep -Fc 'ESTABLISH SSH CONNECTION FOR USER: prior-user' \
  "$run_dir/2b-precedence.out")" -eq 1 ]
[ "$(grep -Fc 'ESTABLISH SSH CONNECTION FOR USER: new-key' \
  "$run_dir/2b-precedence.out")" -eq 2 ]
grep -Fq 'boot not newer than the floor' "$run_dir/2e-caller-old-boot.out"
grep -Fq "works as 'elevated-winner'" "$run_dir/2e-caller-no-restart.out"
! grep -Fq 'Pausing for' "$run_dir/2e-caller-no-restart.out"
grep -Eq 'sudo -H -S -n +(-u root )?/bin/sh -c' "$run_dir/2f-posix-elevation.ssh"
for secret in "$CREDENTIAL_RESOLVER_CANARY_A" "$CREDENTIAL_RESOLVER_CANARY_B"; do
  ! grep -Fq -- "$secret" "${logs[@]}"
done
! grep -Fq -f "$run_dir/id" "${logs[@]}"
! grep -Fq -f "$run_dir/id.pub" "${logs[@]}"
printf 'CASE 2d-secrecy: PASS (0 canary hits)\nAll credential resolver cases passed.\n'
