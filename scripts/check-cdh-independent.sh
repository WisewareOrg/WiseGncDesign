#!/usr/bin/env bash
set -euo pipefail

target=gnc_cdh/
if [ ! -d "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# gnc_cdh/ imports no WiseDynamics module, so the C&DH partition stays independent of the
# simulation repo. WiseDynamics' root package is "sim" (sim/__init__.py), not "wise_dynamics",
# so the pattern keys on "sim" itself, not only its "sim.basilisk" submodule.
pattern='wise_dynamics|sim\.basilisk|sim/basilisk|WiseDynamics|^[[:space:]]*import[[:space:]]+sim([.[:space:]]|$)|^[[:space:]]*from[[:space:]]+sim([.[:space:]]|[[:space:]]+import)'
matches=$(command grep -rniE --include='*.py' "$pattern" "$target" || true)

if [ -n "$matches" ]; then
  echo "$matches"
  exit 1
fi
exit 0
