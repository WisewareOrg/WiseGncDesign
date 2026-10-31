#!/usr/bin/env bash
set -euo pipefail

# hosts/ imports no WiseDynamics module, so a flight host adapter stays independent of the simulation repo.
if command grep -rniE --include='*.py' 'wise_dynamics|sim\.basilisk' hosts/
then
  exit 1
fi
exit 0
