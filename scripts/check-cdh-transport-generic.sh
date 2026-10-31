#!/usr/bin/env bash
set -euo pipefail

target=gnc_cdh/basilisk/algorithm_module.py
if [ ! -f "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# gnc_cdh/basilisk/algorithm_module.py hosts any algorithm generically; a match here means
# algorithm-specific vocabulary leaked into the generic host, including inside an identifier
# (snake_case or camelCase), which is how this vocabulary actually leaks into code. Substring
# matching, not word-bounded, mirroring WiseDynamics' scripts/check-hosting-generic.sh.
matches=$(command grep -niE \
  'imu|gyro|accel|mrp|sigma|reckon|navatt|navtrans|tracker|omega|quaternion|attitude' \
  "$target" || true)

if [ -n "$matches" ]; then
  echo "$matches"
  exit 1
fi
exit 0
