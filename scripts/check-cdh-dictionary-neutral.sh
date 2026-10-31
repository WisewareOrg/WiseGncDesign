#!/usr/bin/env bash
set -euo pipefail

# cdh/bindings.py names no transport-specific type, class or payload field, so the data
# dictionary stays transport-independent. Case-sensitive: Basilisk's own vocabulary is
# capitalized this way (AngVelPlatform, NavAttMsg, NavAttMsgPayload, Basilisk.architecture.messaging).
if command grep -nE 'Basilisk|messaging|Msg|Payload|Platform' cdh/bindings.py
then
  exit 1
fi
exit 0
