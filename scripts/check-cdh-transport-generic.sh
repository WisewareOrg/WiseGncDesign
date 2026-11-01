#!/usr/bin/env bash
set -euo pipefail

target=gnc_cdh/basilisk/algorithm_module.py
if [ ! -f "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# gnc_cdh/basilisk/algorithm_module.py hosts any algorithm generically; a match here means
# algorithm- or sensor-specific vocabulary leaked into the generic host, including inside an
# identifier (snake_case or camelCase), which is how this vocabulary actually leaks into code.
# Substring matching, not word-bounded, mirroring WiseDynamics' scripts/check-hosting-generic.sh,
# whose full list this carries over including "dcm_pb" (the IMU sensor's platform-to-body DCM
# attribute name): this module already uses the neutral "mountings"/"P->B" in its place, so
# "dcm_pb" appearing here would mean a sensor-specific name crept back in.
pattern='imu|gyro|accel|mrp|sigma|reckon|navatt|navtrans|tracker|omega|quaternion|dcm_pb|attitude'

# "imu" also false-positives on the English words "simulation" and "maximum" (both contain "imu"
# as a substring). Strip just those two word-fragments from each line before matching -- never
# drop the whole line, since a real leak sharing a line with one of those words (for example
# "simulation imu_bias") must still be caught.
line_numbers=$(sed -E 's/simulat[a-z]*//Ig; s/maxim[a-z]*//Ig' "$target" \
  | command grep -niE "$pattern" \
  | cut -d: -f1 || true)

if [ -n "$line_numbers" ]; then
  matches=$(while IFS= read -r n; do
    sed -n "${n}p" "$target" | sed "s/^/${n}:/"
  done <<<"$line_numbers")
  echo "$matches"
  exit 1
fi
exit 0
