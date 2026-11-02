#!/usr/bin/env bash
# Fails when a transport's generic host modules name an algorithm's or sensor's vocabulary
# (cdh/README.md).
set -uo pipefail
shopt -s nullglob
pattern='imu|gyro|accel|mrp|sigma|reckon|navatt|navtrans|tracker|omega|quaternion|dcm_pb|attitude'
targets=(cdh/gnc_cdh/*/__init__.py cdh/gnc_cdh/*/algorithm_module.py cdh/gnc_cdh/*/fsw.py)
[ ${#targets[@]} -gt 0 ] || { echo "no transport's generic modules under cdh/gnc_cdh/" >&2; exit 2; }
command grep -niE "$pattern" "${targets[@]}"
case $? in 0) exit 1 ;; 1) exit 0 ;; *) exit 2 ;; esac
