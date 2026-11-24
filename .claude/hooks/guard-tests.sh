#!/usr/bin/env bash
# Queues test runs so one runs at a time on the machine: agents never start a suite alongside each other or
# underneath the owner's own run, and never start one while memory is short.
#
# As a PreToolUse hook on Bash|Monitor it never allows, and denies only when the lock directory is not the user's own.
# A command that calls pytest, executes a notebook (jupytext/nbconvert --execute, papermill), or names a just recipe
# whose body does either, is rewritten through updatedInput to run inside
#
#     { guard-tests.sh wait 9 || exit $?
#     <original command>
#     } 9>|/tmp/claude-$UID/test-run.lock
#
# so the calling shell holds an flock on the lock file for exactly as long as the command and anything it starts
# keep the descriptor open. The group runs in the calling shell, so cd, &&, pipes and env prefixes behave as typed.
# Every other command passes untouched.
#
# `guard-tests.sh wait FD [SECONDS]` is that first line: it takes the lock on FD, then waits while a test process
# started outside the lock is running or MemAvailable is under the floor. Both waits share one budget of SECONDS
# (default 1800); past it the command does not run and exits 75 with the reason. A Bash call that reaches its tool
# timeout while queued moves to the background and keeps waiting. The kernel drops the lock with the descriptor, so
# a refused or killed wait leaves nothing behind.
#
# The hook returns no permissionDecision, so permission rules see the rewritten command. In auto mode a second
# rewritten call in the same response is refused for review; re-issuing the rewritten command exactly runs it, and
# a command already carrying the wrapper's first line passes untouched, so it is never wrapped twice.
set -u

floor_kib=$((6 * 1024 * 1024))
running='/bin/pytest|-m pytest|py\.test|papermill|nbconvert.*--execute|jupytext.*--execute'
calls_tests='(^|[^[:alnum:]_-])(pytest|py\.test|papermill)([^[:alnum:]_-]|$)|(jupytext|nbconvert).*--execute'
state="/tmp/claude-$(id -u)"
lock="$state/test-run.lock"
self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# Test processes not started through the lock: what pgrep finds, less this shell's ancestry and the shells that
# carry a queued command's text in their argv.
foreign() {
    local ancestors=" " pid=$$ p rest
    while ((pid > 1)); do ancestors+="$pid " pid=$(ps -o ppid= -p "$pid" | tr -d ' '); done
    pgrep -af -- "$running" | while read -r p rest; do
        [[ $ancestors == *" $p "* ]] && continue
        [[ $(ps -o comm= -p "$p") =~ ^(ba|z|da)?sh$ ]] && continue
        printf '%s %s\n' "$p" "${rest:0:150}"
    done
}

if [[ ${1-} == wait ]]; then
    fd=$2 budget=${3:-1800}
    give_up() {
        echo "test lock: $1 after ${budget} s; this command did not run. Retry it; nothing needs cleaning up." >&2
        exit 75
    }
    if ! flock -n "$fd"; then
        echo "test lock: another test run holds $lock; queued for up to ${budget} s" >&2
        flock -w "$budget" "$fd" || give_up "still held"
    fi
    while :; do
        others=$(foreign)
        available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
        [[ -z $others ]] && ((available >= floor_kib)) && exit 0
        if ((SECONDS >= budget)); then
            [[ -n $others ]] && give_up "a test process outside the lock is still running: ${others//$'\n'/ | }"
            give_up "only $((available / 1024)) MiB still available, under the $((floor_kib / 1024)) MiB floor"
        fi
        ((${told-0})) || echo "test lock: waiting for ${others:-$((available / 1024)) MiB free memory to reach the floor}" >&2
        told=1
        sleep 5
    done
fi

payload=$(cat)
cmd=$(jq -r '.tool_input.command // ""' <<<"$payload")
cwd=$(jq -r '.cwd // ""' <<<"$payload")

is_test_run() {
    [[ $cmd =~ $calls_tests ]] && return 0
    local -a words pre
    local w in_just=0
    read -ra words <<<"${cmd//[;&|()]/ ; }"
    for w in "${words[@]}"; do
        if [[ $w == just || $w == */just ]]; then in_just=1; pre=(); continue; fi
        [[ $w == ";" ]] && { in_just=0; continue; }
        if ((in_just)); then
            if [[ $w != -* ]] && (cd "${cwd:-.}" 2>/dev/null && just "${pre[@]}" --show "$w" 2>/dev/null) |
                command grep -Eq "$calls_tests"; then
                return 0
            fi
            pre+=("$w")
        fi
    done
    return 1
}
prefix=$(printf '{ %q wait 9 || exit $?' "$self")
[[ $cmd == "$prefix"$'\n'* ]] && exit 0
is_test_run || exit 0

[[ -d $state ]] || mkdir -m 700 "$state"
if [[ ! -O $state || -L $state ]]; then
    jq -cn --arg r "$state is not a directory this user owns, so the test lock cannot live there." \
        '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
    exit 0
fi
wrapped=$(printf '%s\n%s\n} 9>|%q' "$prefix" "$cmd" "$lock")
printf '%s' "$payload" | jq -c --arg c "$wrapped" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", updatedInput: (.tool_input | .command = $c)}}'
