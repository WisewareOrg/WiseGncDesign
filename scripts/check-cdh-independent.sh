#!/usr/bin/env bash
# Fails when a Python file under cdh/ names the simulation repository (cdh/README.md).
set -uo pipefail
pattern='wise_?dynamics'
[ -d cdh ] || { echo "cdh/ is missing" >&2; exit 2; }
command grep -rniE --include='*.py' "$pattern" cdh
case $? in 0) exit 1 ;; 1) exit 0 ;; *) exit 2 ;; esac
