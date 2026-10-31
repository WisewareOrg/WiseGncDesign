#!/usr/bin/env bash
set -euo pipefail

# algorithms/ imports or includes no simulation or flight-framework name, so flight code stays host-swappable.
if command grep -rniE \
  --include='*.py' --include='*.c' --include='*.cc' --include='*.cpp' --include='*.h' --include='*.hh' --include='*.hpp' \
  'basilisk|fprime|f_prime|Fw/|Svc/|cfe_|osal|trick' \
  algorithms/
then
  exit 1
fi
exit 0
