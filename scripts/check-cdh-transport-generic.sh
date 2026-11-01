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
# as a substring). Strip just those two words' own forms from each line before matching -- never
# drop the whole line, since a real leak sharing a line with one of those words (for example
# "simulation imu_bias") must still be caught. Word-bounded (\b...\b), not [a-z]*: an unbounded
# strip also eats the "Imu"/"Rate" tail of camelCase identifiers like "simulatedImuSample", which
# is exactly the kind of leak this gate exists to catch.
line_numbers=$(sed -E 's/\b(simulat(ion|ions|e|ed|es|ing|or|ors)|maxim(um|ums|al|ize|ise|izing))\b//Ig' "$target" \
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
