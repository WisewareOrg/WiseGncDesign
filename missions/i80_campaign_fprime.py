"""Issue 80 spike: the dead reckoner's full campaign (missions/dead_reckoner_leo.py) on the fprime build."""

import os
import sys

sys.path.insert(0, "/tmp/claude-1000/-home-wise-code-WiseGncDesign/e208a9fd-e128-4d35-9e3e-2074bc41b06b/scratchpad/issue80/campaign")
import patches  # noqa: E402,F401  (applies the levers named in I80_LEVERS, if any)

from harness.mission import Mission, mission_tests  # noqa: E402

BASE = Mission(
    vehicle="imu_spacecraft",
    gnc="ImuDeadReckoning",
    build="fprime",
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
)
MISSIONS = [BASE, BASE.but(vehicle="heavy_imu_spacecraft")]
globals().update(mission_tests(*MISSIONS))
