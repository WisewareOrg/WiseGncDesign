#!/usr/bin/env bash
# PreToolUse hook on Bash. Lets one test run at a time onto the machine, so agents never start a suite alongside
# each other or underneath the owner's own run, and never start one while memory is short.
#
# A command is a test run when it calls pytest, executes a notebook (jupytext/nbconvert --execute, papermill), or
# names a just recipe whose body does either. Such a command is denied while another test process is running, while
# MemAvailable is under the floor, or within a short window after this hook let another test run through (the window
# closes the race between two agents checking at the same moment, before either's pytest exists).
# Every other command passes untouched, and this hook never allows anything: it only denies or stays silent.
set -u

floor_kib=$((6 * 1024 * 1024))
claim_window_s=60
running='/bin/pytest|-m pytest|py\.test|papermill|nbconvert.*--execute|jupytext.*--execute'
calls_tests='(^|[^[:alnum:]_-])(pytest|py\.test|papermill)([^[:alnum:]_-]|$)|(jupytext|nbconvert).*--execute'

payload=$(cat)
field() {
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$payload" | jq -r "$1 // \"\""
    else
        printf '%s' "$payload" | python3 -c 'import json,sys
d=json.load(sys.stdin)
for k in sys.argv[1].lstrip(".").split("."): d=d.get(k,{}) if isinstance(d,dict) else {}
print(d if isinstance(d,str) else "")' "$1"
    fi
}
cmd=$(field .tool_input.command)
cwd=$(field .cwd)

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
is_test_run || exit 0

deny() {
    jq -cn --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny",
        permissionDecisionReason: ("One test run at a time on this machine: " + $r +
        ". Wait for it to finish (check with: free -h), then retry. Do not work around this gate.")}}'
    exit 0
}

state="/tmp/claude-$(id -u)"
mkdir -p "$state"
exec 9>"$state/test-gate.lock"
flock -w 5 9 || deny "the test gate is busy"

claim="$state/test-gate.claim"
if [[ -f $claim ]] && (($(date +%s) - $(stat -c %Y "$claim") < claim_window_s)); then
    deny "another agent was let through to start tests under ${claim_window_s} s ago"
fi
ancestors=" " pid=$$
while ((pid > 1)); do ancestors+="$pid " pid=$(ps -o ppid= -p "$pid" | tr -d ' '); done
others=$(pgrep -af -- "$running" | while read -r p rest; do
    [[ $ancestors == *" $p "* ]] || printf '%s %s\n' "$p" "${rest:0:150}"
done)
[[ -z $others ]] || deny "a test process is already running: ${others//$'\n'/ | }"
available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
((available >= floor_kib)) || deny "only $((available / 1024)) MiB of memory available, under the $((floor_kib / 1024)) MiB floor"
touch "$claim"
exit 0
