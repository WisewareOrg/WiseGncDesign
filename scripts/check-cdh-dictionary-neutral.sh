#!/usr/bin/env bash
set -euo pipefail

target=gnc_cdh/bindings.py
if [ ! -f "$target" ]; then
  echo "$target is missing" >&2
  exit 1
fi

# gnc_cdh/bindings.py names no transport-specific type, class or payload field, and imports no
# transport subpackage under any spelling (gnc_cdh.basilisk, cdh.basilisk, "from gnc_cdh import
# basilisk", "from .basilisk import ..."), so the data dictionary stays transport-independent.
# Case-sensitive: Basilisk's own vocabulary is capitalized this way (AngVelPlatform, NavAttMsg,
# NavAttMsgPayload, SysModel, Basilisk.architecture.messaging), and its package name is this
# lowercase "basilisk"; the neutral frame name "platform_to_body" survives both.
pattern='Basilisk|basilisk|messaging|Msg|Payload|Platform|Reader|Writer|SysModel|r_BN_N|v_BN_N'
if command grep -nE "$pattern" "$target"
then
  exit 1
fi
exit 0
