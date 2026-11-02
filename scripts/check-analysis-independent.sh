#!/usr/bin/env bash
# Fails when a Python file under analysis/ imports the algorithms, the C&DH partition, Basilisk
# or the simulation repository (analysis/README.md).
set -uo pipefail
banned='(gnc_algorithms|gnc_cdh|Basilisk|wise_dynamics)'
pattern="^[[:space:]]*from[[:space:]]+${banned}\b|^[[:space:]]*import[[:space:]].*\b${banned}\b"
[ -d analysis ] || { echo "analysis/ is missing" >&2; exit 2; }
command grep -rnE --include='*.py' "$pattern" analysis
case $? in 0) exit 1 ;; 1) exit 0 ;; *) exit 2 ;; esac
