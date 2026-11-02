#!/usr/bin/env bash
# Fails when a file under algorithms/ names a simulation or flight framework (README.md, Layout).
set -uo pipefail
pattern='\b(basilisk|fprime|f_prime)|Fw/|Svc/|cfe_|\b(osal|trick)([^a-z]|$)'
[ -d algorithms ] || { echo "algorithms/ is missing" >&2; exit 2; }
command grep -rniE \
  --include='*.py' --include='*.c' --include='*.cc' --include='*.cpp' \
  --include='*.h' --include='*.hh' --include='*.hpp' \
  "$pattern" algorithms
case $? in 0) exit 1 ;; 1) exit 0 ;; *) exit 2 ;; esac
