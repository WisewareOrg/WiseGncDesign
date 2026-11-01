#!/usr/bin/env bash
set -euo pipefail

target=analysis/
if [ ! -d "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# analysis/ imports no gnc_algorithms, gnc_cdh, Basilisk or WiseDynamics module: the grader
# shares no code with the algorithms it measures, nor with the host or simulation repos.
# Anchored to an import statement's module root (not a bare substring), so a docstring naming
# these repos in prose does not false-positive, and "sim" catches WiseDynamics' root package
# (sim/__init__.py) without also matching "simulate"/"similar". The "import" alternative scans
# the whole line, so a comma-separated form such as "import os, gnc_cdh" still matches; "from"
# has at most one root module, so it stays anchored immediately after the keyword.
pattern='^[[:space:]]*from[[:space:]]+(gnc_algorithms|gnc_cdh|Basilisk|wise_dynamics|sim)\b|^[[:space:]]*import[[:space:]].*\b(gnc_algorithms|gnc_cdh|Basilisk|wise_dynamics|sim)\b'
matches=$(command grep -rnE --include='*.py' "$pattern" "$target" || true)

if [ -n "$matches" ]; then
  echo "$matches"
  exit 1
fi
exit 0
