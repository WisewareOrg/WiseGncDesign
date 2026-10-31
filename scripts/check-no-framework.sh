#!/usr/bin/env bash
set -euo pipefail

target=algorithms/
if [ ! -d "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# algorithms/ imports or includes no simulation or flight-framework name, so flight code stays host-swappable.
if command grep -rniE \
  --include='*.py' --include='*.c' --include='*.cc' --include='*.cpp' --include='*.h' --include='*.hh' --include='*.hpp' \
  'basilisk|fprime|f_prime|Fw/|Svc/|cfe_|osal|trick' \
  "$target"
then
  exit 1
fi
exit 0
