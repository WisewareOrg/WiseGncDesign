#!/usr/bin/env bash
set -euo pipefail

# cdh/ imports no WiseDynamics module, so the C&DH partition stays independent of the simulation repo.
if command grep -rniE --include='*.py' 'wise_dynamics|sim\.basilisk' cdh/
then
  exit 1
fi
exit 0
