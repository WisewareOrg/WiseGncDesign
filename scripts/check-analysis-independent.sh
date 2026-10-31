#!/usr/bin/env bash
set -euo pipefail

target=analysis/
if [ ! -d "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# analysis/ imports no gnc_cdh, Basilisk or WiseDynamics module, so run analysis stays
# independent of the host and simulation repos. Anchored to an import statement's module root
# (not a bare substring), so a docstring naming these repos in prose does not false-positive,
# and "sim" catches WiseDynamics' root package (sim/__init__.py) without also matching
# "simulate"/"similar".
pattern='^[[:space:]]*(import|from)[[:space:]]+(gnc_cdh|Basilisk|wise_dynamics|sim)\b'
matches=$(command grep -rnE --include='*.py' "$pattern" "$target" || true)

if [ -n "$matches" ]; then
  echo "$matches"
  exit 1
fi
exit 0
