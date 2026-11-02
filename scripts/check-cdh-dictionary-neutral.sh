#!/usr/bin/env bash
# Fails when a transport-neutral module of gnc_cdh names a transport's vocabulary
# (cdh/README.md).
set -uo pipefail
shopt -s nullglob
pattern='Basilisk|basilisk|messaging|Msg|Payload|Platform|Reader|Writer|SysModel|r_BN_N|v_BN_N'
targets=(cdh/gnc_cdh/*.py)
[ ${#targets[@]} -gt 0 ] || { echo "no file matches cdh/gnc_cdh/*.py" >&2; exit 2; }
command grep -nE "$pattern" "${targets[@]}"
case $? in 0) exit 1 ;; 1) exit 0 ;; *) exit 2 ;; esac
